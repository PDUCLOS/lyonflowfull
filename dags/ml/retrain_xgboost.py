"""DAG — Retrain ML models.

XGBoost Speed : hourly
XGBoost Velov : hourly (H+30min uniquement — Sprint 12+, Patrice : "tout en H+30min pour Vélov")

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
    """Entraîne le modèle XGBoost speed (H+1h uniquement — focus VPS).

    Sprint P2.1 (2026-06-14) — AUDIT_INTEGRATION_LIVE.md § 1.2.2.
    Avant : 4 horizons entraînés (5min, 1h, 3h, 6h) — 4x le coût
             compute et la RAM, pour rien : les widgets dashboard ne
             lisent que H+1h (cf. gold.trafic_predictions.horizon_h=1).
    Après : 1 horizon H+1h — aligné avec CLAUDE.md « focus H+1h » et
            avec le schéma gold (PK stocke horizon_h=1).

    Si un caller demande un autre horizon à ``predict()``, le modèle
    retourne son fallback (30.0 km/h) — déjà géré dans
    ``XGBoostSpeedModel.predict()``.

    Note : les anciens .pkl H+5min/H+3h/H+6h restent sur disque mais
    ne sont plus ré-entraînés. Pas de suppression forcée — Patrice peut
    purger ``/app/models/xgb_speed_h5.pkl`` etc. manuellement si besoin.
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    model = XGBoostSpeedModel()
    results = {}
    # 1 horizon uniquement (Sprint P2.1 — focus fiabilité VPS)
    for horizon in [60]:
        try:
            metrics = model.train_one(horizon_minutes=horizon)
            results[f"h{horizon}"] = metrics
        except Exception as e:
            logger.exception(f"Train H+{horizon}min failed: {e}")
    return results


def _train_xgboost_velov():
    """Entraîne le modèle XGBoost Velov (H+30min uniquement — focus réactivité).

    Sprint P2.1 (2026-06-14) — AUDIT_INTEGRATION_LIVE.md § 1.2.2.
    Avant : 2 horizons (30min, 1h) — gaspillage CPU/RAM sur VPS.
    Après : 1 horizon H+30min — aligné avec CLAUDE.md « Vélov = H+30min
            uniquement » (Patrice 2026-06-13 : « tout en H+30min pour Vélov »).
            Le modèle H+1h Vélov est supprimé du registry MLflow.
    """
    from src.models.xgboost_velov import XGBoostVelovModel

    model = XGBoostVelovModel()
    results = {}
    # 1 horizon uniquement (Sprint P2.1 — focus H+30min pour Vélov)
    for horizon in [30]:
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
# Sprint P2.1 (2026-06-14) — 1 horizon (H+1h) au lieu de 4 — focus fiabilité VPS.
with DAG(
    dag_id="retrain_xgboost_speed",
    description="Retrain XGBoost Speed hourly (1 horizon H+1h — focus VPS) — toggleable",
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
# Sprint P2.1 (2026-06-14) — 1 horizon (H+30min) au lieu de 2 — focus réactivité.
with DAG(
    dag_id="retrain_xgboost_velov",
    description="Retrain XGBoost Velov hourly (1 horizon H+30min — focus réactivité) — toggleable",
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
