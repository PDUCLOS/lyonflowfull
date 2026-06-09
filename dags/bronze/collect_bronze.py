"""DAG — Collecte Bronze temps réel (5 min).

Itère sur `REALTIME_COLLECTORS` (6 classes) et lance chaque collecteur
en parallèle. Les collecteurs calendaires (vacances scolaires, jours
fériés) sont dans `collect_calendriers_monthly.py` (DAG mensuel).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion import REALTIME_COLLECTORS, DataCollector

logger = logging.getLogger(__name__)


def _run_collector(collector_class: type[DataCollector]) -> dict:
    """Instancie le collecteur (lazy) puis lance run()."""
    collector = collector_class()  # type: ignore
    result = collector.run()
    return {
        "source": result.source,
        "n_records": result.n_records,
        "duration_ms": result.duration_ms,
        "error": result.error,
    }


def on_failure(context) -> None:
    logger.error("Task failed: %s", context["task_instance"].task_id)


default_args = {
    "owner": "lyonflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": on_failure,
}

with DAG(
    dag_id="collect_bronze",
    description="Collecte Bronze toutes les 5 min (6 sources temps réel)",
    default_args=default_args,
    schedule_interval="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "ingestion"],
) as dag:
    for cls in REALTIME_COLLECTORS:
        PythonOperator(
            task_id=f"collect_{cls.__name__.lower()}",
            python_callable=_run_collector,
            op_kwargs={"collector_class": cls},
            execution_timeout=timedelta(minutes=2),
        )
