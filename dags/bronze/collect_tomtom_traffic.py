"""DAG — Collecte TomTom Traffic Flow , 2026-06-18 — RÉACTIVÉ).

 (2026-06-12) avait désactivé ce DAG en no-op parce que le module
``src.ingestion.tomtom_traffic`` n'avait pas de classe ``DataCollector``
conforme (juste helpers cache/quota).

 (2026-06-18) — Réactivation :
* Nouvelle classe ``TomTomTrafficFlow(DataCollector)`` dans
  ``src.ingestion/tomtom_traffic.py`` (câblée dans REALTIME_COLLECTORS).
* Ce DAG utilise maintenant le pattern unifié : ``TomTomTrafficFlow().run()``
  appelle ``collect_lyon_tiles()`` + ``save_lyon_tiles_to_bronze()``.
* Vue SQL ``gold.v_coherence_tomtom_vs_grandlyon`` (migration 14) fait
  le JOIN spatial TomTom ↔ boucle la plus proche (< 200m) pour la
  cross-validation et la détection de capteurs HS.

Quotas :
* Free tier TomTom = 2500 req/jour. Ce DAG = 12 tuiles x 96 cycles/jour
  = 1152 req/jour. Marge confortable.
* retries=0 (politique le cycle suivant rattrape).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _collect_tomtom_flow(**context) -> int:
    """Collecte TomTom Flow + persistance Bronze (pattern DataCollector.run).

    Returns:
        Nombre de lignes insérées dans bronze.tomtom_traffic.

    Raises:
        Exception: si la classe TomTomTrafficFlow échoue (DB indispo,
            HTTP fail définitif, etc.). Le cycle suivant rattrapera.
    """
    from src.ingestion.tomtom_traffic import TomTomTrafficFlow

    collector = TomTomTrafficFlow()
    result = collector.run()

    if result.error:
        logger.error(
            "TomTomTrafficFlow a échoué : %s. Le prochain cycle rattrapera.",
            result.error,
        )
        raise RuntimeError(f"TomTomTrafficFlow failed: {result.error}")

    n = result.n_records
    logger.info(
        "TomTomTrafficFlow OK : %d tuiles, %d ms, last_success_at=%s",
        n,
        result.duration_ms,
        collector.last_success_at,
    )
    # Pousse le count dans XCom pour le monitoring downstream
    context["ti"].xcom_push(key="n_records", value=n)
    return n


def _log_health(**context) -> None:
    """Push health() dans XCom pour Grafana / monitoring."""
    from src.ingestion.tomtom_traffic import health

    h = health()
    logger.info("TomTom health: %s", h)
    context["ti"].xcom_push(key="health", value=h)


default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,  # Politique le cycle suivant rattrape
    "execution_timeout": timedelta(minutes=2),
}

with DAG(
    dag_id="collect_tomtom_traffic",
    default_args=default_args,
    description="Collecte TomTom Traffic Flow — 12 tuiles Lyon toutes les 15 min",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2026, 6, 18),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "traffic", "tomtom", "sprint-13+"],
) as dag:
    collect = PythonOperator(
        task_id="collect_tomtom_flow",
        python_callable=_collect_tomtom_flow,
    )

    health_check = PythonOperator(
        task_id="tomtom_health",
        python_callable=_log_health,
    )

    collect >> health_check
