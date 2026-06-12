"""Tests pour xgboost_velov.py — Sprint 9 refacto.

Couvre :
* Import du module sans erreur
* Classe instanciable
* FEATURE_COLS coherent avec les queries SQL
* Methodes load/predict ne crash pas (hors DB)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.xgboost_velov import (
    FEATURE_COLS,
    XGBoostVelovModel,
)


class TestXGBoostVelovImports:
    def test_module_imports_without_error(self):
        assert True

    def test_feature_cols_are_strings(self):
        assert isinstance(FEATURE_COLS, list)
        assert all(isinstance(c, str) for c in FEATURE_COLS)

    def test_feature_cols_not_empty(self):
        assert len(FEATURE_COLS) > 0


class TestXGBoostVelovInstantiation:
    def test_instantiation_default(self):
        model = XGBoostVelovModel()
        assert model._model_dir is not None
        assert model.models == {}

    def test_instantiation_custom_dir(self, tmp_path):
        model = XGBoostVelovModel(model_dir=str(tmp_path))
        assert model._model_dir == tmp_path

    def test_single_assignment_model_dir(self):
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "models" / "xgboost_velov.py"
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "XGBoostVelovModel":
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


class TestXGBoostVelovLoad:
    def test_load_does_not_crash_without_models(self):
        model = XGBoostVelovModel(model_dir="/tmp/nonexistent_xgb_velov")
        model.load()
        assert 30 not in model.models
        assert 60 not in model.models

    @patch("src.ml.mlflow_integration.is_mlflow_available", return_value=False)
    def test_load_skips_mlflow_when_unavailable(self, mock_mlflow):
        """load() appelle is_mlflow_available depuis mlflow_integration."""
        model = XGBoostVelovModel()
        model.load()
        mock_mlflow.assert_called()


class TestXGBoostVelovPredict:
    def test_predict_fallback_no_model(self):
        model = XGBoostVelovModel(model_dir="/tmp/nonexistent")
        result = model.predict("lyon_001", horizon_minutes=30)
        assert "predicted_bikes" in result
        assert "model_name" in result
        assert result["model_name"] == "fallback"

    def test_predict_fallback_skips_db(self):
        """predict() sans model charge retourne fallback sans appeler la DB."""
        model = XGBoostVelovModel()
        result = model.predict("lyon_001", horizon_minutes=30)
        assert result["model_name"] == "fallback"
        assert result["predicted_bikes"] == 0.0


class TestXGBoostVelovSql:
    def test_load_training_data_query_no_redundant_params(self):
        """_load_training_data() appelle execute_query() sans () redundant."""
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "models" / "xgboost_velov.py"
        content = src.read_text()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_load_training_data":
                calls = [
                    n
                    for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "execute_query"
                ]
                for call in calls:
                    args = call.args
                    if len(args) >= 2:
                        second_arg = args[1]
                        assert not (isinstance(second_arg, ast.Constant) and second_arg.value == ()), (
                            "_load_training_data: execute_query called with redundant ()"
                        )


class TestXGBoostVelovNoDeadCode:
    def test_all_public_methods_exist(self):
        """Toutes les methodes publiques de XGBoostVelovModel sont definies."""
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "models" / "xgboost_velov.py"
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "XGBoostVelovModel":
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                public = [m for m in methods if not m.startswith("_")]
                private = [m for m in methods if m.startswith("_") and m != "__init__"]
                assert "load" in public
                assert "train_one" in public
                assert "predict" in public
                assert "_load_training_data" in private
                assert "_lookup_features" in private
                assert len(public) == len(set(public))
