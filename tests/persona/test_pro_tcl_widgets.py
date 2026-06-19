"""Tests pour les widgets et pages Pro TCL."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# Sprint 15 prep (2026-06-19) — 5 tests mock-constants supprimés (test_mock_data_pro_tcl_imports,
# test_tcl_lines_pro_count, test_segments_have_classification, test_otp_grid_lyon_lines,
# test_line_kpis_have_all_fields). Backup: ~/.mavis/backups/sprint15-prep/persona/test_pro_tcl_widgets.py


def test_widget_modules_pro_tcl_importable():
    from dashboard.components.widgets import pro_tcl

    # Vérifier que les fonctions principales sont exposées
    assert hasattr(pro_tcl, "render_network_map")
    assert hasattr(pro_tcl, "render_alert_ticker")
    assert hasattr(pro_tcl, "render_otp_heatmap")
    assert hasattr(pro_tcl, "render_correlation_matrix")
    assert hasattr(pro_tcl, "render_cause_analysis")
    assert hasattr(pro_tcl, "render_frequency_slider")
    assert hasattr(pro_tcl, "render_otp_projection")
    assert hasattr(pro_tcl, "render_saeiv_export")
    assert hasattr(pro_tcl, "render_line_kpis")
    assert hasattr(pro_tcl, "render_segment_table")


def test_pro_tcl_pages_exist():
    pages_dir = WORKSPACE / "dashboard" / "pages"
    expected = [
        "Pro_1_PCC_Live.py",
        "Pro_2_Heatmap_OTP.py",
        "Pro_3_Correlation.py",
        "Pro_4_Simulateur.py",
        "Pro_5_Export.py",
    ]
    for page in expected:
        path = pages_dir / page
        assert path.exists(), f"Page manquante : {path}"
        content = path.read_text(encoding="utf-8")
        assert "apply_persona_guard" in content
        assert 'expected_persona="pro_tcl"' in content


def test_correlation_page_uses_correlation_matrix():
    """L'USP technique doit être utilisée dans Pro_3_Correlation."""
    content = (WORKSPACE / "dashboard" / "pages" / "Pro_3_Correlation.py").read_text(encoding="utf-8")
    assert "render_correlation_matrix" in content
    assert "render_cause_analysis" in content


# =============================================================================
# Sprint 13+ (2026-06-18) — Widget cohérence TomTom × Grand Lyon
# =============================================================================


def test_coherence_scatter_widget_imports():
    """Le widget coherence_scatter doit être importable."""
    from dashboard.components.widgets.pro_tcl.coherence_scatter import render_coherence_scatter

    assert callable(render_coherence_scatter)


def test_coherence_scatter_exported_from_pro_tcl():
    """Le widget doit être listé dans le __all__ de pro_tcl."""
    from dashboard.components.widgets.pro_tcl import (
        render_coherence_scatter as r1,
    )
    from dashboard.components.widgets.pro_tcl.coherence_scatter import (
        render_coherence_scatter as r2,
    )
    assert r1 is r2


def test_coherence_scatter_status_labels_complete():
    """Les 4 status SQL ont un label FR."""
    from dashboard.components.widgets.pro_tcl.coherence_scatter import (
        STATUS_COLORS,
        STATUS_LABELS,
    )
    assert set(STATUS_LABELS.keys()) == {"ok", "minor_drift", "drift", "no_data"}
    assert set(STATUS_COLORS.keys()) == {"ok", "minor_drift", "drift", "no_data"}
    # Tous les labels FR sont non vides
    for label in STATUS_LABELS.values():
        assert label and isinstance(label, str)
    # Toutes les couleurs sont des hex
    for color in STATUS_COLORS.values():
        assert color.startswith("#") and len(color) == 7


def test_correlation_page_includes_coherence_widget():
    """Sprint 13+ — Pro_3_Correlation doit aussi rendre la cohérence TomTom."""
    content = (WORKSPACE / "dashboard" / "pages" / "Pro_3_Correlation.py").read_text(encoding="utf-8")
    assert "render_coherence_scatter" in content
    assert "coherence_scatter" in content


def test_data_cache_has_coherence_helpers():
    """Sprint 13+ — cached_tomtom_coherence et cached_tomtom_gl_drift existent."""
    from dashboard.components.data_cache import (
        cached_tomtom_coherence,
        cached_tomtom_gl_drift,
    )
    assert callable(cached_tomtom_coherence)
    assert callable(cached_tomtom_gl_drift)
