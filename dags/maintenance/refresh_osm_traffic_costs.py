"""DAG — Refresh des coûts trafic sur le réseau routier OSM.

Appelle osm.refresh_traffic_costs() toutes les 15 min pour
injecter les vitesses capteurs Grand Lyon dans les arêtes OSM.

Note : ce DAG était en ``PostgresOperator(..., postgres_conn_id='lyonflow_postgres')``
mais cette conn Airflow n'existe pas sur le VPS (seule ``postgres_default`` est
provisionnée, et elle pointe sur le user ``postgres`` ≠ ``lyonflow``). On
passe en ``PythonOperator`` + ``psycopg2.connect(os.getenv(...))`` — même
pattern que ``critical_pipeline_health.py`` (Sprint 24).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}


def _refresh_traffic_costs() -> int:
    """Refresh osm.ways cost depuis vitesse capteurs Grand Lyon.

    Returns:
        Nombre d'arêtes OSM dont le coût a été mis à jour.
    """
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
            cur.execute("SELECT osm.refresh_traffic_costs();")
            row = cur.fetchone()
        conn.commit()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


with DAG(
    dag_id="refresh_osm_traffic_costs",
    default_args=default_args,
    description="Refresh coûts trafic temps réel sur arêtes OSM (pgRouting)",
    # Décalé 3,18,33,48 (au lieu de */15 pile) — évite le thundering herd
    # :00/:15/:30/:45 avec collect_bronze/dag_inference_xgboost/etc.
    # (cf. docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md item C1).
    schedule="3,18,33,48 * * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "routing", "pgrouting"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_traffic_costs",
        python_callable=_refresh_traffic_costs,
        execution_timeout=timedelta(minutes=5),
    )
