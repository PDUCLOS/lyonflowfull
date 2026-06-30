"""DAG — Refresh des vues matérialisées gold LOURDES (Sprint 24, 2026-06-29).

Pourquoi ce DAG existe
----------------------
Découplage performance. Deux refresh gold sont coûteux sur le VPS (6 CPU,
12 Go RAM) :

* ``build_infrastructure_bottlenecks`` — JOIN global bus x trafic par heure
  sur ~4.4M lignes de gold.traffic_features_live (DELETE + INSERT complet).
* ``refresh_mv_bus_traffic_spatial`` — GROUP BY spatial 0.001° (~100 m) sur
  48 h de trafic (migration 036) x positions GPS TCL.
* ``purge_old_traffic_features`` (Sprint 24+) — DELETE WHERE
  ``computed_at < NOW() - retention_h`` (défaut 48 h, env var
  ``GOLD_TRAFFIC_FEATURES_RETENTION_HOURS``). Allège les scans gold
  downstream. Index requis : migration 037.

Avant Sprint 24, ces deux tasks vivaient dans ``transform_silver_to_gold``
(*/10 min, max_active_runs=1). Un refresh lourd de 15-30 min bloquait la tête
de file et empêchait le run */10 suivant de rafraîchir
``gold.traffic_features_live`` → la carte trafic tombait « stale > 10 min » et
``gold.mv_bus_traffic_spatial`` restait à 0 ligne.

En isolant les refresh lourds ici, à une cadence */30 alignée sur leur fenêtre
de données (48 h bougent très peu en 30 min), la fraîcheur du trafic temps réel
n'est plus l'otage des MV analytiques. Le refresh lui-même est rendu robuste
par ``_refresh_matview_safe`` (fallback CONCURRENTLY→plain + statement_timeout)
côté ``src/transformation/silver_to_gold.py``.

Consommateurs
-------------
* gold.mv_bus_traffic_spatial → widget Pro TCL ``bus_traffic_spatial.py`` +
  page Élu ``Elu_2`` (ROI bottlenecks, Sprint 22++).
* gold.infrastructure_bottlenecks → ``correlation_matrix.py`` /
  ``segment_table.py`` (fallback legacy, à terme remplacé par la MV spatiale).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.transformation.silver_to_gold import transform_silver_to_gold

logger = logging.getLogger(__name__)


def _run_bottleneck() -> dict[str, int]:
    return transform_silver_to_gold(target="bottleneck")


def _run_bus_traffic_spatial() -> dict[str, int]:
    return transform_silver_to_gold(target="bus_traffic_spatial")


def _run_purge_traffic() -> dict[str, int]:
    """Sprint 24+ — purge gold.traffic_features_live > N heures (défaut 48h).

    Opt-in : ``target='purge_traffic_features'`` n'est PAS dans ``'all'``
    (sécurité, cf. dispatch table dans ``silver_to_gold.py``).
    """
    return transform_silver_to_gold(target="purge_traffic_features")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="refresh_heavy_mv",
    description=(
        "Refresh des MV gold lourdes (bottlenecks + busxtrafic spatial) + "
        "purge gold.traffic_features_live — découplé du chemin critique */10 "
        "(Sprint 24 / 24+)"
    ),
    default_args=default_args,
    start_date=datetime(2026, 6, 29),
    schedule_interval="*/30 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["transform", "gold", "heavy"],
) as dag:
    # Diagnostic infra/operations/bus_lane_ok — JOIN global lourd.
    # Best-effort : un échec ne doit pas empêcher la MV spatiale de tourner.
    bottleneck = PythonOperator(
        task_id="build_infrastructure_bottlenecks",
        python_callable=_run_bottleneck,
        execution_timeout=timedelta(minutes=12),
        retries=0,
        trigger_rule="all_done",
    )

    # Corrélation bus x trafic spatialisée (zone ~100 m). Refresh robuste :
    # _refresh_matview_safe gère MV-vide → plain, sinon CONCURRENTLY, +
    # statement_timeout 10 min (coupe avant l'execution_timeout Airflow).
    bus_traffic_spatial = PythonOperator(
        task_id="refresh_mv_bus_traffic_spatial",
        python_callable=_run_bus_traffic_spatial,
        execution_timeout=timedelta(minutes=12),
        retries=1,
        retry_delay=timedelta(minutes=5),
        trigger_rule="all_done",
    )

    # Sprint 24+ (2026-06-29) — purge gold.traffic_features_live > N heures.
    # Best-effort : un échec ne doit pas bloquer la chaîne. Allège les scans
    # gold downstream (mv_multimodal_grid, mv_bus_traffic_spatial). Index sur
    # computed_at requis (migration 037) — DELETE < 1 s sur 1 M+ rows.
    purge = PythonOperator(
        task_id="purge_old_traffic_features",
        python_callable=_run_purge_traffic,
        execution_timeout=timedelta(minutes=5),
        retries=0,
        trigger_rule="all_done",
    )

    # Séquentiel (pas parallèle) : sur 12 Go RAM, deux GROUP BY lourds en même
    # temps risquent l'OOM-kill du worker. L'un après l'autre est plus sûr.
    # Sprint 24+ : la purge s'enchaîne APRÈS la MV spatiale (la MV vient
    # d'être snapshot — meilleur moment pour purger la source).
    bottleneck >> bus_traffic_spatial >> purge
