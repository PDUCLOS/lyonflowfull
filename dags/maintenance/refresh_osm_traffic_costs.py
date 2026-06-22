"""DAG — Refresh des coûts trafic sur le réseau routier OSM.

Appelle osm.refresh_traffic_costs() toutes les 15 min pour
injecter les vitesses capteurs Grand Lyon dans les arêtes OSM.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator

default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="refresh_osm_traffic_costs",
    default_args=default_args,
    description="Refresh coûts trafic temps réel sur arêtes OSM (pgRouting)",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["maintenance", "routing", "pgrouting"],
) as dag:
    refresh = PostgresOperator(
        task_id="refresh_traffic_costs",
        postgres_conn_id="lyonflow_postgres",
        sql="SELECT osm.refresh_traffic_costs();",
    )
