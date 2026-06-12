"""DAG Airflow — Construit le training set materialisé pour XGBoost H+1h.

Sprint 9+ (2026-06-12) — Remplace la query ``_load_training_data()`` de
``src/models/xgboost_speed.py`` qui faisait un ``LEAD() OVER (...)`` sur
2.4M rows de ``gold.traffic_features_live`` (11.5s en postgres direct,
timeout depuis Streamlit).

**Stratégie** :
1. Self-join indexé sur ``computed_at + INTERVAL '60 min'`` (utilise
   l'index existant ``idx_traffic_features_live_channel_computed``).
2. INSERT batch dans ``gold.xgb_training_set`` (idempotent via TRUNCATE).
3. Rétention 14 jours (auto-purge).

**Scheduling** : quotidien à 02h30 (avant le retrain H+1h qui tourne
``*/30min`` et qui lit cette table — voir ``dag_live_speed_retrain``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db import execute_query

logger = logging.getLogger(__name__)

DAG_ID = "build_xgb_training_set"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

# Retain 14 days of training data (sliding window)
RETENTION_DAYS = 14
# Lookback window for training set population (2 days — VPS-friendly)
# Sprint 9+ Optimisation : avec 2 jours on a ~700k rows, le self-join
# tourne en ~3 min au lieu de timeout sur 7 jours. Le XGBoost n'a
# pas besoin de plus : 2 jours x 1100 channels x 288 pas/5min = ~600k
# training samples, largement suffisant pour un modèle à 11 features.
LOOKBACK_DAYS = 2


def _build_training_set(**context) -> dict:
    """Populate gold.xgb_training_set via self-join H+1h.

    Self-join approach (Sprint 9+) : for each (channel_id, computed_at)
    in lookback window, find the row of the same channel exactly 60 min
    later (target_speed). Much faster than ``LEAD() OVER (...)`` because
    the join uses the existing index on (channel_id, computed_at).

    Idempotent : TRUNCATE + INSERT. The previous run's data is dropped
    before re-population. Safe because this is a derived table.
    """
    logger.info(
        "Building gold.xgb_training_set (lookback=%d days, retention=%d days)",
        LOOKBACK_DAYS,
        RETENTION_DAYS,
    )

    # Step 1 — Purge old data (>14 days)
    # Sprint 10+ fix : on passe RETENTION_DAYS en paramètre psycopg2 au
    # lieu de ``%d`` Python. Le `%d` est safe (int hardcodé) mais le
    # pattern f-string / ``%`` n'est pas homogène avec le reste du
    # codebase, qui privilégie les paramètres psycopg2 (cf. AGENTS.md).
    execute_query(
        "DELETE FROM gold.xgb_training_set "
        "WHERE created_at < NOW() - make_interval(days => %s)",
        (RETENTION_DAYS,),
    )
    logger.info("Purged training set rows older than %d days", RETENTION_DAYS)

    # Step 2 — TRUNCATE recent window
    execute_query("TRUNCATE TABLE gold.xgb_training_set RESTART IDENTITY")

    # Step 3 — Self-join populate via single query index-friendly
    # Stratégie Sprint 9+ Optimisation : CTE pré-filtrée (computed_at >
    # 2 jours, features non-NULL) + INNER JOIN sur l'index
    # ``idx_gold_traffic_channel_computed (channel_id, computed_at) INCLUDE
    # (speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3)``. Index Only Scan
    # 444k iterations en ~19s sur le VPS. Pas de boucle Python par
    # channel (qui faisait 9 min et timeout).
    insert_query = f"""
        INSERT INTO gold.xgb_training_set (
            computed_at, target_computed_at, channel_id, channel_hash,
            target_speed,
            speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3,
            sin_hour, cos_hour, temperature_2m, precipitation,
            is_vacances, is_ferie, lat, lon, importance_code
        )
        WITH feat AS (
            SELECT channel_id, channel_hash, computed_at, speed_kmh,
                   lag_1, lag_2, lag_3, rolling_mean_3,
                   sin_hour, cos_hour, temperature_2m, precipitation,
                   is_vacances, is_ferie, lat, lon, importance_code
            FROM gold.traffic_features_live
            WHERE computed_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
              AND speed_kmh IS NOT NULL
              AND lag_1 IS NOT NULL
              AND rolling_mean_3 IS NOT NULL
        ),
        tgt AS (
            SELECT channel_id, speed_kmh, computed_at
            FROM gold.traffic_features_live
            WHERE computed_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
              AND speed_kmh IS NOT NULL
        )
        SELECT
            feat.computed_at,
            tgt.computed_at AS target_computed_at,
            feat.channel_id,
            feat.channel_hash,
            tgt.speed_kmh AS target_speed,
            feat.speed_kmh,
            feat.lag_1,
            feat.lag_2,
            feat.lag_3,
            feat.rolling_mean_3,
            feat.sin_hour,
            feat.cos_hour,
            feat.temperature_2m,
            feat.precipitation,
            COALESCE(feat.is_vacances, FALSE),
            COALESCE(feat.is_ferie, FALSE),
            feat.lat,
            feat.lon,
            feat.importance_code
        FROM feat
        INNER JOIN tgt
            ON  tgt.channel_id  = feat.channel_id
            AND tgt.computed_at >= feat.computed_at + INTERVAL '60 minutes'
            AND tgt.computed_at <  feat.computed_at + INTERVAL '65 minutes'
    """
    execute_query(insert_query)
    logger.info(
        "Inserted training rows for last %d days (single-query, indexed self-join)",
        LOOKBACK_DAYS,
    )



    # Step 4 — Stats
    stats = execute_query("""
        SELECT
            COUNT(*) AS n_rows,
            COUNT(DISTINCT channel_id) AS n_channels,
            MIN(computed_at) AS min_t,
            MAX(computed_at) AS max_t,
            AVG(target_speed) AS mean_target,
            STDDEV(target_speed) AS std_target
        FROM gold.xgb_training_set
    """)
    stats_row = stats[0] if stats else {}
    logger.info("Training set stats: %s", stats_row)

    return {
        "n_rows": stats_row.get("n_rows", 0),
        "n_channels": stats_row.get("n_channels", 0),
        "min_t": str(stats_row.get("min_t")),
        "max_t": str(stats_row.get("max_t")),
        "mean_target": float(stats_row.get("mean_target") or 0),
        "std_target": float(stats_row.get("std_target") or 0),
    }


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Construit gold.xgb_training_set pour XGBoost H+1h (Sprint 9+)",
    schedule_interval="30 2 * * *",  # quotidien 02h30
    start_date=datetime(2026, 6, 12),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "training", "xgboost", "sprint9"],
) as dag:
    build = PythonOperator(
        task_id="build_xgb_training_set",
        python_callable=_build_training_set,
        provide_context=True,
    )
