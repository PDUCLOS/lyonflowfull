"""DAG — Transform Silver → Gold toutes les 10 min.

Tasks actives :
- build_bus_delay_segments : silver.tcl_vehicles_clean → gold.bus_delay_segments
- build_infrastructure_bottlenecks : gold.bus_delay_segments x gold.traffic_features_live
  -> gold.infrastructure_bottlenecks (diagnostic infra/operations/bus_lane_ok)

Tasks NOOP (gérées par dags/legacy_github/dag_pipeline.py) :
- build_traffic_features : prod schema legacy (fetched_at, id, lag_1/2/3)
- build_velov_features : silver.velov_clean pas encore alimenté en prod
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.transformation.silver_to_gold import transform_silver_to_gold

logger = logging.getLogger(__name__)


def _noop_traffic() -> dict[str, int]:
    logger.info("[NOOP] build_traffic_features: handled by legacy_github DAG")
    return {"traffic": 0}


def _noop_velov() -> dict[str, int]:
    logger.info("[NOOP] build_velov_features: silver.velov_clean not fed yet")
    return {"velov": 0}


def _run_bus_delay() -> dict[str, int]:
    return transform_silver_to_gold(target="bus_delay")


def _run_bottleneck() -> dict[str, int]:
    return transform_silver_to_gold(target="bottleneck")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="transform_silver_to_gold",
    description="Silver → Gold (bus_delay + bottleneck actifs, traffic/velov NOOP)",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transform", "gold"],
) as dag:
    noop_traffic = PythonOperator(
        task_id="build_traffic_features",
        python_callable=_noop_traffic,
        execution_timeout=timedelta(minutes=1),
    )

    noop_velov = PythonOperator(
        task_id="build_velov_features",
        python_callable=_noop_velov,
        execution_timeout=timedelta(minutes=1),
    )

    bus_delay = PythonOperator(
        task_id="build_bus_delay_segments",
        python_callable=_run_bus_delay,
        execution_timeout=timedelta(minutes=5),
    )

    bottleneck = PythonOperator(
        task_id="build_infrastructure_bottlenecks",
        python_callable=_run_bottleneck,
        execution_timeout=timedelta(minutes=3),
    )

    bus_delay >> bottleneck
