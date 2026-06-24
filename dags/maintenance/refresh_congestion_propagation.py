"""DAG — Refresh */30 min de gold.mv_congestion_propagation_pairs (Sprint 17, 2026-06-20).

Cycle : toutes les 30 min (cohérent avec le rythme des MVs lourdes —
la table des paires est spatialement stable, le refresh est rapide).

Tache :
1. REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_congestion_propagation_pairs

Notes :
* Sprint 17 Axe 2 — Propagation de congestion.
* La MV stocke les paires de capteurs adjacents (K=2 grid) avec
  lat/lon des 2 nœuds. PAS de CORR (calculée en Python par le widget).
* CONCURRENTLY necessite UNIQUE INDEX sur (node_a, node_b)
  (cree dans migration_024 v3).
* En cas d'echec CONCURRENTLY, fallback REFRESH standard.
* Schedule */30 min : la table des paires ne bouge que si le graphe
  GNN change (très rare). Le widget calcule les CORR à la volée depuis
  gold.traffic_features_live (rafraîchi toutes les 5 min côté
  transform_silver_to_gold), donc pas besoin d'un refresh plus rapide.
* Logs structures pour monitoring Prometheus.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _refresh_mv_congestion_propagation(**context) -> None:
    """Refresh gold.mv_congestion_propagation_pairs (Sprint 17 Axe 2, migration 024 v3)."""
    from src.db import execute_query

    try:
        # CONCURRENTLY evite les locks en lecture. Necessite UNIQUE INDEX
        # sur (node_a, node_b) (cree dans migration_024 v3).
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_congestion_propagation_pairs")
        logger.info("gold.mv_congestion_propagation_pairs refreshed OK (CONCURRENTLY)")
    except Exception as e:
        # Si CONCURRENTLY echoue (1er run sans index unique, lock
        # concurrent, etc.), on retombe sur un REFRESH standard.
        logger.warning("CONCURRENTLY refresh failed, fallback standard: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_congestion_propagation_pairs")
        logger.info("gold.mv_congestion_propagation_pairs refreshed OK (fallback standard)")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="refresh_congestion_propagation",
    description=(
        "Sprint 17 Axe 2 — REFRESH */30 min gold.mv_congestion_propagation_pairs "
        "(propagation congestion, K=2 grid pairs, migration 024 v3)"
    ),
    default_args=default_args,
    schedule_interval="*/30 * * * *",  # toutes les 30 min
    start_date=datetime(2026, 6, 20),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "gold", "sprint17", "axe2"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_mv_congestion_propagation_pairs",
        python_callable=_refresh_mv_congestion_propagation,
        execution_timeout=timedelta(minutes=5),
    )
