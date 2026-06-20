"""Tests Sprint 16 Axe A — Backtest dashboard widget (smoke + structure).

Vérifie que le widget backtest_dashboard s'importe correctement et expose
les bonnes fonctions helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_backtest_dashboard_module_importable():
    """Le module backtest_dashboard doit s'importer sans erreur."""
    from dashboard.components.widgets.pro_tcl import backtest_dashboard

    assert hasattr(backtest_dashboard, "render_backtest_dashboard")
    assert callable(backtest_dashboard.render_backtest_dashboard)


def test_backtest_dashboard_exported_from_pro_tcl():
    """render_backtest_dashboard doit être exporté par le package pro_tcl."""
    from dashboard.components.widgets.pro_tcl import render_backtest_dashboard

    assert callable(render_backtest_dashboard)


def test_backtest_dashboard_helpers_present():
    """Le widget doit exposer les helpers internes _scatter, _mae_temporal, _accuracy_distribution."""
    from dashboard.components.widgets.pro_tcl import backtest_dashboard

    assert hasattr(backtest_dashboard, "_scatter_xgb_vs_tomtom")
    assert hasattr(backtest_dashboard, "_mae_temporal_chart")
    assert hasattr(backtest_dashboard, "_accuracy_distribution")
    assert hasattr(backtest_dashboard, "_compute_kpis")
    # _compute_kpis doit retourner un dict avec les 4 clés
    import pandas as pd

    empty_df = pd.DataFrame()
    k = backtest_dashboard._compute_kpis(empty_df)
    assert "mae_kmh" in k
    assert "mape_pct" in k
    assert "p90_kmh" in k
    assert "n_pairs" in k
    assert k["n_pairs"] == 0


def test_backtest_dashboard_thresholds_defined():
    """Les seuils MAE_GREEN/YELLOW doivent être définis et cohérents."""
    from dashboard.components.widgets.pro_tcl import backtest_dashboard

    assert backtest_dashboard.MAE_GREEN_THRESHOLD < backtest_dashboard.MAE_YELLOW_THRESHOLD
    assert backtest_dashboard.MAE_GREEN_THRESHOLD > 0
