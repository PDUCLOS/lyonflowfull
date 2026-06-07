"""DAG — Collecte calendriers (mensuel, séparé du DAG 5-min).

Données calendaires (vacances scolaires, jours fériés) — changent rarement.
DAG mensuel pour éviter 8600 appels/mois inutiles au lieu de 1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion import (
    CalendrierScolaire,
    JoursFeries,
)


logger = logging.getLogger(__name__)


def _run_collector(collector_class) -> dict:
    """Instancie et lance un collecteur."""
    collector = collector_class()
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
    schedule="@monthly",  # 1x/mois
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "ingestion", "calendrier"],
) as dag:

    t_cal = PythonOperator(
        task_id="collect_calendrier_scolaire",
        python_callable=_run_collector,
        op_kwargs={"collector_class": CalendrierScolaire},
        execution_timeout=timedelta(minutes=5),
    )

    t_fer = PythonOperator(
        task_id="collect_jours_feries",
        python_callable=_run_collector,
        op_kwargs={"collector_class": JoursFeries},
        execution_timeout=timedelta(minutes=5),
    )
