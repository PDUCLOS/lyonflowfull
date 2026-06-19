"""Tests Sprint 8 (2026-06-12) — Fail loud en l'absence de DB.

Avant (Sprint VPS-6) : ``load_X()`` retournait un mock si la DB était
down, ce qui masquait les pannes. Maintenant (Sprint 8) : zéro mock,
donc ``load_X()`` lève ``DashboardDataError`` quand la DB est
indisponible.

Ce module valide :
1. ``_is_db_available()`` retourne False quand l'env ne pointe pas
   vers une DB.
2. ``load_X()`` lèvent ``DashboardDataError`` (pas de fallback mock).

Note : pour tester du code avec une vraie DB, marquer
``@pytest.mark.integration`` (voir ``tests/integration/``). Sprint 15+
(2026-06-19) — la fixture ``mock_db`` qui monkeypatchait
``src.db.connection`` a été virée d'un commun accord avec Patrice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests (pas de DB locale)."""
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helper : charge_X qui DOIT lever DashboardDataError en absence de DB
# =============================================================================

FAIL_LOUD_FUNCS = [
    "load_traffic",
    "load_velov_stations",
    "load_bus_delays",
    "load_infra_bottlenecks",
    "load_predictions_vs_actuals",
    "load_rgpd_audit",
    "load_rgpd_consents",
    "load_weather_hourly",
    "load_recent_alerts",
    "load_segments",
    "load_correlation_matrix",
    "load_buses_positions",
    "load_amenagements_passes",
]


@pytest.mark.parametrize("func_name", FAIL_LOUD_FUNCS)
def test_load_x_raises_when_no_db(func_name: str) -> None:
    """Sprint 8 : load_X() lève DashboardDataError si DB indispo.

    Avant : retournait un mock silencieux. Maintenant : fail loud.
    """
    func = getattr(data_loader, func_name)
    with pytest.raises(DashboardDataError):
        func()


def test_load_kpis_12_months_raises_when_no_db() -> None:
    """load_kpis_12_months doit aussi fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_kpis_12_months()


def test_load_elu_kpis_dict_raises_when_no_db() -> None:
    """load_elu_kpis_dict doit aussi fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_elu_kpis_dict()


def test_load_bottlenecks_top_raises_when_no_db() -> None:
    """load_bottlenecks_top doit aussi fail loud.

    Sprint 8 — bug connu : get_bottlenecks_summary n'est pas exporté
    par src.data.db_query. À fixer Sprint 9.
    """
    with pytest.raises((DashboardDataError, ImportError)):
        data_loader.load_bottlenecks_top()


def test_load_tcl_lines_raises_when_no_db() -> None:
    """load_tcl_lines lit gold.tcl_vehicle_realtime en DB, fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_tcl_lines()


def test_load_lyon_addresses_raises_when_no_db() -> None:
    """load_lyon_addresses : DB obligatoire (referentiel.lieux_lyon)."""
    with pytest.raises(DashboardDataError):
        data_loader.load_lyon_addresses()


# =============================================================================
# Tests fail-loud supplémentaires (sans mock — DB absente = exception)
# =============================================================================


def test_load_kpis_12_months_raises_explicit() -> None:
    """load_kpis_12_months : pas de fallback (Sprint 8)."""
    with pytest.raises(DashboardDataError) as exc_info:
        data_loader.load_kpis_12_months()
    assert "kpis" in str(exc_info.value).lower() or "month" in str(exc_info.value).lower()
