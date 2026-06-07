"""DAG — Collecte Bronze temps réel (5 min).

Lance les 6 collecteurs temps-réel en parallèle. Les collecteurs de
calendriers (vacances scolaires, jours fériés) sont dans un DAG mensuel séparé
(collect_calendriers_monthly.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion import (
    TraficGrandLyon,
    VelovCollector,
    MeteoOpenMeteo,
    AirQualityOpenMeteo,
    ChantiersGrandLyon,
    TclSiriLite,
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


def on_failure(context):
    """Callback d'erreur — log + webhook."""
    logger.error(f"Task failed: {context['task_instance'].task_id}")


default_args = {
    "owner": "lyonflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": on_failure,
}

with DAG(
    dag_id="collect_bronze",
    description="Collecte Bronze toutes les 5 min (8 sources parallèles)",
    default_args=default_args,
    schedule_interval="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "ingestion"],
) as dag:

    # 8 collecteurs en parallèle
    t_trafic = PythonOperator(
        task_id="collect_trafic_grandlyon",
        python_callable=_run_collector,
        op_kwargs={"collector_class": TraficGrandLyon},
        execution_timeout=timedelta(minutes=2),
    )

    t_velov = PythonOperator(
        task_id="collect_velov",
        python_callable=_run_collector,
        op_kwargs={"collector_class": VelovCollector},
        execution_timeout=timedelta(minutes=2),
    )

    t_meteo = PythonOperator(
        task_id="collect_meteo",
        python_callable=_run_collector,
        op_kwargs={"collector_class": MeteoOpenMeteo},
        execution_timeout=timedelta(minutes=2),
    )

    t_aq = PythonOperator(
        task_id="collect_air_quality",
        python_callable=_run_collector,
        op_kwargs={"collector_class": AirQualityOpenMeteo},
        execution_timeout=timedelta(minutes=2),
    )

    t_chantiers = PythonOperator(
        task_id="collect_chantiers",
        python_callable=_run_collector,
        op_kwargs={"collector_class": ChantiersGrandLyon},
        execution_timeout=timedelta(minutes=2),
    )

    t_tcl = PythonOperator(
        task_id="collect_tcl_siri_lite",
        python_callable=_run_collector,
        op_kwargs={"collector_class": TclSiriLite},
        execution_timeout=timedelta(minutes=2),
    )

    # Note : CalendrierScolaire et JoursFeries sont maintenant dans
    # collect_calendriers_monthly.py (DAG mensuel séparé)
