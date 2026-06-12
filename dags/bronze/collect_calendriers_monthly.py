"""DAG — Collecte calendriers (mensuel).

Données calendaires (vacances scolaires, jours fériés) — changent rarement.
DAG mensuel pour éviter ~8600 appels/mois inutiles.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion import MONTHLY_COLLECTORS, DataCollector

logger = logging.getLogger(__name__)


def _run_collector(collector_class: type[DataCollector]) -> dict:
    collector = collector_class()  # type: ignore
    result = collector.run()
    return {
        "source": result.source,
        "n_records": result.n_records,
        "duration_ms": result.duration_ms,
        "error": result.error,
    }


default_args = {
    "owner": "lyonflow",
    "retries": 2,
    "retry_delay": timedelta(hours=1),
}

with DAG(
    dag_id="collect_calendriers_monthly",
    description="Collecte calendriers (vacances scolaires + jours fériés) — mensuel",
    default_args=default_args,
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "ingestion", "calendrier"],
) as dag:
    for cls in MONTHLY_COLLECTORS:
        PythonOperator(
            task_id=f"collect_{cls.__name__.lower()}",
            python_callable=_run_collector,
            op_kwargs={"collector_class": cls},
            execution_timeout=timedelta(minutes=5),
        )
