"""DAG — Refresh vues matérialisées Gold (Sprint 7, 2026-06-11).

Cycle : quotidien 5h (apres collect_bronze 02:00, transform 02:30,
gold 03:00, drift 06:00).

Taches :
1. REFRESH MATERIALIZED VIEW gold.mv_line_kpis_live CONCURRENTLY
2. REFRESH MATERIALIZED VIEW gold.mv_otp_heatmap CONCURRENTLY
3. REFRESH MATERIALIZED VIEW referentiel.lieux_calendrier (table,
   pas matview — on la re-popule via seed_lieux_calendrier.py)

Notes :
* CONCURRENTLY necessite UNIQUE INDEX sur la vue (deja cree dans le
  script SQL de creation).
* En cas d'echec d'une tache, les autres continuent (best effort).
* Logs structures pour monitoring Prometheus.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _refresh_mv_line_kpis(**context) -> None:
    """Refresh mv_line_kpis_live depuis gold.bus_delay_segments."""
    from src.db import execute_query

    try:
        # CONCURRENTLY evite les locks en lecture (vu en service)
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_line_kpis_live")
        logger.info("mv_line_kpis_live refreshed OK")
    except Exception as e:
        # Si CONCURRENTLY echoue (1er run sans index unique, etc.),
        # on retombe sur un REFRESH standard.
        logger.warning("CONCURRENTLY refresh failed, fallback standard: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_line_kpis_live")


def _refresh_mv_otp_heatmap(**context) -> None:
    """Refresh mv_otp_heatmap depuis gold.bus_delay_segments."""
    from src.db import execute_query

    try:
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_otp_heatmap")
        logger.info("mv_otp_heatmap refreshed OK")
    except Exception as e:
        logger.warning("CONCURRENTLY refresh failed, fallback standard: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_otp_heatmap")


def _refresh_lieux_calendrier(**context) -> None:
    """Re-popule referentiel.lieux_calendrier via le script seed.

    Le calendrier (jours feries, vacances) evolue peu, mais les
    cadences (7j glissants) doivent etre recalculees pour rester
    representatives. Sprint 7+ : remplacer par une vue materialisee
    raffraichie en place.
    """
    try:
        result = subprocess.run(
            [sys.executable, "/opt/lyonflow/scripts/seed_lieux_calendrier.py"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("lieux_calendrier re-popule OK:\n%s", result.stdout)
        else:
            logger.error(
                "seed_lieux_calendrier a echoue (code=%d):\n%s\nstderr: %s",
                result.returncode,
                result.stdout,
                result.stderr,
            )
            raise RuntimeError(f"seed_lieux_calendrier failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("seed_lieux_calendrier timeout apres 300s")
        raise


default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=10),
}

with DAG(
    dag_id="refresh_lieux_calendrier",
    default_args=default_args,
    description="Refresh quotidien 5h : mv_line_kpis_live + mv_otp_heatmap + lieux_calendrier",
    schedule_interval="0 5 * * *",  # 5h tous les jours
    start_date=datetime(2026, 6, 11),
    catchup=False,
    max_active_runs=1,
    tags=["gold", "refresh", "sprint-7"],
) as dag:
    PythonOperator(
        task_id="refresh_mv_line_kpis",
        python_callable=_refresh_mv_line_kpis,
        provide_context=True,
    )
    PythonOperator(
        task_id="refresh_mv_otp_heatmap",
        python_callable=_refresh_mv_otp_heatmap,
        provide_context=True,
    )
    PythonOperator(
        task_id="refresh_lieux_calendrier",
        python_callable=_refresh_lieux_calendrier,
        provide_context=True,
    )
