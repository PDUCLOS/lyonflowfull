"""DAG — Collecte TomTom Traffic Flow (Sprint VPS-6, 2026-06-11).

Cycle : 15 min, 12 tuiles Lyon utiles (0.02 degres de cote, ~2 km).
Budget : 12 x 4 x 24 = 1152 req/jour (free tier 2500, marge 1348).

Ecrit dans ``bronze.tomtom_traffic``, agrege en ``gold.v_tomtom_traffic_live``.
Le dashboard lit via ``src.data.data_loader.load_traffic_combined_for_map()``.

Si ``TOMTOM_API_KEY`` absent, le DAG est en no-op + log warning. Le
fallback ``gold.v_traffic_combined`` sert la derniere valeur cachee
(DB) jusqu'a 24h.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion import tomtom_traffic as tt

logger = logging.getLogger(__name__)


def _collect_tomtom(**context) -> int:
    """Tâche : collect TomTom Flow sur 12 tuiles Lyon + persist bronze."""
    if not tt.get_api_key():
        logger.warning(
            "TOMTOM_API_KEY non configuré — DAG collect_tomtom_traffic no-op. "
            "Inscrivez-vous sur https://developer.tomtom.com/ (free tier) "
            "et ajoutez TOMTOM_API_KEY=... dans .env + .deploy.env."
        )
        return 0

    results = tt.collect_lyon_tiles()
    if not results:
        logger.info("TomTom: 0 résultats (quota épuisé ou API down)")
        return 0

    n_inserted = tt.save_lyon_tiles_to_bronze(results)
    logger.info(
        "TomTom: %d/%d tuiles insérées, health=%s",
        n_inserted, len(results), tt.health(),
    )
    return n_inserted


default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=5),
}

with DAG(
    dag_id="collect_tomtom_traffic",
    default_args=default_args,
    description="Collecte TomTom Traffic Flow toutes les 15 min (Sprint VPS-6)",
    schedule_interval="*/15 * * * *",  # toutes les 15 min
    start_date=datetime(2026, 6, 11),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "traffic", "tomtom", "sprint-vps-6"],
) as dag:
    PythonOperator(
        task_id="collect_tomtom_flow",
        python_callable=_collect_tomtom,
        provide_context=True,
    )
