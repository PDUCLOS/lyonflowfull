"""Tests (2026-06-19) — Helpers bus × trafic spatialisé (Axe 3).

Vérifie que les helpers ``get_bus_traffic_spatial``,
``get_bus_traffic_spatial_diagnosis_counts`` et leurs wrappers ``load_*``
respectent la politique zéro mock de
* Helpers bas-niveau (db_query) → DataFrame vide si DB indispo.
* Wrappers data_loader → lèvent ``DashboardDataError`` si DB indispo ou
  si la MV est vide.

Voir ``docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`` (Axe 3, 2026-06-19).
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
    """Force ``_is_db_available = False`` pour ces tests.

    Patch dans DEUX modules (db_query + data_loader) car data_loader
    importe ``_is_db_available`` via ``from ... import`` ce qui crée une
    seconde référence. Sans le patch data_loader, les load_X() ne lèvent
    pas ``DashboardDataError`` quand le monkeypatch db_query est bypass
    (cf. test_db_query_and_data_loader.py pour l'explication complète).
    """
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helpers data_loader — fail loud quand DB indispo
# =============================================================================


def test_load_bus_traffic_spatial_raises_when_no_db() -> None:
    with pytest.raises(DashboardDataError):
        data_loader.load_bus_traffic_spatial()


def test_load_bus_traffic_spatial_with_line_raises_when_no_db() -> None:
    with pytest.raises(DashboardDataError):
        data_loader.load_bus_traffic_spatial(line_ref="T1")


def test_load_bus_traffic_spatial_diagnosis_counts_raises_when_no_db() -> None:
    with pytest.raises(DashboardDataError):
        data_loader.load_bus_traffic_spatial_diagnosis_counts()


def test_load_bus_traffic_spatial_diagnosis_counts_with_line_raises() -> None:
    with pytest.raises(DashboardDataError):
        data_loader.load_bus_traffic_spatial_diagnosis_counts(line_ref="T1")


# =============================================================================
# Helpers db_query — DataFrame vide si DB indispo
# =============================================================================


def test_get_bus_traffic_spatial_returns_empty_when_no_db() -> None:
    df = db_query.get_bus_traffic_spatial(limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_bus_traffic_spatial_with_line_returns_empty() -> None:
    df = db_query.get_bus_traffic_spatial(line_ref="T1", limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_bus_traffic_spatial_diagnosis_counts_returns_empty() -> None:
    df = db_query.get_bus_traffic_spatial_diagnosis_counts()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_bus_traffic_spatial_diagnosis_counts_with_line_returns_empty() -> None:
    df = db_query.get_bus_traffic_spatial_diagnosis_counts(line_ref="T1")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# =============================================================================
# Widget helpers — diagnostic counts + KPI logic
# =============================================================================


def test_widget_diagnosis_counts_empty() -> None:
    from dashboard.components.widgets.pro_tcl.bus_traffic_spatial import (
        SPATIAL_DIAGNOSIS_COLORS,
        _diagnosis_counts,
    )

    counts = _diagnosis_counts(pd.DataFrame())
    assert set(counts.keys()) == set(SPATIAL_DIAGNOSIS_COLORS.keys())
    assert all(v == 0 for v in counts.values())


def test_widget_diagnosis_counts_with_data() -> None:
    from dashboard.components.widgets.pro_tcl.bus_traffic_spatial import (
        _diagnosis_counts,
    )

    df = pd.DataFrame(
        {
            "diagnosis": ["infra", "infra", "ok", "operations", "bus_lane_ok"],
        }
    )
    counts = _diagnosis_counts(df)
    assert counts["infra"] == 2
    assert counts["ok"] == 1
    assert counts["operations"] == 1
    assert counts["bus_lane_ok"] == 1


def test_widget_thresholds_consistent() -> None:
    from dashboard.components.widgets.pro_tcl.bus_traffic_spatial import (
        DELAY_THRESHOLD,
        SPEED_THRESHOLD,
    )

    assert DELAY_THRESHOLD == 120
    assert SPEED_THRESHOLD == 25
