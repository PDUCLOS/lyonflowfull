"""Tests pour xgboost_speed.py — Sprint 9 refacto.

Couvre :
* Import du module sans erreur
* Classe instanciable
* FEATURE_COLS aligné sur le schéma gold.traffic_features_live
* Méthodes load/predict ne crash pas (hors DB)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.xgboost_speed import (
    DEFAULT_HORIZONS,
    FEATURE_COLS,
    SAMPLE_STEP_MINUTES,
    XGBoostSpeedModel,
)


class TestXGBoostSpeedImports:
    def test_module_imports_without_error(self):
        assert True

    def test_feature_cols_are_strings(self):
        assert isinstance(FEATURE_COLS, list)
        assert all(isinstance(c, str) for c in FEATURE_COLS)

    def test_feature_cols_aligned_on_schema(self):
        expected = {
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
        }
        assert set(FEATURE_COLS) == expected

    def test_default_horizons_h1_only(self):
        assert DEFAULT_HORIZONS == [60]

    def test_sample_step_5min(self):
        assert SAMPLE_STEP_MINUTES == 5


class TestXGBoostSpeedInstantiation:
    def test_instantiation_default(self):
        model = XGBoostSpeedModel()
        assert model._model_dir is not None
        assert model.models == {}

    def test_instantiation_custom_dir(self, tmp_path):
        model = XGBoostSpeedModel(model_dir=str(tmp_path))
        assert model._model_dir == tmp_path

    def test_single_assignment_model_dir(self):
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "models" / "xgboost_speed.py"
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "XGBoostSpeedModel":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        assigns = [
                            t.attr
                            for n in ast.walk(item)
                            if isinstance(n, ast.Assign)
                            for t in n.targets
                            if isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"
                            and t.attr == "_model_dir"
                        ]
                        assert len(assigns) == 1


class TestXGBoostSpeedLoad:
    def test_load_does_not_crash_without_models(self):
        model = XGBoostSpeedModel(model_dir="/tmp/nonexistent_xgb_speed")
        model.load()
        assert 60 not in model.models

    @patch("src.ml.mlflow_integration.is_mlflow_available", return_value=False)
    def test_load_skips_mlflow_when_unavailable(self, mock_mlflow):
        """load() appelle is_mlflow_available depuis mlflow_integration."""
        model = XGBoostSpeedModel()
        model.load()
        mock_mlflow.assert_called()


class TestXGBoostSpeedPredict:
    def test_predict_fallback_no_model(self):
        model = XGBoostSpeedModel(model_dir="/tmp/nonexistent")
        result = model.predict("LYO00007", horizon_minutes=60)
        assert "predicted_speed_kmh" in result
        assert "confidence_low" in result
        assert "confidence_high" in result
        assert result["model_name"] in ("fallback", "fallback_horizon_unsupported")

    def test_predict_unsupported_horizon_fallback(self):
        model = XGBoostSpeedModel()
        result = model.predict("LYO00007", horizon_minutes=30)
        assert result["model_name"] == "fallback_horizon_unsupported"
        assert result["predicted_speed_kmh"] == 30.0

    @patch("src.models.xgboost_speed.execute_query")
    def test_predict_with_features_uses_them(self, mock_eq):
        """predict() utilise les features passees en argument, pas la DB."""
        model = XGBoostSpeedModel()
        model.models[60] = MagicMock()
        model.models[60].predict.return_value = [65.0]
        features = dict.fromkeys(FEATURE_COLS, 50.0)
        features["speed_kmh"] = 50.0
        result = model.predict("LYO00007", horizon_minutes=60, features=features)
        mock_eq.assert_not_called()
        assert result["predicted_speed_kmh"] == 65.0


class TestXGBoostSpeedNoUndefinedVars:
    def test_train_one_no_undefined_params(self):
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "models" / "xgboost_speed.py"
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "train_one":
                params_uses = [n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id == "params"]
                assert len(params_uses) == 0, f"train_one references undefined 'params': {params_uses}"
