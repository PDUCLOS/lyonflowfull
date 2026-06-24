"""DAG — Refresh materialised view ``gold.mv_sensor_saturation`` (Sprint 22+).

Schedule : */15 minutes (décalé à :07 pour ne pas marcher en même temps
que les DAGs critiques :00/:15/:30/:45). Le décalage évite les
spikes CPU sur le serveur PostgreSQL.

Refresh : ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` — nécessite
l'``UNIQUE INDEX idx_mv_sensor_saturation_channel`` créé en migration
034. Sans cet index, le refresh bloquerait tous les reads pendant
le recompute.

Pourquoi ce DAG existe :
- La migration 033 créait une VIEW (non matérialisée) qui scannait
  ~889k rows x 2 fenêtres temporelles + percentiles + STDDEV + 3
  LEFT JOINs → > 60 s en prod (timeout widget Streamlit).
- Migration 034 matérialise la vue + index unique.
- Ce DAG re-calcule la matérialisation toutes les 15 min → 0-15 min
  lag acceptable (le widget a un cache Streamlit 60s de toute façon).
- Trade-off validé : 0 lag + 60s/query → 0-15min lag + <100ms/query.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import psycopg2
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

from src.config import get_settings

_DAG_ID = "refresh_sensor_saturation"
_DAG_SCHEDULE = "7,22,37,52 * * * *"  # toutes les 15 min, décalé :07


@dag(
    dag_id=_DAG_ID,
    description="Refresh MV gold.mv_sensor_saturation (Sprint 22+ saturation/amplitude)",
    start_date=datetime(2026, 6, 22),
    schedule=_DAG_SCHEDULE,
    catchup=False,
    max_active_runs=1,  # pas de chevauchement (REFRESH CONCURRENTLY le permet, mais ceinture+bretelles)
    default_args={
        "owner": "lyonflow",
        "retries": 0,  # critique : le cycle suivant rattrape (Sprint 8+)
        "execution_timeout": timedelta(minutes=5),
    },
    tags=["maintenance", "saturation", "sprint22+"],
)
def refresh_sensor_saturation_dag() -> None:
    """DAG qui rafraîchit la matérialisation toutes les 15 min."""

    start = EmptyOperator(task_id="start")

    @task
    def refresh() -> None:
        """REFRESH MATERIALIZED VIEW CONCURRENTLY (no-read-block)."""
        settings = get_settings()
        conn = psycopg2.connect(
            host=settings.postgres_host,
            user=settings.postgres_user,
            password=settings.postgres_password,
            dbname=settings.postgres_db,
            connect_timeout=30,
        )
        try:
            with conn.cursor() as cur:
                # CONCURRENTLY = pas de blocage des reads (besoin
                # de l'UNIQUE INDEX idx_mv_sensor_saturation_channel).
                cur.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_sensor_saturation;"
                )
            conn.commit()
        finally:
            conn.close()

    end = EmptyOperator(task_id="end")

    start >> refresh() >> end


# Instanciation requise par Airflow (pattern @dag)
refresh_sensor_saturation_dag()
