"""Tests pour src.ml.model_registry.

Couvre :
* Lecture des variables d'environnement (LYONFLOW_MODELS_ACTIVE, training toggles)
* Toggle XGBoost / GNN / both
* Wrapper functions is_*_enabled()
* should_run_*_dag() — utilisé par les DAGs Airflow
* ModelRegistry singleton + status + compare_predictions (fallback gracieux)
* Validation des valeurs invalides
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permet l'import depuis la racine
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ml import model_registry
from src.ml.model_registry import (
    ModelKind,
    ModelRegistry,
    get_active_models,
    is_stgcn_enabled,
    is_stgcn_training_enabled,
    is_xgboost_enabled,
    is_xgboost_training_enabled,
    should_run_stgcn_dag,
    should_run_xgboost_dag,
)


@pytest.fixture(autouse=True)
def reset_env_and_cache(monkeypatch):
    """Reset env vars + cache ModelRegistry entre chaque test."""
    # Reset cache registry
    ModelRegistry.reset()
    # Nettoyer env vars liées au registry
    for key in (
        "LYONFLOW_MODELS_ACTIVE",
        "LYONFLOW_XGBOOST_TRAINING",
        "LYONFLOW_STGCN_TRAINING",
    ):
        monkeypatch.delenv(key, raising=False)
    # Recharger la config (les settings pydantic cachent aussi)
    from src.config import get_settings

    get_settings.__globals__["_settings"] = None
    yield
    ModelRegistry.reset()


# =============================================================================
# Tests toggle par env var
# =============================================================================


class TestActiveModels:
    """Vérifie la lecture de LYONFLOW_MODELS_ACTIVE."""

    def test_default_is_both(self, monkeypatch):
        monkeypatch.delenv("LYONFLOW_MODELS_ACTIVE", raising=False)
        assert get_active_models() == ModelKind.BOTH

    def test_xgboost_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        assert get_active_models() == ModelKind.XGBOOST

    def test_stgcn_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        assert get_active_models() == ModelKind.STGCN

    def test_both_explicit(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        assert get_active_models() == ModelKind.BOTH

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "XGBOOST")
        assert get_active_models() == ModelKind.XGBOOST
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "StGcn")
        assert get_active_models() == ModelKind.STGCN

    def test_invalid_value_raises(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "garbage")
        with pytest.raises(ValueError, match="invalide"):
            get_active_models()


# =============================================================================
# Tests flags is_*_enabled
# =============================================================================


class TestEnabledFlags:
    """Vérifie les flags is_xgboost_enabled / is_stgcn_enabled."""

    def test_both_xgboost_and_stgcn_when_both(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        assert is_xgboost_enabled() is True
        assert is_stgcn_enabled() is True

    def test_only_xgboost_when_xgboost_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        assert is_xgboost_enabled() is True
        assert is_stgcn_enabled() is False

    def test_only_stgcn_when_stgcn_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        assert is_xgboost_enabled() is False
        assert is_stgcn_enabled() is True


class TestTrainingFlags:
    """Vérifie les toggles de training (séparés de l'activation).

    Sprint 9 : STGCN training est désactivé par défaut (mode préparation).
    Le DAG est créé en pause, à activer via ``LYONFLOW_STGCN_TRAINING=true``.
    """

    def test_default_stgcn_training_disabled(self, monkeypatch):
        """Sprint 9 : STGCN training off par défaut (DAG en pause)."""
        # XGBoost reste ON (training actif sur VPS)
        assert is_xgboost_training_enabled() is True
        # STGCN est OFF (DAG préparé mais pas activé)
        assert is_stgcn_training_enabled() is False

    def test_can_enable_stgcn_training(self, monkeypatch):
        """Pour activer le GNN training : set LYONFLOW_STGCN_TRAINING=true."""
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "true")
        assert is_stgcn_training_enabled() is True
        # XGBoost reste actif
        assert is_xgboost_training_enabled() is True

    def test_can_disable_xgboost_training(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_XGBOOST_TRAINING", "false")
        assert is_xgboost_training_enabled() is False
        # STGCN reste en préparation (off)
        assert is_stgcn_training_enabled() is False

    def test_can_disable_stgcn_training(self, monkeypatch):
        # Set STGCN à true puis à false pour vérifier la désactivation
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "true")
        assert is_stgcn_training_enabled() is True
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "false")
        assert is_stgcn_training_enabled() is False

    def test_can_disable_both_trainings(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_XGBOOST_TRAINING", "false")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "false")
        assert is_xgboost_training_enabled() is False
        assert is_stgcn_training_enabled() is False


# =============================================================================
# Tests should_run_*_dag (utilisé par Airflow)
# =============================================================================


class TestShouldRunDag:
    """Vérifie les helpers utilisés par les DAGs Airflow."""

    def test_should_run_xgboost_when_active_and_training(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        assert should_run_xgboost_dag() is True

    def test_should_not_run_xgboost_when_disabled_in_active(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        assert should_run_xgboost_dag() is False

    def test_should_not_run_xgboost_when_training_disabled(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        monkeypatch.setenv("LYONFLOW_XGBOOST_TRAINING", "false")
        assert should_run_xgboost_dag() is False

    def test_should_run_stgcn_when_active_and_training(self, monkeypatch):
        # Sprint 9 : STGCN training off par défaut, il faut l'activer explicitement
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "true")
        assert should_run_stgcn_dag() is True

    def test_should_not_run_stgcn_when_default_preparation(self, monkeypatch):
        """Sprint 9 : par défaut, le DAG GNN ne doit PAS tourner."""
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        # STGCN_TRAINING n'est pas set → off par défaut
        assert should_run_stgcn_dag() is False

    def test_should_not_run_stgcn_when_not_in_active(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        assert should_run_stgcn_dag() is False

    def test_should_not_run_stgcn_when_training_disabled(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "false")
        assert should_run_stgcn_dag() is False

    def test_both_disabled_no_dags_run(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        monkeypatch.setenv("LYONFLOW_XGBOOST_TRAINING", "false")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "false")
        assert should_run_xgboost_dag() is False
        assert should_run_stgcn_dag() is False


# =============================================================================
# Tests ModelRegistry
# =============================================================================


class TestModelRegistry:
    """Vérifie le comportement du registry (singleton + status)."""

    def test_registry_is_singleton_per_horizon(self):
        r1 = ModelRegistry.get(60)
        r2 = ModelRegistry.get(60)
        assert r1 is r2

    def test_different_horizons_different_instances(self):
        r60 = ModelRegistry.get(60)
        r120 = ModelRegistry.get(120)
        assert r60 is not r120

    def test_reset_clears_cache(self):
        r1 = ModelRegistry.get(60)
        ModelRegistry.reset()
        r2 = ModelRegistry.get(60)
        assert r1 is not r2

    def test_status_includes_all_fields(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        r = ModelRegistry.get(60)
        s = r.status()
        assert s["horizon_min"] == 60
        assert s["active"] == "both"
        assert "xgboost_available" in s
        assert "stgcn_available" in s
        assert "xgboost_training" in s
        assert "stgcn_training" in s
        assert s["champion"] == "xgboost"  # BOTH → XGBoost = champion
        assert s["challenger"] == "stgcn"

    def test_status_xgboost_only_champion(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        r = ModelRegistry.get(60)
        s = r.status()
        assert s["champion"] == "xgboost"
        assert s["challenger"] is None

    def test_status_stgcn_only_champion(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        r = ModelRegistry.get(60)
        s = r.status()
        assert s["champion"] == "stgcn"
        assert s["challenger"] is None


class TestModelRegistryGetters:
    """Vérifie les getters xgboost / stgcn / get_active_model."""

    def test_xgboost_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        r = ModelRegistry.get(60)
        assert r.xgboost is None

    def test_stgcn_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        r = ModelRegistry.get(60)
        assert r.stgcn is None

    def test_get_active_model_returns_xgboost_when_xgboost_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        r = ModelRegistry.get(60)
        active = r.get_active_model()
        assert active is not None
        assert active.model_kind == ModelKind.XGBOOST

    def test_get_active_model_returns_stgcn_when_stgcn_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        r = ModelRegistry.get(60)
        active = r.get_active_model()
        assert active is not None
        assert active.model_kind == ModelKind.STGCN

    def test_get_active_model_champion_is_xgboost_when_both(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        r = ModelRegistry.get(60)
        active = r.get_active_model()
        # BOTH → champion = XGBoost
        assert active.model_kind == ModelKind.XGBOOST

    def test_get_challenger_model_returns_stgcn_when_both(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        r = ModelRegistry.get(60)
        challenger = r.get_challenger_model()
        assert challenger is not None
        assert challenger.model_kind == ModelKind.STGCN

    def test_get_challenger_model_none_when_not_both(self, monkeypatch):
        for active_val in ("xgboost", "stgcn"):
            monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", active_val)
            r = ModelRegistry.get(60)
            assert r.get_challenger_model() is None


class TestModelRegistryComparePredictions:
    """Vérifie compare_predictions (utilisé par monitoring)."""

    def test_compare_with_no_models_loaded(self, monkeypatch):
        """Si aucun modèle chargé, retourne les bons flags."""
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        r = ModelRegistry.get(60)
        result = r.compare_predictions(features=None, edge_index=None)
        assert "xgboost" in result
        assert "stgcn" in result
        assert "delta" in result
        assert result["active"] == "both"

    def test_compare_xgboost_only(self, monkeypatch):
        """Si seul XGBoost activé, stgcn=None dans le résultat."""
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        r = ModelRegistry.get(60)
        result = r.compare_predictions(features=None, edge_index=None)
        assert result["active"] == "xgboost"
        assert result["xgboost"] is None  # pas chargé (modèle absent sur disque)
        assert result["stgcn"] is None  # désactivé

    def test_compare_stgcn_only(self, monkeypatch):
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        r = ModelRegistry.get(60)
        result = r.compare_predictions(features=None, edge_index=None)
        assert result["active"] == "stgcn"


# =============================================================================
# Tests workflow validation (story de Patrice)
# =============================================================================


class TestValidationWorkflow:
    """Simule les transitions du workflow de validation Sprint 8."""

    def test_phase1_both_models_active(self, monkeypatch):
        """Phase 1 : les 2 en //, GNN challenger, XGBoost champion.

        Sprint 9 : par défaut STGCN training est off (préparation).
        Pour activer les 2 DAGs, il faut explicitement mettre
        ``LYONFLOW_STGCN_TRAINING=true``.
        """
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "true")
        r = ModelRegistry.get(60)
        s = r.status()
        assert s["active"] == "both"
        assert s["champion"] == "xgboost"
        assert s["challenger"] == "stgcn"
        # Les 2 DAGs tournent (avec toggle GNN ON)
        assert should_run_xgboost_dag() is True
        assert should_run_stgcn_dag() is True

    def test_phase1_default_preparation(self, monkeypatch):
        """Sprint 9 : par défaut, seul XGBoost tourne, GNN préparé."""
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "both")
        # Pas de STGCN_TRAINING explicite → off par défaut
        r = ModelRegistry.get(60)
        s = r.status()
        assert s["active"] == "both"
        assert s["champion"] == "xgboost"
        # Seul XGBoost tourne (GNN préparé mais désactivé)
        assert should_run_xgboost_dag() is True
        assert should_run_stgcn_dag() is False

    def test_phase2_patrice_validates_gnn(self, monkeypatch):
        """Phase 2 : Patrice valide le GNN → on bascule sur stgcn seul."""
        # Étape 1 : switch le toggle prod
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "stgcn")
        # Étape 2 : stopper le retrain XGBoost (économie VPS)
        monkeypatch.setenv("LYONFLOW_XGBOOST_TRAINING", "false")
        # Étape 3 : activer le retrain GNN (préparation → prod)
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "true")

        r = ModelRegistry.get(60)
        s = r.status()
        assert s["active"] == "stgcn"
        assert s["champion"] == "stgcn"
        assert s["challenger"] is None
        # DAG XGBoost est skip, seul GNN tourne
        assert should_run_xgboost_dag() is False
        assert should_run_stgcn_dag() is True

    def test_phase3_rollback_to_xgboost(self, monkeypatch):
        """Phase 3 : si GNN foire en prod, rollback XGBoost."""
        monkeypatch.setenv("LYONFLOW_MODELS_ACTIVE", "xgboost")
        monkeypatch.setenv("LYONFLOW_STGCN_TRAINING", "false")

        r = ModelRegistry.get(60)
        s = r.status()
        assert s["active"] == "xgboost"
        assert s["champion"] == "xgboost"
        # Seul XGBoost tourne
        assert should_run_xgboost_dag() is True
        assert should_run_stgcn_dag() is False
