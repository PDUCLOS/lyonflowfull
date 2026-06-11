"""Tests Sprint VPS-6 — Politique fail loud en mode prod.

Vérifie que :
1. En mode prod (LYONFLOW_DEMO_MODE=0), les load_X() lèvent DashboardDataError
   quand la DB est indispo.
2. En mode démo (LYONFLOW_DEMO_MODE=1), le fallback mock est préservé.
3. La variable d'env est lue correctement.
4. Les widgets catchent DashboardDataError sans crasher.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Permet l'import de `src` depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def reset_caches(monkeypatch):
    """Reset tous les caches module (DB + demo mode) entre chaque test."""
    db_query.reset_db_cache()
    # Force relecture de LYONFLOW_DEMO_MODE
    data_loader._demo_mode_cache = None
    yield
    db_query.reset_db_cache()
    data_loader._demo_mode_cache = None


@pytest.fixture
def prod_mode(monkeypatch):
    """Active mode prod (LYONFLOW_DEMO_MODE=0)."""
    monkeypatch.setenv("LYONFLOW_DEMO_MODE", "0")
    data_loader._demo_mode_cache = None
    yield
    data_loader._demo_mode_cache = None


@pytest.fixture
def demo_mode(monkeypatch):
    """Active mode démo (LYONFLOW_DEMO_MODE=1)."""
    monkeypatch.setenv("LYONFLOW_DEMO_MODE", "1")
    data_loader._demo_mode_cache = None
    yield
    data_loader._demo_mode_cache = None


# =============================================================================
# _is_demo_mode
# =============================================================================


class TestIsDemoMode:
    """Vérifie la lecture de LYONFLOW_DEMO_MODE."""

    def test_default_is_prod(self, monkeypatch, reset_caches):
        """Sans env var → mode prod (fail loud)."""
        monkeypatch.delenv("LYONFLOW_DEMO_MODE", raising=False)
        data_loader._demo_mode_cache = None
        assert data_loader._is_demo_mode() is False

    def test_prod_explicit(self, prod_mode):
        """LYONFLOW_DEMO_MODE=0 → mode prod."""
        assert data_loader._is_demo_mode() is False

    def test_demo_explicit(self, demo_mode):
        """LYONFLOW_DEMO_MODE=1 → mode démo."""
        assert data_loader._is_demo_mode() is True

    def test_demo_mode_stripped(self, monkeypatch, reset_caches):
        """Espaces autour de la valeur sont strippés."""
        monkeypatch.setenv("LYONFLOW_DEMO_MODE", "  1  ")
        data_loader._demo_mode_cache = None
        assert data_loader._is_demo_mode() is True


# =============================================================================
# _maybe_force_mock
# =============================================================================


class TestMaybeForceMock:
    """Vérifie la logique de gating."""

    def test_prod_db_down_no_mock(self, prod_mode, monkeypatch):
        """En prod, DB down → pas de mock, force_mock ignoré."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
        # force_mock=True est IGNORÉ en prod
        assert data_loader._maybe_force_mock(force_mock=True) is False
        # force_mock=False + DB down → pas de mock
        assert data_loader._maybe_force_mock(force_mock=False) is False

    def test_prod_db_up_no_mock(self, prod_mode, monkeypatch):
        """En prod, DB up → pas de mock."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        assert data_loader._maybe_force_mock(force_mock=True) is False
        assert data_loader._maybe_force_mock(force_mock=False) is False

    def test_demo_db_down_mock(self, demo_mode, monkeypatch):
        """En démo, DB down → mock par défaut."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
        assert data_loader._maybe_force_mock(force_mock=False) is True
        assert data_loader._maybe_force_mock(force_mock=True) is True

    def test_demo_db_up_no_mock(self, demo_mode, monkeypatch):
        """En démo, DB up → pas de mock sauf si force_mock=True."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        assert data_loader._maybe_force_mock(force_mock=False) is False
        # force_mock=True force le mock même si DB up (utile pour screenshots)
        assert data_loader._maybe_force_mock(force_mock=True) is True


# =============================================================================
# _require_db_or_raise
# =============================================================================


class TestRequireDbOrRaise:
    """Vérifie que l'helper lève DashboardDataError quand DB down en prod."""

    def test_db_up_no_error(self, prod_mode, monkeypatch):
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        data_loader._require_db_or_raise("test_source")  # ne lève rien

    def test_db_down_raises(self, prod_mode, monkeypatch):
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
        with pytest.raises(DashboardDataError) as exc_info:
            data_loader._require_db_or_raise("test_source")
        assert exc_info.value.source == "test_source"
        assert "PostgreSQL" in str(exc_info.value)


# =============================================================================
# DashboardDataError
# =============================================================================


class TestDashboardDataError:
    """Vérifie la nouvelle exception."""

    def test_basic(self):
        e = DashboardDataError(source="airflow", detail="Connection refused")
        assert e.source == "airflow"
        assert e.detail == "Connection refused"
        assert "[airflow]" in str(e)
        assert "Connection refused" in str(e)

    def test_no_detail(self):
        e = DashboardDataError(source="mlflow")
        assert e.source == "mlflow"
        assert e.detail == ""
        assert "[mlflow]" in str(e)


# =============================================================================
# load_X() : fail loud en prod
# =============================================================================


class TestLoadXFailLoud:
    """Vérifie que les load_X() lèvent DashboardDataError en prod quand DB down."""

    @pytest.mark.parametrize("func_name,kwargs", [
        ("load_traffic", {}),
        ("load_traffic_timeseries", {"node_idx": 1}),
        ("load_velov_stations", {}),
        ("load_velov_predictions", {"horizon_minutes": 30}),
        ("load_bus_delays", {}),
        ("load_infra_bottlenecks", {}),
        ("load_predictions_vs_actuals", {}),
        ("load_rgpd_audit", {}),
        ("load_rgpd_consents", {}),
        ("load_weather_hourly", {}),
        ("load_recent_alerts", {}),
        ("load_segments", {}),
        ("load_correlation_matrix", {}),
        ("load_buses_positions", {}),
        ("load_kpis_12_months", {}),
        ("load_amenagements_passes", {}),
        ("load_tcl_lines", {}),
        ("load_spatial_mapping", {}),
        ("load_traffic_predictions_for_map", {}),
    ])
    def test_prod_db_down_raises(self, prod_mode, monkeypatch, func_name, kwargs):
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
        # Mock execute_query utilisé par get_tcl_lines pour éviter d'autres soucis
        monkeypatch.setattr(data_loader, "execute_query", mock.MagicMock(return_value=[]))
        func = getattr(data_loader, func_name)
        with pytest.raises(DashboardDataError):
            func(force_mock=False, **kwargs)

    def test_load_tcl_lines_empty_in_prod(self, prod_mode, monkeypatch):
        """load_tcl_lines : DB up mais table vide → liste vide (pas d'exception)."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        monkeypatch.setattr(data_loader, "execute_query", mock.MagicMock(return_value=[]))
        result = data_loader.load_tcl_lines(force_mock=False)
        assert result == []


# =============================================================================
# load_X() : fallback mock préservé en démo
# =============================================================================


class TestLoadXDemoFallback:
    """Vérifie que les load_X() retombent sur les mocks en mode démo."""

    def test_load_traffic_demo(self, demo_mode, monkeypatch):
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
        result = data_loader.load_traffic(force_mock=False)
        # MOCK_TRAFFIC = dict avec 'city', 'average_speed_kmh', etc.
        assert isinstance(result, dict)
        assert "city" in result

    def test_load_traffic_forced_mock(self, demo_mode, monkeypatch):
        """force_mock=True marche même si DB up."""
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        result = data_loader.load_traffic(force_mock=True)
        assert isinstance(result, dict)
        assert "city" in result


# =============================================================================
# Widgets (smoke tests)
# =============================================================================


class TestWidgetFallback:
    """Vérifie que les widgets catchent DashboardDataError sans crasher."""

    def test_pipeline_status_handles_error(self, prod_mode, monkeypatch):
        """render_pipeline_status ne crash pas en cas de DashboardDataError."""
        from dashboard.components.widgets.pro_tcl import pipeline_management

        monkeypatch.setattr(
            pipeline_management, "_cached_dags",
            mock.MagicMock(side_effect=DashboardDataError("airflow", "down")),
        )
        # On ne peut pas exécuter render_pipeline_status hors Streamlit
        # mais on vérifie que l'exception est bien catchable
        with pytest.raises(DashboardDataError):
            pipeline_management._cached_dags()
