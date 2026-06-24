"""XGBoost Speed Model — prédiction vitesse trafic.

Sprint 9 — Focus H+1h (fiabilité VPS), aligné sur le schéma RÉEL
v0.3.1 de `gold.traffic_features_live` (cf. audit 2026-06-12).

Schéma réel :
    speed_kmh, channel_id, computed_at,
    lag_1, lag_2, lag_3, delta_current, delta_1, rolling_mean_3,
    sin_hour, cos_hour, sin_dow, cos_dow,
    temperature_2m, precipitation, rain, is_raining,
    is_vacances, is_ferie, lat, lon, ...

FEATURES (11 colonnes, strictes H+1h) :
    speed_kmh (valeur courante)
    lag_1, lag_2, lag_3 (lags 5/10/15 min)
    rolling_mean_3 (moyenne 15 min de contexte)
    sin_hour, cos_hour (saisonnalité intra-journalière)
    temperature_2m, precipitation (météo)
    is_vacances, is_ferie (calendrier)

Target = LEAD(speed_kmh, 12) — la valeur 12 pas (60 min) plus tard,
pour H+1h. Échantillonnage : 1 pas = 5 min (cf. computed_at).

MLflow tracking opt-in via MLFLOW_TRACKING_URI non-vide.
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


# Features (Sprint 9 — alignées sur le schéma RÉEL gold.traffic_features_live)
# Convention de nommage : les colonnes de la DB sont déjà préfixées
# (lag_1 = valeur 5 min avant, lag_2 = 10 min avant, etc.). Pour
# H+1h, lag_1, lag_2, lag_3 couvrent 5/10/15 min de contexte court,
# rolling_mean_3 = moyenne 15 min.
FEATURE_COLS = [
    "speed_kmh",
    "lag_1",
    "lag_2",
    "lag_3",
    "rolling_mean_3",
    "sin_hour",
    "cos_hour",
    "temperature_2m",
    "precipitation",
    "is_vacances",
    "is_ferie",
]

# Pas d'échantillonnage Gold = 5 min
SAMPLE_STEP_MINUTES = 5
# H+1h uniquement (focus fiabilité)
DEFAULT_HORIZONS = [60]


class XGBoostSpeedModel:
    """Modèle XGBoost multi-horizon pour prédiction vitesse trafic."""

    def __init__(self, model_dir: str | None = None):
        # Une seule assignation de model_dir.
        # Double `or` pour que mypy comprenne que le résultat est toujours str.
        resolved_dir = model_dir or os.getenv("LYONFLOW_MODELS_DIR") or "/app/models"
        self.model_dir = Path(resolved_dir)
        self.models: dict[int, xgb.XGBRegressor] = {}  # horizon_minutes → model

    def load(self, horizons: list[int] | None = None) -> None:
        """Charge les modèles depuis MLflow (si dispo) ou depuis le disque local.

        EXPLICATION MÉTIER (Analyse) :
        Ce modèle est intégré avec MLflow pour le suivi des expérimentations et le
        registre de modèles (Model Registry). Au démarrage ou lors d'une prédiction,
        le code tente de télécharger le modèle marqué "Production" depuis MLflow.
        Si MLflow est tombé ou inaccessible, le code "fallback" de façon robuste
        sur le dernier modèle pkl stocké localement sur le disque du VPS.
        """
        import mlflow

        from src.ml.mlflow_integration import is_mlflow_available

        # Sprint 8+2 (2026-06-12) — Focus H+1h uniquement (fiabilité VPS).
        # Avant : [5, 60, 180, 360] — 4 modèles entraînés, 4x le coût
        #          compute et la mémoire.
        # Après : [60] — 1 seul modèle, horizon = 1h, conforme au focus
        #          Sprint VPS-6 (gold.trafic_predictions.horizon_h=1).
        horizons = horizons or [60]
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

        EXPLICATION MÉTIER (Analyse) :
        C'est ici que l'entraînement du modèle a lieu (souvent déclenché par le DAG Airflow).
        On sépare chronologiquement les données : les 80% les plus anciens pour l'entraînement,
        les 20% les plus récents pour le test (afin de ne pas faire de fuite temporelle).
        Les hyperparamètres peuvent être ajustés, mais par défaut on limite la profondeur
        (`max_depth=6`) pour éviter le surentraînement.
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

        # Entraînement — 3 modèles quantile (P10, P50, P90) pour intervalles
        # de confiance réels. XGBoost 2.0+ supporte nativement quantile error.
        # Sprint 21 P4.2 : remplace l'heuristique ±5 km/h.
        quantiles = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
        models = {}
        metrics = {}
        for label, alpha in quantiles.items():
            model = xgb.XGBRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                objective="reg:quantileerror",
                quantile_alpha=alpha,
                random_state=42,
                n_jobs=-1,
            )
            model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
            y_pred_q = model.predict(X_test)
            models[label] = model
            metrics[label] = {
                "mae": float(np.mean(np.abs(y_test - y_pred_q))),
                "rmse": float(np.sqrt(np.mean((y_test - y_pred_q) ** 2))),
                "r2": float(1 - np.sum((y_test - y_pred_q) ** 2) / max(np.sum((y_test - y_test.mean()) ** 2), 1e-9)),
            }

        # Métrique agrégée = P50 (médiane) pour rétro-compat dashboard
        y_pred = models["p50"].predict(X_test)
        metrics.update(
            {
                "mae": float(np.mean(np.abs(y_test - y_pred))),
                "rmse": float(np.sqrt(np.mean((y_test - y_pred) ** 2))),
                "r2": float(1 - np.sum((y_test - y_pred) ** 2) / max(np.sum((y_test - y_test.mean()) ** 2), 1e-9)),
            }
        )

        # Sauvegarde : 1 dict {p10, p50, p90} par horizon (même path que
        # l'ancien format mono-modèle pour rétro-compat loader MLflow/FS).
        self.models[horizon_minutes] = models
        models_path = self.model_dir / f"xgb_speed_h{horizon_minutes}.pkl"
        models_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(models, models_path)

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
                    tracker.log_artifact(str(models_path))
                    # Register & transition to Production natively
                    reg_model_name = f"xgboost_speed_h{horizon_minutes}"
                    tracker.register_model(reg_model_name)
                    tracker.transition_to_production(reg_model_name)
            except Exception as e:  # pragma: no cover
                logger.warning("MLflow tracking failed (non-bloquant): %s", e)

        # Sprint 10+ MLOps — Génère et sauvegarde un Model Card (Markdown)
        try:
            from src.data.db_query import get_latest_drift_report
            from src.ml.model_card import generate_xgboost_card, save_card

            params = {
                "horizon_min": horizon_minutes,
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "learning_rate": learning_rate,
                "n_samples": len(df),
                "n_features": len(FEATURE_COLS),
                "model_version": "1.2.0",
            }
            dataset_stats = {
                "n_rows": len(df),
                "n_channels": int(df["channel_id"].nunique()) if "channel_id" in df.columns else 0,
            }
            card_md = generate_xgboost_card(
                model_version=str(params.get("model_version", "1.2.0")),
                horizon_minutes=horizon_minutes,
                metrics=metrics,
                params=params,
                dataset_stats=dataset_stats,
                drift_report=get_latest_drift_report(),
                feature_cols=FEATURE_COLS,
            )
            card_path = save_card(card_md, "xgboost_speed", str(params.get("model_version", "1.2.0")))
            # Pousse le card comme artifact MLflow si tracking actif
            if os.getenv("MLFLOW_TRACKING_URI", "") != "":
                try:
                    tracker.log_artifact(str(card_path))
                except Exception as e:
                    logger.debug("MLflow log_artifact(model_card) failed: %s", e)
        except Exception as e:
            logger.warning("Model Card generation failed (non-bloquant): %s", e)

        logger.info(f"XGBoost speed H+{horizon_minutes}min trained: MAE={metrics['mae']:.2f}, R²={metrics['r2']:.3f}")
        return metrics

    def predict(
        self,
        channel_id: str,
        horizon_minutes: int = 60,
        features: dict | None = None,
    ) -> dict:
        """Prédit la vitesse pour un canal (string LYO000xx) à H+1h.

        Args:
            channel_id: identifiant canal trafic (ex. "LYO00007")
            horizon_minutes: doit être 60 (Sprint 8+2 — focus H+1h).
                            Si autre valeur, fallback (30.0 km/h) et warning.
            features: dict de features. Si None, lookup gold.

        Returns:
            Dict avec predicted_speed, confidence_low/high.

        EXPLICATION MÉTIER (Analyse) :
        La prédiction à H+1h se base sur les "lags" (vitesse il y a 5, 10, 15 min),
        et sur des facteurs exogènes (heure de la journée encodée en sinus/cosinus, météo).
        Si l'horizon demandé n'est pas 60 minutes, la fonction renvoie volontairement
        un "fallback" (30 km/h) afin de limiter les coûts de calculs inutiles,
        car le Sprint 8 a recentré le besoin métier exclusivement sur le H+1h.
        """
        # Sprint 8+2 (2026-06-12) — Focus H+1h uniquement. Si un caller
        # demande un autre horizon, fallback direct (pas de coût compute).
        if horizon_minutes != 60:
            logger.warning(
                "xgb_speed: horizon %dmin demandé, fallback (focus H+1h)",
                horizon_minutes,
            )
            return {
                "predicted_speed_kmh": 30.0,
                "confidence_low": 25.0,
                "confidence_high": 35.0,
                "model_name": "fallback_horizon_unsupported",
                "model_version": "0.0.0",
            }

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
        # Sprint 21 P4.2 : 3 modèles quantile (P10, P50, P90) par horizon.
        # Retourne vrais intervalles de confiance au lieu de l'heuristique ±5 km/h.
        models = self.models[horizon_minutes]
        if isinstance(models, dict):
            # Nouveau format : dict {p10, p50, p90}
            p10 = float(np.clip(models["p10"].predict(X)[0], 1.0, 130.0))
            p50 = float(np.clip(models["p50"].predict(X)[0], 1.0, 130.0))
            p90 = float(np.clip(models["p90"].predict(X)[0], 1.0, 130.0))
        else:
            # Rétro-compat : ancien format (1 seul modèle, fallback heuristique)
            pred = float(np.clip(models.predict(X)[0], 1.0, 130.0))
            p10 = max(1.0, pred - 5.0)
            p50 = pred
            p90 = min(130.0, pred + 5.0)

        return {
            "predicted_speed_kmh": round(p50, 2),
            "confidence_low": round(p10, 2),
            "confidence_high": round(p90, 2),
            "model_name": "xgb_speed",
            "model_version": "1.1.0",  # bumped : quantile support
        }

    def _load_training_data(self, horizon_minutes: int) -> pd.DataFrame:
        """Charge les données d'entraînement depuis ``gold.xgb_training_set``.

        Sprint 9+ (2026-06-12) — La table ``gold.xgb_training_set`` est
        materialisée quotidiennement par le DAG ``build_xgb_training_set``
        (02h30) avec un self-join H+1h indexé. Le target_speed est
        pré-calculé en base, donc plus de ``LEAD() OVER (...)`` sur 2.4M
        rows à l'entraînement (qui timeout depuis Streamlit).

        Note : ``horizon_minutes`` est conservé pour la signature
        d'API, mais l'implémentation est H+1h uniquement (focus fiabilité
        VPS, Sprint VPS-6). La table contient déjà le target à 60 min.

        Returns:
            DataFrame avec les colonnes de FEATURE_COLS + ``target_speed``.
        """
        query = """
            SELECT
                channel_id, channel_hash,
                speed_kmh, lag_1, lag_2, lag_3,
                rolling_mean_3,
                sin_hour, cos_hour,
                temperature_2m, precipitation,
                is_vacances, is_ferie,
                target_speed
            FROM gold.xgb_training_set
            WHERE target_speed IS NOT NULL
              AND computed_at > NOW() - INTERVAL '7 days'
            ORDER BY channel_id, computed_at
        """
        rows = execute_query(query)
        if not rows:
            raise RuntimeError(
                "gold.xgb_training_set est vide. Le DAG "
                "'build_xgb_training_set' doit tourner (02h30 quotidien) "
                "pour matérialiser le training set H+1h."
            )
        return pd.DataFrame(rows)

    def _lookup_features(self, channel_id: str) -> dict:
        """Récupère les dernières features pour un canal (string LYO000xx).

        Sprint 9 : `channel_id` est un string (LYO000xx) au lieu d'un int
        `node_idx`. Voir gold.dim_spatial_grid_mapping.
        Sprint 9+ : aligné sur le schéma RÉEL (lag_1, lag_2, lag_3, etc.).
        """
        query = """
            SELECT
                speed_kmh, lag_1, lag_2, lag_3,
                rolling_mean_3,
                sin_hour, cos_hour,
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
