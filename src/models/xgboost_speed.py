"""XGBoost Speed Model — prédiction vitesse trafic.

Multi-horizon : H+5min, H+1h, H+3h, H+6h
Features : speed (current + lags), temporel (sin/cos), météo, is_vacances, is_ferie

IMPORTANT : target = speed au temps t + horizon, pas t.
On utilise LEAD() window function (données échantillonnées toutes les 5 min).

Sprint 9 — Chaque train log dans MLflow (params + metrics + artifact)
via src.ml.mlflow_integration. Le tracking est opt-out via la variable
d'env ``MLFLOW_TRACKING_URI=""``.
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
from src.ml.mlflow_integration import MLflowTracker

logger = logging.getLogger(__name__)


# Features utilisées (Sprint 9 — alignées sur schéma v0.3.1 de gold.traffic_features_live,
# focus H+1h depuis Sprint VPS-6 2026-06-11).
# Convention de nommage : `lag_h1` = valeur il y a 1h, `lag_h2` = 2h, `lag_h3` = 3h.
# `delta_h1` = speed - lag_h1 (variation sur 1h).
# `rolling_mean_h1` = moyenne sur les 3 derniers pas de 5 min (= 15 min de contexte ~ 1h).
# Avant : speed_lag_1/2/3, speed_delta_1, rolling_mean_5min, hour_sin/cos, day_sin/cos,
#         temperature_c, rain_mm, node_idx
# Après : lag_h1/h2/h3, delta_h1, rolling_mean_h1, sin_hour/cos_hour, sin_dow/cos_dow,
#         temperature_2m, precipitation, channel_id (string LYO000xx, pas int node_idx)
FEATURE_COLS = [
    "speed_kmh",
    "lag_h1",
    "lag_h2",
    "lag_h3",
    "delta_h1",
    "rolling_mean_h1",
    "sin_hour",
    "cos_hour",
    "sin_dow",
    "cos_dow",
    "temperature_2m",
    "precipitation",
    "is_vacances",
    "is_ferie",
]

# Pas d'échantillonnage Gold (5 min)
SAMPLE_STEP_MINUTES = 5


class XGBoostSpeedModel:
    """Modèle XGBoost multi-horizon pour prédiction vitesse trafic."""

    def __init__(self, model_dir: str | None = None):
        # Une seule assignation de model_dir
        self.model_dir = Path(model_dir or os.getenv("LYONFLOW_MODELS_DIR", "/app/models"))
        self.models: dict[int, xgb.XGBRegressor] = {}  # horizon_minutes → model

    def load(self, horizons: list[int] | None = None) -> None:
        """Charge les modèles depuis MLflow (si dispo) ou depuis le disque local."""
        import mlflow

        from src.ml.mlflow_integration import is_mlflow_available

        horizons = horizons or [5, 60, 180, 360]
        for h in horizons:
            model_name = f"xgb_speed_h{h}"
            model_path = self.model_dir / f"{model_name}.pkl"

            # Essayer MLflow en premier (Model Registry)
            mlflow_success = False
            if is_mlflow_available():
                try:
                    # Télécharge l'artifact depuis le registre (Production)
                    artifact_uri = f"models:/{model_name}/Production"
                    local_path = mlflow.artifacts.download_artifacts(artifact_uri, dst_path=str(self.model_dir))
                    self.models[h] = joblib.load(local_path)
                    logger.info(f"Loaded XGBoost model horizon {h}min from MLflow Registry (Production)")
                    mlflow_success = True
                except Exception as e:
                    logger.warning(f"Failed to load {model_name} from MLflow Registry: {e}")

            # Fallback disque local
            if not mlflow_success:
                if model_path.exists():
                    self.models[h] = joblib.load(model_path)
                    logger.info(f"Loaded XGBoost model horizon {h}min from local disk")
                else:
                    logger.warning(f"Model not found: {model_path} (neither in MLflow nor local)")

    def train_one(
        self,
        horizon_minutes: int,
        df: pd.DataFrame | None = None,
        n_estimators: int = 200,
        max_depth: int = 6,
        learning_rate: float = 0.1,
    ) -> dict:
        """Entraîne un modèle pour un horizon donné.

        Args:
            horizon_minutes: horizon de prédiction (5, 60, 180, 360)
            df: DataFrame pré-chargé. Si None, charge depuis gold.
            n_estimators, max_depth, learning_rate: hyperparamètres XGBoost.

        Returns:
            Dict avec métriques {'mae', 'rmse', 'r2'}.
        """
        if df is None:
            df = self._load_training_data(horizon_minutes)

        if df.empty:
            raise ValueError(f"Pas de données d'entraînement pour horizon {horizon_minutes}min")

        # Split train/test chronologique
        split_idx = int(len(df) * 0.8)
        train = df.iloc[:split_idx]
        test = df.iloc[split_idx:]

        X_train = train[FEATURE_COLS]
        y_train = train["target_speed"]
        X_test = test[FEATURE_COLS]
        y_test = test["target_speed"]

        # Entraînement
        model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        # Évaluation
        y_pred = model.predict(X_test)
        metrics = {
            "mae": float(np.mean(np.abs(y_test - y_pred))),
            "rmse": float(np.sqrt(np.mean((y_test - y_pred) ** 2))),
            "r2": float(1 - np.sum((y_test - y_pred) ** 2) / np.sum((y_test - y_test.mean()) ** 2)),
        }

        # Sauvegarde
        self.models[horizon_minutes] = model
        model_path = self.model_dir / f"xgb_speed_h{horizon_minutes}.pkl"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_path)

        # MLflow tracking (Sprint 9 — opt-out via MLFLOW_TRACKING_URI=""
        # Le tracker gère le no-op gracieux si le serveur est down.)
        if os.getenv("MLFLOW_TRACKING_URI", "") != "":
            try:
                tracker = MLflowTracker(experiment_name="xgboost_speed")
                run_name = f"xgb_speed_h{horizon_minutes}_{int(time.time())}"
                with tracker.start_run(run_name=run_name) as _run:
                    tracker.set_tag("model", "xgboost_speed")
                    tracker.set_tag("horizon_min", str(horizon_minutes))
                    tracker.log_params(
                        {
                            "horizon_min": horizon_minutes,
                            "n_estimators": n_estimators,
                            "max_depth": max_depth,
                            "learning_rate": learning_rate,
                            "n_samples": len(df),
                            "n_features": len(FEATURE_COLS),
                            "model_version": "1.2.0",
                        }
                    )
                    tracker.log_metrics(metrics)
                    tracker.log_artifact(str(model_path))
                    # Register & transition to Production natively
                    reg_model_name = f"xgboost_speed_h{horizon_minutes}"
                    tracker.register_model(reg_model_name)
                    tracker.transition_to_production(reg_model_name)
            except Exception as e:  # pragma: no cover
                logger.warning("MLflow tracking failed (non-bloquant): %s", e)

        logger.info(f"XGBoost speed H+{horizon_minutes}min trained: MAE={metrics['mae']:.2f}, R²={metrics['r2']:.3f}")
        return metrics

    def predict(
        self,
        channel_id: str,
        horizon_minutes: int,
        features: dict | None = None,
    ) -> dict:
        """Prédit la vitesse pour un canal (string LYO000xx) et un horizon.

        Args:
            channel_id: identifiant canal trafic (ex. "LYO00007")
            horizon_minutes: 5, 60, 180, 360
            features: dict de features. Si None, lookup gold.

        Returns:
            Dict avec predicted_speed, confidence_low/high.
        """
        if horizon_minutes not in self.models:
            self.load()
        if horizon_minutes not in self.models:
            # Pas de modèle entraîné — fallback
            return {
                "predicted_speed_kmh": 30.0,
                "confidence_low": 25.0,
                "confidence_high": 35.0,
                "model_name": "fallback",
                "model_version": "0.0.0",
            }

        if features is None:
            features = self._lookup_features(channel_id)
        if not features:
            return {
                "predicted_speed_kmh": 30.0,
                "confidence_low": 25.0,
                "confidence_high": 35.0,
                "model_name": "fallback_no_features",
                "model_version": "0.0.0",
            }

        X = pd.DataFrame([features])[FEATURE_COLS]
        model = self.models[horizon_minutes]
        pred = model.predict(X)[0]
        pred = float(np.clip(pred, 1.0, 130.0))

        # Confidence interval : ±5 km/h (heuristique simple, à raffiner)
        # TODO Sprint 6+ : quantile regression XGBoost pour vrais intervalles
        return {
            "predicted_speed_kmh": round(pred, 2),
            "confidence_low": round(max(1.0, pred - 5.0), 2),
            "confidence_high": round(min(130.0, pred + 5.0), 2),
            "model_name": "xgb_speed",
            "model_version": "1.0.0",
        }

    def _load_training_data(self, horizon_minutes: int) -> pd.DataFrame:
        """Charge les données d'entraînement depuis Gold.

        Le target est la vitesse au temps t + horizon, calculée via LEAD()
        sur les données échantillonnées toutes les SAMPLE_STEP_MINUTES minutes.
        """
        # Nombre de pas = horizon_minutes / step
        lead_steps = max(1, horizon_minutes // SAMPLE_STEP_MINUTES)

        query = """
            WITH ranked AS (
                SELECT
                    speed_kmh, lag_h1, lag_h2, lag_h3,
                    delta_h1, rolling_mean_h1,
                    sin_hour, cos_hour, sin_dow, cos_dow,
                    temperature_2m, precipitation,
                    COALESCE(is_vacances, FALSE) AS is_vacances,
                    COALESCE(is_ferie, FALSE) AS is_ferie,
                    -- Target : speed au temps t + horizon (LEAD window function)
                    LEAD(speed_kmh, %s) OVER (
                        PARTITION BY channel_id ORDER BY computed_at
                    ) AS target_speed,
                    channel_id
                FROM gold.traffic_features_live
                WHERE speed_kmh IS NOT NULL
                  AND computed_at > NOW() - INTERVAL '7 days'
            )
            SELECT
                speed_kmh, lag_h1, lag_h2, lag_h3,
                delta_h1, rolling_mean_h1,
                sin_hour, cos_hour, sin_dow, cos_dow,
                temperature_2m, precipitation,
                is_vacances, is_ferie,
                target_speed
            FROM ranked
            WHERE target_speed IS NOT NULL
            ORDER BY channel_id
        """
        # Note: psycopg2 peut paramétrer un int dans LEAD()
        rows = execute_query(query, (lead_steps,))
        return pd.DataFrame(rows)

    def _lookup_features(self, channel_id: str) -> dict:
        """Récupère les dernières features pour un canal (string LYO000xx).

        Sprint 9 : `channel_id` est maintenant un string (LYO000xx) au lieu
        d'un int `node_idx`. Voir gold.dim_spatial_grid_mapping.
        """
        query = """
            SELECT
                speed_kmh, lag_h1, lag_h2, lag_h3,
                delta_h1, rolling_mean_h1,
                sin_hour, cos_hour, sin_dow, cos_dow,
                temperature_2m, precipitation,
                COALESCE(is_vacances, FALSE) AS is_vacances,
                COALESCE(is_ferie, FALSE) AS is_ferie
            FROM gold.traffic_features_live
            WHERE channel_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
        """
        rows = execute_query(query, (channel_id,))
        if not rows:
            return {}
        return dict(rows[0])
