"""DAG — Transform Bronze → Silver toutes les 5 min.

Suit la collecte Bronze (5 min après). Idempotent (UPSERT).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.transformation import transform_to_silver

logger = logging.getLogger(__name__)


def _transform(source: str) -> int:
    return transform_to_silver(source=source)


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="transform_bronze_to_silver",
    description="Bronze → Silver toutes les 5 min (5 sources en parallèle)",
    default_args=default_args,
    schedule_interval="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transform", "silver"],
) as dag:
    for source in ["trafic_boucles", "velov", "tcl_vehicles", "meteo", "chantiers"]:
        PythonOperator(
            task_id=f"transform_{source}",
            python_callable=_transform,
            op_kwargs={"source": source},
            execution_timeout=timedelta(minutes=5),
        )
