"""DAG — Retrain ML models.

XGBoost Speed : hourly, **PAUSED 2026-07-01** — redondant avec
``dag_daily_speed_train`` (1x/jour 03h) qui lit la même table
``gold.xgb_training_set`` matérialisée quotidiennement. Un retrain hourly sur
une source qui ne change qu'1x/jour produit des runs MLflow bit-identiques
(vérifié : mêmes métriques à 12 décimales sur 24 runs consécutifs).
XGBoost Velov : hourly, H+1h uniquement (focus H+1h strict, cf. Sprint VPS-6 —
H+30min n'est plus entraîné).

Toggle ``LYONFLOW_XGBOOST_TRAINING`` (+ ``LYONFLOW_MODELS_ACTIVE``) permet
de désactiver le retrain nightly. Si désactivé, le DAG skip automatiquement
(ce task_id log "skipped" + return 0).
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
    """Entraîne H+1h XGBoost speed uniquement (— H+1h strict).

    Avant : 4 horizons (5min, 1h, 3h, 6h) — en contradiction avec la
    règle projet focus H+1h strict (Sprint VPS-6). Le DAG
    ``dag_daily_speed_train`` (1x/jour 03h) le remplace fonctionnellement
    pour H+1h.

    Action : on garde SEUL H+1h ici pour ne pas perdre
    silencieusement des runs historiques (dead data → models jamais
    chargés → fail loud au predict). Toggle ``LYONFLOW_XGBOOST_TRAINING``
    permet de désactiver complètement ce DAG.
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    model = XGBoostSpeedModel()
    # Sprint 26+ (2026-09-08) — try/except silencieux datait de l'époque
    # multi-horizons (4 horizons, un échec ne devait pas tuer les 3 autres).
    # Avec un seul horizon restant (H+1h strict), il ne servait qu'à avaler
    # les erreurs : la task Airflow finissait SUCCESS même si le training
    # avait planté (constaté — connexion DB coupée pendant l'entraînement,
    # xgb_velov_h60 resté bloqué 15 jours sans que le DAG ne l'affiche nulle
    # part). Laisser l'exception remonter : Airflow marque FAILED, le
    # monitoring de taux d'échec (dag-failure-rate-monitor.sh) le détecte.
    horizon = 60
    metrics = model.train_one(horizon_minutes=horizon)
    return {f"h{horizon}": metrics}


def _train_xgboost_velov():
    """Entraîne H+1h XGBoost Velov uniquement (— H+1h strict)."""
    from src.models.xgboost_velov import XGBoostVelovModel

    model = XGBoostVelovModel()
    # Sprint 26+ (2026-09-08) — cf. commentaire _train_xgboost_speed() :
    # même try/except silencieux retiré, même raison (xgb_velov_h60 bloqué
    # 15 jours en MLflow malgré un DAG systématiquement SUCCESS).
    horizon = 60
    metrics = model.train_one(horizon_minutes=horizon)
    return {f"h{horizon}": metrics}


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# DAG 1: retrain_xgboost_speed (hourly :25 — match CLAUDE.md)
with DAG(
    dag_id="retrain_xgboost_speed",
    description="PAUSED 2026-07-01 (redondant avec dag_daily_speed_train) — Retrain XGBoost Speed H+1h hourly, toggleable",
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
    description="Retrain XGBoost Velov H+1h hourly (focus H+1h strict) — toggleable",
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
