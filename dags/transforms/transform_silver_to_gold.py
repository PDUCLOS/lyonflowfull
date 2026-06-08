"""DAG — Transform Silver → Gold toutes les 10 min.

⚠️  STATUT 2026-06-08 : DÉSACTIVÉ (toutes les tasks en no-op)

Ce DAG visait à construire 3 tables gold (traffic_features_live,
velov_features, bus_delay_segments) via SQL set-based (psycopg2).

PROBLÈMES CONSTATÉS en prod :
1. Le schéma gold visé (measurement_time, node_idx, speed_lag_1/2/3) n'est
   PAS celui de la prod. La prod a un schéma legacy différent
   (fetched_at, id, lag_1/2/3) alimenté par dags/legacy_github/dag_pipeline.py.
2. Les sources silver.velov_clean et silver.tcl_vehicles_clean n'existent
   PAS en prod. Aucun DAG ne les alimente (collect_bronze ne fait que
   trafic_boucles + meteo + air_quality + chantiers).
3. Le legacy_github DAG fait DÉJÀ le travail pour le trafic via
   `materialize_gold_layer` et `stgcn_predict_on_ray` (gold.traffic_features_live
   + gold.fact_traffic_series + gold.trafic_predictions).

CONCLUSION : ce code est du **dead code** qui ne peut pas fonctionner en l'état.
Il faudrait soit :
- Le réécrire pour matcher le schéma prod + ajouter les sources silver manquantes
- Le supprimer et garder uniquement le legacy_github (plus simple, déjà opérationnel)

Pour l'instant, les tasks sont des no-op pour que le scheduler ne log pas
des erreurs, mais le DAG reste schedulé pour qu'on n'oublie pas.

Voir SPRINT_7_REPORT.md section "DAGs alternatifs" pour le contexte.
Voir aussi l'issue #TODO : "Refonte transform_silver_to_gold".
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _noop_traffic() -> dict[str, int]:
    logger.info("[NOOP] build_traffic_features: see DAG docstring")
    return {"traffic": 0}


def _noop_velov() -> dict[str, int]:
    logger.info("[NOOP] build_velov_features: see DAG docstring")
    return {"velov": 0}


def _noop_bus_delay() -> dict[str, int]:
    logger.info("[NOOP] build_bus_delay_segments: see DAG docstring")
    return {"bus_delay": 0}


default_args = {
    "owner": "lyonflow",
    "retries": 0,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="transform_silver_to_gold",
    description="[NOOP depuis 2026-06-08] Silver → Gold — voir docstring",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused=True,  # désactivé par défaut — ne pas réactiver sans refonte
    tags=["transform", "gold", "deprecated"],
) as dag:
    PythonOperator(
        task_id="build_traffic_features",
        python_callable=_noop_traffic,
        execution_timeout=timedelta(minutes=1),
    )

    PythonOperator(
        task_id="build_velov_features",
        python_callable=_noop_velov,
        execution_timeout=timedelta(minutes=1),
    )

    PythonOperator(
        task_id="build_bus_delay_segments",
        python_callable=_noop_bus_delay,
        execution_timeout=timedelta(minutes=1),
    )
