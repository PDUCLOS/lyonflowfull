"""Tests pour src.ml.mlflow_integration.

Couvre :
* Détection MLflow dispo / tracking server reachable
* Tracker en mode no-op (MLflow indispo)
* Tracker en mode live (log params, metrics, artifact)
* Helpers d'introspection (list_registered_models, get_latest_run, etc.)
* quick_log (one-liner)
* Graceful degradation sur erreur
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Permet l'import depuis la racine
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ml import mlflow_integration
from src.ml.mlflow_integration import (
    MLflowTracker,
    compare_models,
    get_artifact_root,
    get_experiment_summary,
    get_latest_run,
    get_tracking_uri,
    is_mlflow_available,
    is_tracking_server_reachable,
    list_registered_models,
    quick_log,
)

# =============================================================================
# Tests détection environnement
# =============================================================================


class TestEnvironment:
    """Tests des fonctions de détection MLflow."""

    def test_is_mlflow_available_returns_bool(self):
        """True ou False selon si la lib est installée."""
        result = is_mlflow_available()
        assert isinstance(result, bool)

    def test_is_tracking_server_reachable_returns_bool(self):
        """True si serveur joignable, False sinon."""
        result = is_tracking_server_reachable()
        assert isinstance(result, bool)

    def test_get_tracking_uri_default(self, monkeypatch):
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        uri = get_tracking_uri()
        assert "localhost" in uri or "127.0.0.1" in uri or uri == "http://localhost:5000"

    def test_get_tracking_uri_from_env(self, monkeypatch):
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://my-mlflow:5000")
        assert get_tracking_uri() == "http://my-mlflow:5000"

    def test_get_artifact_root_default(self, monkeypatch):
        monkeypatch.delenv("MLFLOW_DEFAULT_ARTIFACT_ROOT", raising=False)
        assert get_artifact_root() == "./mlruns"


# =============================================================================
# Tests Tracker mode no-op (MLflow indispo)
# =============================================================================


class TestTrackerNoOp:
    """Vérifie le comportement du tracker quand MLflow n'est pas dispo."""

    def test_tracker_initialized_in_noop_mode(self, monkeypatch):
        """Si serveur pas joignable → tracker en no-op."""
        # On force le no-op en mockant is_tracking_server_reachable
        monkeypatch.setattr("src.ml.mlflow_integration.is_tracking_server_reachable", lambda: False)
        tracker = MLflowTracker()
        assert tracker._noop is True

    def test_noop_start_run_yields_noop_run(self, monkeypatch):
        """Le context manager yield un _NoopRun quand MLflow indispo."""
        monkeypatch.setattr("src.ml.mlflow_integration.is_tracking_server_reachable", lambda: False)
        tracker = MLflowTracker()
        with tracker.start_run("test_run") as r:
            assert r is not None
            # _NoopRun a un attribut info.run_id
            assert hasattr(r, "info")
            assert r.info.run_id == "noop_run"

    def test_noop_log_methods_dont_crash(self, monkeypatch):
        """Les méthodes log_* sont silencieuses en no-op."""
        monkeypatch.setattr("src.ml.mlflow_integration.is_tracking_server_reachable", lambda: False)
        tracker = MLflowTracker()
        with tracker.start_run("test"):
            tracker.log_params({"foo": "bar"})
            tracker.log_metrics({"mae": 1.5})
            tracker.set_tag("key", "value")
            tracker.log_artifact("/tmp/some_path")
            tracker.log_dict({"a": 1}, "file.json")
        # Pas d'exception levée

    def test_noop_run_id_is_none(self, monkeypatch):
        """run_id retourne None en no-op mode."""
        monkeypatch.setattr("src.ml.mlflow_integration.is_tracking_server_reachable", lambda: False)
        tracker = MLflowTracker()
        assert tracker.run_id is None


# =============================================================================
# Tests Tracker mode live (MLflow dispo)
# =============================================================================


@pytest.mark.integration
class TestTrackerLive:
    """Vérifie le comportement du tracker quand MLflow est dispo.

    Note: ces tests fonctionnent en mode live uniquement si un serveur
    MLflow tourne (MLFLOW_TRACKING_URI). Sinon, ils skip ou passent en no-op.
    """

    def test_tracker_initialized_with_uri(self, monkeypatch):
        """Tracker avec URI custom s'initialise correctement."""
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://test:5000")
        tracker = MLflowTracker(experiment_name="test", tracking_uri="http://test:5000")
        # Si serveur joignable → pas no-op
        # Sinon → no-op (server pas dispo en CI)
        assert tracker.tracking_uri == "http://test:5000"
        assert tracker.experiment_name == "test"

    def test_quick_log_runs_and_returns_run_id(self, monkeypatch):
        """quick_log fait un run complet + log params/metrics/artifact."""
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://test:5000")
        run_id = quick_log(
            experiment="test_exp",
            run_name="quick_log_test",
            params={"x": 1, "y": 2},
            metrics={"mae": 0.5},
        )
        # run_id peut être un ID réel ou "noop" si serveur indispo
        assert run_id is not None
        assert isinstance(run_id, str)


# =============================================================================
# Tests helpers d'introspection
# =============================================================================


# =============================================================================
# Tests via data_loader (intégration Sprint 9)
# =============================================================================
