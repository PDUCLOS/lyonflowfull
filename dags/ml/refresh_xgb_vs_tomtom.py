"""DAG Airflow — Refresh materialized view gold.mv_xgb_vs_tomtom.

 Axe A (2026-06-20) — Backtest Engine XGBoost H+1h.
Re-calcul la MV ``gold.mv_xgb_vs_tomtom`` toutes les 30 min pour fournir
les paires (XGBoost H+1h, vitesse observée) au widget Pro_7_Model_Monitoring,
aux pages Usager « Notre modèle » / « Statut » et au détecteur de drift Evidently.

Migration 051 (2026-09-28) : la référence n'est plus TomTom (clé rejetée,
collecte mise de côté) mais la vitesse Grand Lyon observée à H+1h
(``gold.traffic_features_live``). Nom de MV historique conservé.

Schedule : ``*/30 * * * *`` (toutes les 30 min, aligné cycle d'inférence
XGBoost H+1h).

Stratégie : ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` (pas de lock
exclusif sur la table pendant le refresh). Nécessite un index UNIQUE
pré-existant — on a créé 3 index (calculated_at, accuracy_band, axis_key)
dans la migration 020. CONCURRENTLY n'utilise pas l'index, juste
l'unicité ; si la MV n'a pas d'index UNIQUE, le refresh tombe en mode
non-concurrent (lock). On accepte ce fallback.

Voir ``docs/SPEC_SPRINT_16.md`` §A.1, §A.7.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db.connection import execute_query

logger = logging.getLogger(__name__)

DAG_ID = "refresh_xgb_vs_tomtom"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _refresh_mv(**context) -> dict:
    """REFRESH MATERIALIZED VIEW gold.mv_xgb_vs_tomtom.

    Returns:
        Dict avec ``mv_name``, ``n_pairs`` (count après refresh), ``duration_s``.
    """
    import time

    start = time.monotonic()
    # CONCURRENTLY : pas de lock lecteurs pendant le refresh (~20 s sur 7 j).
    # Possible depuis la migration 051 (index UNIQUE axis_key, calculated_at).
    # Fallback non-concurrent si l'index manque (base pas encore migrée).
    try:
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_xgb_vs_tomtom")
    except Exception as e:
        logger.warning("REFRESH CONCURRENTLY failed, retry sans CONCURRENTLY: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_xgb_vs_tomtom")
    duration = time.monotonic() - start

    # Count post-refresh pour télémétrie
    rows = execute_query("SELECT COUNT(*) AS n FROM gold.mv_xgb_vs_tomtom")
    n_pairs = int(rows[0]["n"]) if rows else 0
    logger.info(
        "MV gold.mv_xgb_vs_tomtom refreshed in %.2fs, %d paires",
        duration,
        n_pairs,
    )
    return {"mv_name": "gold.mv_xgb_vs_tomtom", "n_pairs": n_pairs, "duration_s": round(duration, 2)}


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description=("Sprint 16 Axe A — Refresh MV gold.mv_xgb_vs_tomtom (backtest XGBoost vs TomTom)"),
    # Décalé 5,35 (au lieu de */30 pile) — évite le thundering herd :00/:30
    # (cf. docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md item C1).
    schedule_interval="5,35 * * * *",
    start_date=datetime(2026, 6, 20),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "backtest", "tomtom", "sprint16"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_mv_xgb_vs_tomtom",
        python_callable=_refresh_mv,
        execution_timeout=timedelta(minutes=5),
    )
