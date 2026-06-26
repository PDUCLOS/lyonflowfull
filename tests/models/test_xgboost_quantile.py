"""Tests pour la quantile regression XGBoost P4.2).

Valide le contrat de l'API sans entraîner de vrai modèle (lent + DB requise).
On mock le xgb.XGBRegressor pour qu'il retourne des prédictions déterministes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.xgboost_speed import FEATURE_COLS, XGBoostSpeedModel

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_xgb_models() -> dict[str, MagicMock]:
    """Mock xgb.XGBRegressor pour P10/P50/P90 avec prédictions déterministes.

    P10 (alpha=0.1) → 22.0 km/h (lower bound)
    P50 (alpha=0.5) → 30.0 km/h (median)
    P90 (alpha=0.9) → 38.0 km/h (upper bound)
    """
    p10, p50, p90 = MagicMock(), MagicMock(), MagicMock()
    p10.predict.return_value = np.array([22.0])
    p50.predict.return_value = np.array([30.0])
    p90.predict.return_value = np.array([38.0])
    return {"p10": p10, "p50": p50, "p90": p90}


@pytest.fixture
def sample_features() -> dict[str, float]:
    """11 features pour H+1h (schéma v0.3.1)."""
    return {
        "speed_kmh": 30.0,
        "lag_1": 29.5,
        "lag_2": 28.0,
        "lag_3": 27.0,
        "rolling_mean_3": 28.5,
        "sin_hour": 0.5,
        "cos_hour": 0.866,
        "temperature_2m": 18.0,
        "precipitation": 0.0,
        "is_vacances": 0.0,
        "is_ferie": 0.0,
    }


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_predict_returns_three_quantiles(
    mock_xgb_models: dict[str, MagicMock],
    sample_features: dict[str, float],
    tmp_path: Path,
) -> None:
    """predict() doit retourner 3 quantiles (P10, P50, P90)."""
    model = XGBoostSpeedModel(model_dir=tmp_path)
    model.models = {60: mock_xgb_models}  # H+1h = 60 min

    result = model.predict(channel_id="LYO00007", horizon_minutes=60, features=sample_features)

    assert "predicted_speed_kmh" in result
    assert "confidence_low" in result
    assert "confidence_high" in result
    assert result["predicted_speed_kmh"] == 30.0  # P50
    assert result["confidence_low"] == 22.0  # P10
    assert result["confidence_high"] == 38.0  # P90
    assert result["model_version"] == "1.1.0"  # bumped


def test_predict_retro_compat_single_model(
    sample_features: dict[str, float],
    tmp_path: Path,
) -> None:
    """predict() doit supporter l'ancien format (1 seul modèle XGBoostRegressor).

    Si le .pkl chargé est un seul modèle (pas un dict), fallback sur l'heuristique.
    """
    model = XGBoostSpeedModel(model_dir=tmp_path)
    old_model = MagicMock()
    old_model.predict.return_value = np.array([30.0])
    model.models = {60: old_model}  # Format ancien : 1 modèle au lieu de dict

    result = model.predict(channel_id="LYO00007", horizon_minutes=60, features=sample_features)

    # Rétro-compat : predicted_speed = modèle, confidence_low/high = ±5 km/h
    assert result["predicted_speed_kmh"] == 30.0
    assert result["confidence_low"] == 25.0  # 30 - 5
    assert result["confidence_high"] == 35.0  # 30 + 5


def test_predict_clipping(
    mock_xgb_models: dict[str, MagicMock],
    sample_features: dict[str, float],
    tmp_path: Path,
) -> None:
    """Les prédictions doivent être clipées entre 1.0 et 130.0 km/h."""
    mock_xgb_models["p10"].predict.return_value = np.array([-50.0])  # < 1.0
    mock_xgb_models["p50"].predict.return_value = np.array([200.0])  # > 130.0
    mock_xgb_models["p90"].predict.return_value = np.array([300.0])  # > 130.0

    model = XGBoostSpeedModel(model_dir=tmp_path)
    model.models = {60: mock_xgb_models}

    result = model.predict(channel_id="LYO00007", horizon_minutes=60, features=sample_features)

    assert result["confidence_low"] == 1.0  # clip bas
    assert result["predicted_speed_kmh"] == 130.0  # clip haut
    assert result["confidence_high"] == 130.0  # clip haut


def test_train_one_saves_dict_format(tmp_path: Path) -> None:
    """train_one() doit sauvegarder un dict {p10, p50, p90} et 3 modèles."""
    import joblib
    from sklearn.model_selection import train_test_split

    np.random.seed(42)
    n_samples = 200
    df = pd.DataFrame(
        {
            "speed_kmh": np.random.uniform(10, 50, n_samples),
            "lag_1": np.random.uniform(10, 50, n_samples),
            "lag_2": np.random.uniform(10, 50, n_samples),
            "lag_3": np.random.uniform(10, 50, n_samples),
            "rolling_mean_3": np.random.uniform(10, 50, n_samples),
            "sin_hour": np.random.uniform(-1, 1, n_samples),
            "cos_hour": np.random.uniform(-1, 1, n_samples),
            "temperature_2m": np.random.uniform(5, 30, n_samples),
            "precipitation": np.random.uniform(0, 5, n_samples),
            "is_vacances": np.zeros(n_samples),
            "is_ferie": np.zeros(n_samples),
            "target_speed": np.random.uniform(10, 50, n_samples),
        }
    )

    # Pas de DB requise : on passe df directement
    model = XGBoostSpeedModel(model_dir=tmp_path)
    with patch("src.models.xgboost_speed.execute_query") as _:
        metrics = model.train_one(horizon_minutes=60, df=df, n_estimators=10)

    # 1. self.models[60] doit être un dict avec 3 clés
    assert isinstance(model.models[60], dict)
    assert set(model.models[60].keys()) == {"p10", "p50", "p90"}

    # 2. .pkl doit exister
    pkl_path = tmp_path / "xgb_speed_h60.pkl"
    assert pkl_path.exists()

    # 3. .pkl doit charger un dict
    loaded = joblib.load(pkl_path)
    assert isinstance(loaded, dict)
    assert set(loaded.keys()) == {"p10", "p50", "p90"}

    # 4. Métriques agrégées P50 présentes
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "r2" in metrics
