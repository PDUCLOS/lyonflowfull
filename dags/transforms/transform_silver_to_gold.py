"""DAG — Transform Silver → Gold toutes les 10 min.

Tasks actives :
- build_traffic_features : silver.trafic_boucles_clean → gold.traffic_features_live
  (alimenté en 2026-06-10 — Sprint VPS-5 a renommé les colonnes, ce code a suivi)
- build_velov_features : silver.velov_clean → gold.velov_features
- build_tcl_realtime : silver.tcl_vehicles_clean → gold.tcl_vehicle_realtime
  (alimente le Pro_4_Simulateur)
- build_bus_delay_segments : silver.tcl_vehicles_clean → gold.bus_delay_segments
- build_infrastructure_bottlenecks : gold.bus_delay_segments x gold.traffic_features_live
  -> gold.infrastructure_bottlenecks (diagnostic infra/operations/bus_lane_ok)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.transformation.silver_to_gold import transform_silver_to_gold

logger = logging.getLogger(__name__)


def _run_traffic() -> dict[str, int]:
    return transform_silver_to_gold(target="traffic")


def _run_velov() -> dict[str, int]:
    return transform_silver_to_gold(target="velov")


def _run_tcl_realtime() -> dict[str, int]:
    return transform_silver_to_gold(target="tcl_realtime")


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
    description=("Silver → Gold (traffic + velov + tcl_realtime + bus_delay + bottleneck) — toutes les 10 min"),
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transform", "gold"],
) as dag:
    traffic = PythonOperator(
        task_id="build_traffic_features",
        python_callable=_run_traffic,
        execution_timeout=timedelta(minutes=5),
    )

    velov = PythonOperator(
        task_id="build_velov_features",
        python_callable=_run_velov,
        execution_timeout=timedelta(minutes=3),
    )

    tcl_realtime = PythonOperator(
        task_id="build_tcl_realtime",
        python_callable=_run_tcl_realtime,
        execution_timeout=timedelta(minutes=2),
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

    # Bottleneck dépend des deux : bus_delay (intra-jour) et traffic (lat/lon pour la carte)
    [traffic, velov, tcl_realtime, bus_delay] >> bottleneck
