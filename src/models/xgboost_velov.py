"""XGBoost Velov Model — prédiction disponibilité Vélov.

Features : station_id_encoded, temporel, météo, lags, rolling

Sprint 9 — Chaque train log dans MLflow via src.ml.mlflow_integration.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from src.db import execute_query

logger = logging.getLogger(__name__)


FEATURE_COLS = [
    "station_id_encoded",
    "bikes_lag_1",
    "bikes_lag_2",
    "bikes_lag_3",
    "rolling_mean_3h",
    "hour_sin",
    "hour_cos",
    "temperature_c",
    "rain_mm",
    "is_vacances",
    "is_ferie",
]


class XGBoostVelovModel:
    """Modèle XGBoost pour prédire le nombre de vélos disponibles."""

    def __init__(self, model_dir: str | None = None):
        # Double `or` pour que mypy comprenne que le résultat est toujours str.
        resolved_dir = model_dir or os.getenv("LYONFLOW_MODELS_DIR") or "/app/models"
        self.model_dir = Path(resolved_dir)
        self.models: dict[int, xgb.Booster] = {}

    def load(self, horizons: list[int] | None = None) -> None:
        """Charge les modèles depuis MLflow (si dispo) ou depuis le disque local."""
        import mlflow

        from src.ml.mlflow_integration import is_mlflow_available

        horizons = horizons or [30, 60]
        for h in horizons:
            model_name = f"xgb_velov_h{h}"
            model_path = self.model_dir / f"{model_name}.pkl"

            mlflow_success = False
            if is_mlflow_available():
                try:
                    artifact_uri = f"models:/{model_name}/Production"
                    local_path = mlflow.artifacts.download_artifacts(artifact_uri, dst_path=str(self.model_dir))
                    self.models[h] = joblib.load(local_path)
                    logger.info(f"Loaded XGBoost Velov horizon {h}min from MLflow Registry (Production)")
                    mlflow_success = True
                except Exception as e:
                    logger.warning(f"Failed to load {model_name} from MLflow Registry: {e}")

            if not mlflow_success:
                if model_path.exists():
                    self.models[h] = joblib.load(model_path)
                    logger.info(f"Loaded XGBoost Velov horizon {h}min from local disk")
                else:
                    logger.warning(f"Model not found: {model_path}")

    def train_one(self, horizon_minutes: int, df: pd.DataFrame | None = None) -> dict:
        """Entraîne pour un horizon donné."""
        if df is None:
            df = self._load_training_data(horizon_minutes)

        if df.empty:
            raise ValueError(f"Pas de données d'entraînement Velov H+{horizon_minutes}min")

        split_idx = int(len(df) * 0.8)
        train = df.iloc[:split_idx]
        test = df.iloc[split_idx:]

        X_train = train[FEATURE_COLS]
        y_train = train["target_bikes"]
        X_test = test[FEATURE_COLS]
        y_test = test["target_bikes"]

        model = xgb.XGBRegressor(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.1,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        y_pred = model.predict(X_test)
        metrics = {
            "mae": float(np.mean(np.abs(y_test - y_pred))),
            "rmse": float(np.sqrt(np.mean((y_test - y_pred) ** 2))),
        }

        self.models[horizon_minutes] = model
        model_path = self.model_dir / f"xgb_velov_h{horizon_minutes}.pkl"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_path)

        # MLflow tracking (Sprint 9 — opt-out via MLFLOW_TRACKING_URI="")
        if os.getenv("MLFLOW_TRACKING_URI", "") != "":
            try:
                from src.ml.mlflow_integration import MLflowTracker

                tracker = MLflowTracker(experiment_name="xgboost_velov")
                run_name = f"xgb_velov_h{horizon_minutes}_{int(time.time())}"
                with tracker.start_run(run_name=run_name) as _run:
                    tracker.set_tag("model", "xgboost_velov")
                    tracker.set_tag("horizon_min", str(horizon_minutes))
                    tracker.log_params(
                        {
                            "horizon_min": horizon_minutes,
                            "n_estimators": 150,
                            "max_depth": 5,
                            "learning_rate": 0.1,
                            "n_samples": len(df),
                            "n_features": len(FEATURE_COLS),
                            "model_version": "1.0.0",
                        }
                    )
                    tracker.log_metrics(metrics)
                    tracker.log_artifact(str(model_path))
                    # Register & transition to Production natively
                    reg_model_name = f"xgb_velov_h{horizon_minutes}"
                    tracker.register_model(reg_model_name)
                    tracker.transition_to_production(reg_model_name)
            except Exception as e:  # pragma: no cover
                logger.warning("MLflow tracking failed (non-bloquant): %s", e)

        logger.info(f"XGBoost Velov H+{horizon_minutes}min: MAE={metrics['mae']:.2f}")
        return metrics

    def predict(self, station_id: str, horizon_minutes: int) -> dict:
        """Prédit le nombre de vélos pour une station."""
        if horizon_minutes not in self.models:
            self.load()
        if horizon_minutes not in self.models:
            return {"predicted_bikes": 0.0, "model_name": "fallback"}

        features = self._lookup_features(station_id)
        if not features:
            return {"predicted_bikes": 0.0, "model_name": "fallback"}

        X = pd.DataFrame([features])[FEATURE_COLS]
        model = self.models[horizon_minutes]
        pred = float(np.clip(model.predict(X)[0], 0, 50))
        return {
            "predicted_bikes": round(pred, 1),
            "model_name": "xgb_velov",
            "model_version": "1.0.0",
        }

    def _load_training_data(self, horizon_minutes: int) -> pd.DataFrame:
        query = """
            SELECT
                station_id_encoded,
                bikes_lag_1, bikes_lag_2, bikes_lag_3,
                rolling_mean_3h,
                hour_sin, hour_cos,
                temperature_c, rain_mm,
                COALESCE(is_vacances, FALSE) AS is_vacances,
                COALESCE(is_ferie, FALSE) AS is_ferie,
                bikes_available AS target_bikes
            FROM gold.velov_features
            WHERE bikes_available IS NOT NULL
              AND measurement_time > NOW() - INTERVAL '14 days'
            ORDER BY measurement_time
        """
        rows = execute_query(query, ())
        return pd.DataFrame(rows)

    def _lookup_features(self, station_id: str) -> dict:
        query = """
            SELECT
                station_id_encoded,
                bikes_lag_1, bikes_lag_2, bikes_lag_3,
                rolling_mean_3h,
                hour_sin, hour_cos,
                temperature_c, rain_mm,
                COALESCE(is_vacances, FALSE) AS is_vacances,
                COALESCE(is_ferie, FALSE) AS is_ferie
            FROM gold.velov_features
            WHERE station_id = %s
            ORDER BY measurement_time DESC LIMIT 1
        """
        rows = execute_query(query, (station_id,))
        if not rows:
            return {}
        return dict(rows[0])
