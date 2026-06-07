"""DAG — Transform Silver → Gold toutes les 10 min.

Construit les features ML-ready (traffic_features, velov_features,
bus_delay_segments) via SQL set-based (psycopg2). Aucune lambda dans le
DAG — chaque task a sa propre fonction Python typée.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.transformation import transform_silver_to_gold

logger = logging.getLogger(__name__)


def _build_traffic() -> dict[str, int]:
    return transform_silver_to_gold(target="traffic")


def _build_velov() -> dict[str, int]:
    return transform_silver_to_gold(target="velov")


def _build_bus_delay() -> dict[str, int]:
    return transform_silver_to_gold(target="bus_delay")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="transform_silver_to_gold",
    description="Silver → Gold toutes les 10 min (3 domaines en parallèle)",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transform", "gold"],
) as dag:
    PythonOperator(
        task_id="build_traffic_features",
        python_callable=_build_traffic,
        execution_timeout=timedelta(minutes=10),
    )

    PythonOperator(
        task_id="build_velov_features",
        python_callable=_build_velov,
        execution_timeout=timedelta(minutes=10),
    )

    PythonOperator(
        task_id="build_bus_delay_segments",
        python_callable=_build_bus_delay,
        execution_timeout=timedelta(minutes=10),
    )
