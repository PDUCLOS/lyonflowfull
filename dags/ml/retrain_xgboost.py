"""DAG — Retrain ML models.

XGBoost Speed : hourly
XGBoost Velov : hourly (2 horizons : H+30min, H+1h)

Sprint 8 — Toggle ``LYONFLOW_XGBOOST_TRAINING`` permet de désactiver
le retrain nightly (par exemple quand le GNN a pris le relais en prod).
Quand Patrice valide le GNN :
1. Set ``LYONFLOW_MODELS_ACTIVE=stgcn``
2. Set ``LYONFLOW_XGBOOST_TRAINING=false``
3. Le DAG skip automatiquement (ce task_id log "skipped" + return 0)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _is_xgboost_dag_enabled() -> bool:
    """Vérifie le toggle LYONFLOW_XGBOOST_TRAINING + LYONFLOW_MODELS_ACTIVE."""
    try:
        from src.ml.model_registry import (
            is_xgboost_enabled,
            is_xgboost_training_enabled,
        )
    except ImportError:
        return True  # fallback : on n'a pas le registry, on tourne

    if not is_xgboost_training_enabled():
        logger.info("LYONFLOW_XGBOOST_TRAINING=False — DAG skip")
        return False
    if not is_xgboost_enabled():
        logger.info("XGBoost pas dans LYONFLOW_MODELS_ACTIVE — DAG skip")
        return False
    return True


def _train_xgnoop_skip() -> dict:
    """No-op task qui log que le DAG est désactivé."""
    return {"skipped": "XGBoost DAG disabled by feature flag"}


def _train_xgboost_speed_wrapped() -> dict:
    """Wrapper qui vérifie le toggle avant d'appeler la vraie fonction."""
    if not _is_xgboost_dag_enabled():
        return _train_xgnoop_skip()
    return _train_xgboost_speed()


def _train_xgboost_velov_wrapped() -> dict:
    """Wrapper qui vérifie le toggle avant d'appeler la vraie fonction."""
    if not _is_xgboost_dag_enabled():
        return _train_xgnoop_skip()
    return _train_xgboost_velov()


def _train_xgboost_speed():
    """Entraîne les 4 horizons XGBoost speed (5min, 1h, 3h, 6h)."""
    from src.models.xgboost_speed import XGBoostSpeedModel

    model = XGBoostSpeedModel()
    results = {}
    for horizon in [5, 60, 180, 360]:
        try:
            metrics = model.train_one(horizon_minutes=horizon)
            results[f"h{horizon}"] = metrics
        except Exception as e:
            logger.exception(f"Train H+{horizon}min failed: {e}")
    return results


def _train_xgboost_velov():
    """Entraîne les 2 horizons XGBoost Velov (30min, 1h)."""
    from src.models.xgboost_velov import XGBoostVelovModel

    model = XGBoostVelovModel()
    results = {}
    # 2 horizons uniquement (CLAUDE.md : "2 horizons, économe")
    for horizon in [30, 60]:
        try:
            metrics = model.train_one(horizon_minutes=horizon)
            results[f"h{horizon}"] = metrics
        except Exception as e:
            logger.exception(f"Train Velov H+{horizon}min failed: {e}")
    return results


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# DAG 1: retrain_xgboost_speed (hourly :25 — match CLAUDE.md)
with DAG(
    dag_id="retrain_xgboost_speed",
    description="Retrain XGBoost Speed hourly (4 horizons : 5min, 1h, 3h, 6h) — toggleable",
    default_args=default_args,
    schedule="25 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "xgboost", "traffic"],
) as dag_speed:
    PythonOperator(
        task_id="train_xgboost_speed",
        python_callable=_train_xgboost_speed_wrapped,
        execution_timeout=timedelta(minutes=15),
    )

# DAG 2: retrain_xgboost_velov (hourly :50 — match CLAUDE.md)
with DAG(
    dag_id="retrain_xgboost_velov",
    description="Retrain XGBoost Velov hourly (2 horizons : 30min, 1h) — toggleable",
    default_args=default_args,
    schedule="50 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "xgboost", "velov"],
) as dag_velov:
    PythonOperator(
        task_id="train_xgboost_velov",
        python_callable=_train_xgboost_velov_wrapped,
        execution_timeout=timedelta(minutes=15),
    )
