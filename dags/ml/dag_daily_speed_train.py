"""DAG — Entraînement quotidien XGBoost Speed (1x/jour à 03h00).

 Optimisation (2026-06-12) — L'entraînement était exécuté toutes
les 30 min dans ``dag_live_speed_retrain`` (47 fois/jour) pour rien car
les données ne changent qu'une fois par jour. On sépare maintenant
training/ inference :

- **dag_daily_speed_train (CE DAG)** : 1x/jour à 03h00, lourd (~5-10 min)
  - charge ``gold.xgb_training_set`` (populé par ``build_xgb_training_set`` 02h30)
  - entraîne le modèle XGBoost H+1h
  - sauvegarde sur disque ET dans MLflow Registry (Production)
- **dag_inference_xgboost** : 1x/15min, léger (<1 min)
  - charge le modèle pré-entraîné (1 fois)
  - prédit + INSERT dans ``gold.trafic_predictions``
  - pas de fit(), pas de re-training

**Avantage VPS** : on peut réduire la RAM du worker Airflow de 9 Go à
6 Go (cf. docker-compose.yml) car l'entraînement, maintenant isolé et
nocturne, n'entre pas en compétition avec l'inférence temps réel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

DAG_ID = "dag_daily_speed_train"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(hours=1),
}


def _train_xgboost_speed_h1h() -> dict:
    """Entraîne le modèle XGBoost H+1h sur gold.xgb_training_set.

    Lit la table materialisée (cf. build_xgb_training_set), entraîne
    un XGBRegressor avec hyperparamètres standards, sauvegarde sur
    disque (LYONFLOW_MODELS_DIR) et log dans MLflow Registry.

    Returns:
        Dict {"mae", "rmse", "r2", "n_train", "n_test", "model_path"}.
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    logger.info("=== Training XGBoost H+1h (1x/jour) ===")

    # 1) Charge modèle + données
    model = XGBoostSpeedModel()
    df = model._load_training_data(horizon_minutes=60)

    if df.empty:
        raise RuntimeError(
            "gold.xgb_training_set est vide. Le DAG 'build_xgb_training_set' "
            "doit tourner en amont pour matérialiser le training set."
        )

    logger.info("Loaded %d training rows from gold.xgb_training_set", len(df))

    # 2) Train
    metrics = model.train_one(horizon_minutes=60, df=df)

    # 3) Récupère le path du modèle sauvegardé
    model_path = model.model_dir / "xgb_speed_h60.pkl"

    logger.info(
        "Training H+1h DONE: MAE=%.2f RMSE=%.2f R²=%.3f (saved to %s)",
        metrics["mae"],
        metrics["rmse"],
        metrics["r2"],
        model_path,
    )

    return {
        **metrics,
        "n_train": int(len(df) * 0.8),
        "n_test": int(len(df) * 0.2),
        "model_path": str(model_path),
    }


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
  description="Entraînement quotidien XGBoost H+1h Optimisation)",
    schedule_interval="0 3 * * *",  # 03h00 tous les jours
    start_date=datetime(2026, 6, 12),
    catchup=False,
    max_active_runs=1,
  tags=["ml", "training", "xgboost", "daily", "sprint9"],
) as dag:
    train = PythonOperator(
        task_id="train_xgboost_speed_h1h",
        python_callable=_train_xgboost_speed_h1h,
        execution_timeout=timedelta(minutes=30),
    )
