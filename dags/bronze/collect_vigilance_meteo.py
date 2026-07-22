"""DAG — Collecte vigilance météo canicule (2026-07-05).

Ingère le niveau de vigilance officiel "canicule" du département du Rhône
(69) via l'API publique Opendatasoft (gratuite, sans clé). Alimente
``bronze.vigilance_meteo``, lue par la vue ``gold.v_velov_safety_advisory``
(conseil sécurité Vélov : pollution/canicule, cf. migration_045).

Les bulletins officiels sont mis à jour 2x/jour (6h/16h) — une fréquence
de 6h suffit pour un warning dashboard sans sur-solliciter l'API publique.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _collect_vigilance_meteo(**context) -> int:
    """Collecte vigilance canicule + persistance Bronze (pattern DataCollector.run).

    Returns:
        Nombre de lignes (périodes horaires) insérées dans bronze.vigilance_meteo.

    Raises:
        Exception: si la classe VigilanceMeteo échoue (DB indispo, HTTP fail
            définitif, etc.). Le cycle suivant (6h après) rattrapera.
    """
    from src.ingestion.vigilance_meteo import VigilanceMeteo

    collector = VigilanceMeteo()
    result = collector.run()

    if result.error:
        logger.error(
            "VigilanceMeteo a échoué : %s. Le prochain cycle rattrapera.",
            result.error,
        )
        raise RuntimeError(f"VigilanceMeteo failed: {result.error}")

    n = result.n_records
    logger.info(
        "VigilanceMeteo OK : %d enregistrements, %d ms, last_success_at=%s",
        n,
        result.duration_ms,
        collector.last_success_at,
    )
    context["ti"].xcom_push(key="n_records", value=n)
    return n


default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,  # Politique le cycle suivant rattrape
    "execution_timeout": timedelta(minutes=1),
}

with DAG(
    dag_id="collect_vigilance_meteo",
    default_args=default_args,
    description="Collecte vigilance météo canicule (département 69 Rhône) toutes les 6h",
    schedule_interval="0 */6 * * *",
    start_date=datetime(2026, 7, 5),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "meteo", "vigilance", "safety", "2026-07-05"],
) as dag:
    collect = PythonOperator(
        task_id="collect_vigilance_meteo",
        python_callable=_collect_vigilance_meteo,
    )
