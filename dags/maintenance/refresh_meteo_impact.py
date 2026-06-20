"""DAG — Refresh quotidien de gold.mv_meteo_impact (Sprint 17, 2026-06-20).

Cycle : quotidien 04h30 (apres collect_bronze 02:00, transform 02:30,
gold 03:00, drift 06:00).

Tache :
1. REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_meteo_impact

Notes :
* Sprint 17 Axe 7 — Météo comme variable d'interaction.
* La vue agrege 30 jours d'historique sur silver.meteo_hourly x
  gold.traffic_features_live x gold.tcl_vehicle_realtime x
  silver.velov_clean. Cout : moyen (~30j x 3 JOINs).
* CONCURRENTLY necessite UNIQUE INDEX sur la vue (idx_gold_mv_meteo_impact_band,
  cree dans migration_022).
* En cas d'echec CONCURRENTLY, fallback REFRESH standard.
* Schedule 04h30 (pas */X) car la vue n'a pas besoin d'etre temps-reel :
  elle sert au tableau comparatif historique Pro_3_Correlation.
* Logs structures pour monitoring Prometheus.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _refresh_mv_meteo_impact(**context) -> None:
    """Refresh gold.mv_meteo_impact (Sprint 17 Axe 7, migration 022).

    Vue matérialisée qui calcule l'impact de 5 bandes météo (fair,
    light_rain, heavy_rain, frost, heatwave) sur 3 modes de transport
    (trafic, TCL, Vélov) avec delta vs baseline "beau temps".
    """
    from src.db import execute_query

    try:
        # CONCURRENTLY evite les locks en lecture (la vue reste lisible
        # pendant le refresh). Necessite UNIQUE INDEX sur meteo_band
        # (cree dans migration_022).
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_meteo_impact")
        logger.info("gold.mv_meteo_impact refreshed OK (CONCURRENTLY)")
    except Exception as e:
        # Si CONCURRENTLY echoue (1er run sans index unique, lock
        # concurrent, etc.), on retombe sur un REFRESH standard.
        logger.warning("CONCURRENTLY refresh failed, fallback standard: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_meteo_impact")
        logger.info("gold.mv_meteo_impact refreshed OK (fallback standard)")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="refresh_meteo_impact",
    description=(
        "Sprint 17 Axe 7 — REFRESH quotidien gold.mv_meteo_impact "
        "(impact meteo x modes, 30 jours historique, migration 022)"
    ),
    default_args=default_args,
    schedule_interval="30 4 * * *",  # 04h30 tous les jours
    start_date=datetime(2026, 6, 20),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "gold", "sprint17", "axe7"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_mv_meteo_impact",
        python_callable=_refresh_mv_meteo_impact,
        execution_timeout=timedelta(minutes=10),
    )
