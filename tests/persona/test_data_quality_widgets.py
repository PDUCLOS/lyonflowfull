"""Tests Sprint 16 Axe B — Data Quality widgets (smoke + classification)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# =============================================================================
# data_quality_badge
# =============================================================================


def test_data_quality_badge_module_importable():
    from dashboard.components.widgets.elu import data_quality_badge

    assert callable(data_quality_badge.render_data_quality_badge)


def test_data_quality_badge_exported_from_elu():
    from dashboard.components.widgets.elu import render_data_quality_badge

    assert callable(render_data_quality_badge)


def test_data_quality_badge_classify_all_healthy():
    from dashboard.components.widgets.elu import data_quality_badge

    color, icon, msg = data_quality_badge._classify(
        n_healthy=8, n_dead=0, n_stale=0, score=94.0
    )
    assert color == "#4CAF50"
    assert icon == "🟢"
    assert "OK" in msg


def test_data_quality_badge_classify_dead():
    from dashboard.components.widgets.elu import data_quality_badge

    color, icon, msg = data_quality_badge._classify(
        n_healthy=6, n_dead=1, n_stale=0, score=61.0
    )
    assert color == "#F44336"
    assert icon == "🔴"
    assert "panne" in msg.lower()


def test_data_quality_badge_classify_stale():
    from dashboard.components.widgets.elu import data_quality_badge

    color, icon, msg = data_quality_badge._classify(
        n_healthy=7, n_dead=0, n_stale=1, score=82.0
    )
    assert color == "#FF9800"
    assert icon == "🟡"
    assert "stale" in msg.lower()


def test_data_quality_badge_global_score_weights():
    """Vérifie que _global_score pondère trafic plus que air_quality."""
    from dashboard.components.widgets.elu import data_quality_badge

    df = pd.DataFrame({
        "source": ["bronze.trafic_boucles", "bronze.air_quality"],
        "health_score": [100, 0],
    })
    score = data_quality_badge._global_score(df)
    # trafic (poids 3) + air (poids 1) → weighted = 100*3 + 0*1 = 300
    # total_weight = 4 → score = 75
    assert 70 < score < 80


# =============================================================================
# source_health_monitor
# =============================================================================


def test_source_health_monitor_module_importable():
    from dashboard.components.widgets.pro_tcl import source_health_monitor

    assert callable(source_health_monitor.render_source_health_monitor)


def test_source_health_monitor_exported_from_pro_tcl():
    from dashboard.components.widgets.pro_tcl import render_source_health_monitor

    assert callable(render_source_health_monitor)


def test_source_health_monitor_weights_defined():
    """Les poids doivent favoriser trafic (3) > TCL (2) = Vélov (2) > reste (1)."""
    from dashboard.components.widgets.pro_tcl import source_health_monitor

    assert source_health_monitor.SOURCE_WEIGHTS["bronze.trafic_boucles"] == 3
    assert source_health_monitor.SOURCE_WEIGHTS["bronze.tcl_vehicles"] == 2
    assert source_health_monitor.SOURCE_WEIGHTS["bronze.velov"] == 2
    assert source_health_monitor.SOURCE_WEIGHTS["bronze.meteo"] == 1


def test_source_health_monitor_global_score_zero_when_empty():
    from dashboard.components.widgets.pro_tcl import source_health_monitor

    assert source_health_monitor._global_score(pd.DataFrame()) == 0.0
