"""DAG — Refresh vues matérialisées Gold , 2026-06-11).

Cycle : quotidien 5h (apres collect_bronze 02:00, transform 02:30,
gold 03:00, drift 06:00).

Taches :
1. REFRESH MATERIALIZED VIEW gold.mv_line_kpis_live CONCURRENTLY
2. REFRESH MATERIALIZED VIEW gold.mv_otp_heatmap CONCURRENTLY
3. referentiel.lieux_calendrier (table, pas matview) : UPSERT depuis
   referentiel.v_cadence_summary

Notes :
* CONCURRENTLY necessite UNIQUE INDEX sur la vue (deja cree dans le
  script SQL de creation).
* En cas d'echec d'une tache, les autres continuent (best effort).
* Logs structures pour monitoring Prometheus.
"""

from __future__ import annotations

import logging
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
    """Re-popule referentiel.lieux_calendrier depuis referentiel.v_cadence_summary.

    UPSERT direct en SQL. L'ancienne version lançait
    ``/opt/lyonflow/scripts/seed_lieux_calendrier.py`` en sous-processus, or
    ``scripts/`` n'est pas monté dans les containers Airflow : la tâche n'a
    jamais réussi (table figée au 2026-06-11). Le script reste utilisable à la
    main ; la requête ci-dessous fait le même UPSERT.

    La vue ne couvre que la fenêtre récente de gold.tcl_vehicle_realtime : chaque
    run met à jour le type de jour courant, les 4 types sont rafraîchis en une
    semaine.
    """
    from src.db import execute_query

    rows = execute_query(
        """
        WITH upserted AS (
            INSERT INTO referentiel.lieux_calendrier
                (line_ref, day_type, time_bucket, cadence_min_per_vehicle,
                 n_observations, confidence, computed_at)
            SELECT line_ref, day_type, time_bucket, cadence_min_per_vehicle,
                   n_observations, confidence, NOW()
            FROM referentiel.v_cadence_summary
            ON CONFLICT (line_ref, day_type, time_bucket) DO UPDATE SET
                cadence_min_per_vehicle = EXCLUDED.cadence_min_per_vehicle,
                n_observations          = EXCLUDED.n_observations,
                confidence              = EXCLUDED.confidence,
                computed_at             = NOW()
            RETURNING day_type
        )
        SELECT day_type, COUNT(*) AS n FROM upserted GROUP BY day_type ORDER BY day_type
        """
    )
    if not rows:
        logger.warning(
            "v_cadence_summary vide : gold.tcl_vehicle_realtime sans données récentes "
            "(réseau TCL à l'arrêt ou collecte en panne). Rien à mettre à jour."
        )
        return
    logger.info(
        "lieux_calendrier : %s lignes upsertées (%s)",
        sum(int(r["n"]) for r in rows),
        ", ".join(f"{r['day_type']}={r['n']}" for r in rows),
    )


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
