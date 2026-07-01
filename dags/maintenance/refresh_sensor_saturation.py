"""DAG — Refresh materialised view ``gold.mv_sensor_saturation`` ).

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

import os
from datetime import datetime, timedelta

import psycopg2
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

_DAG_ID = "refresh_sensor_saturation"
_DAG_SCHEDULE = "7,22,37,52 * * * *"  # toutes les 15 min, décalé :07


@dag(
    dag_id=_DAG_ID,
    description="Refresh MV gold.mv_sensor_saturation saturation/amplitude)",
    start_date=datetime(2026, 6, 22),
    schedule=_DAG_SCHEDULE,
    catchup=False,
    max_active_runs=1,  # pas de chevauchement (REFRESH CONCURRENTLY le permet, mais ceinture+bretelles)
    default_args={
        "owner": "lyonflow",
        "retries": 0,  # critique : le cycle suivant rattrape )
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
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "lyonflow"),
            user=os.getenv("POSTGRES_USER", "lyonflow"),
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=30,
            options="-c statement_timeout=240000",  # 240s < execution_timeout Airflow (5min) — sans ça, un timeout Airflow tue le worker mais pas la requête Postgres (I/O bloquant), qui continue à saturer sdb
        )
        try:
            with conn.cursor() as cur:
                # CONCURRENTLY = pas de blocage des reads (besoin
                # de l'UNIQUE INDEX idx_mv_sensor_saturation_channel).
                cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_sensor_saturation;")
            conn.commit()
        finally:
            conn.close()

    end = EmptyOperator(task_id="end")

    start >> refresh() >> end


# Instanciation requise par Airflow (pattern @dag)
refresh_sensor_saturation_dag()
