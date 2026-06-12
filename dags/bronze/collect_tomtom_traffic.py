"""DAG — Collecte TomTom Traffic Flow (Sprint 8, 2026-06-12 — désactivé).

Sprint VPS-6 (2026-06-11) avait ajouté ce DAG, mais :
- Le module ``src.ingestion.tomtom_traffic`` n'a JAMAIS eu la classe
  ``TomTomTrafficFlow`` ni les fonctions ``collect_lyon_tiles()`` /
  ``save_lyon_tiles_to_bronze()`` / ``health()`` (juste des helpers
  cache/quota). Le DAG plantait à l'import (``ImportError``).
- TomTom est marqué "redondant avec boucles" dans CLAUDE.md (Sprint
  2). Les boucles Grand Lyon couvrent Lyon intra-muros.
- Sprint 8 a viré tous les mocks — la dette TomTom est ressortie.

Sprint 8 — Décision : on désactive ce DAG (no-op) en attendant un
refacto complet. Le DAG reste listé (pour traçabilité) mais ne fait
rien. Réactivation Sprint 12+ si besoin (cf. backlog).

Migration : le code TomTom reste dans ``src.ingestion.tomtom_traffic``
pour les widgets qui lisent ``bronze.tomtom_traffic`` (cf.
``data_loader.load_traffic_combined_for_map``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _collect_tomtom_disabled(**context) -> int:  # noqa: ARG001
    """Sprint 8 — No-op. Voir docstring du module."""
    logger.info(
        "DAG collect_tomtom_traffic DÉSACTIVÉ (Sprint 8 2026-06-12). "
        "Le module src.ingestion.tomtom_traffic n'a jamais eu de "
        "classe DataCollector conforme. Voir backlog Sprint 12+ "
        "pour réactivation éventuelle."
    )
    return 0


default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,
    "execution_timeout": timedelta(minutes=1),
}

with DAG(
    dag_id="collect_tomtom_traffic",
    default_args=default_args,
    description="[DÉSACTIVÉ Sprint 8] Collecte TomTom — no-op en attendant refacto",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2026, 6, 11),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "traffic", "tomtom", "disabled", "sprint-8"],
) as dag:
    PythonOperator(
        task_id="collect_tomtom_flow",
        python_callable=_collect_tomtom_disabled,
    )
