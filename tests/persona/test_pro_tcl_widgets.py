"""Tests pour les widgets et pages Pro TCL."""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_mock_data_pro_tcl_imports():
    from tests.fixtures.mock_data import pro_tcl

    assert hasattr(pro_tcl, "TCL_LINES_PRO")
    assert hasattr(pro_tcl, "SEGMENTS")
    assert hasattr(pro_tcl, "OTP_GRID")
    assert hasattr(pro_tcl, "LINE_KPIS")
    assert hasattr(pro_tcl, "ALL_BUSES")
    assert hasattr(pro_tcl, "PREDICTED_ALERTS")
    assert hasattr(pro_tcl, "TOP_BOTTLENECKS")
    assert hasattr(pro_tcl, "DIAGNOSIS_COLORS")
    assert hasattr(pro_tcl, "DIAGNOSIS_LABELS")


def test_tcl_lines_pro_count():
    from tests.fixtures.mock_data.pro_tcl import TCL_LINES_PRO

    assert len(TCL_LINES_PRO) >= 10, f"Attendu ≥ 10 lignes, trouvé {len(TCL_LINES_PRO)}"


def test_segments_have_classification():
    from tests.fixtures.mock_data.pro_tcl import SEGMENTS

    assert len(SEGMENTS) >= 25  # 5 lignes × 5 segments (C3, C13, T1, T3, M_A)
    for s in SEGMENTS:
        assert "line_id" in s
        assert "name" in s
        assert "bus_state" in s
        assert s["bus_state"] in ("on_time", "delayed")
        assert "traffic_state" in s
        assert s["traffic_state"] in ("fluid", "jammed")
        assert "diagnosis" in s
        assert s["diagnosis"] in ("ok", "infra", "operations", "bus_lane_ok")


def test_otp_grid_lyon_lines():
    from tests.fixtures.mock_data.pro_tcl import LINE_BASE_OTP, OTP_GRID

    assert len(OTP_GRID) >= 10
    for line_id, base in LINE_BASE_OTP.items():
        assert line_id in OTP_GRID
        otp_values = []
        for date, hours in OTP_GRID[line_id].items():
            assert len(hours) == 24
            for h in hours:
                assert 60.0 <= h <= 98.0, f"OTP hors plage pour {line_id} {date} h={h}"
                otp_values.append(h)
        avg = sum(otp_values) / len(otp_values)
        # L'OTP moyen doit être proche de la base (variation autorisée ±10)
        assert abs(avg - base) < 10, f"OTP moyen {avg} trop loin de base {base} pour {line_id}"


def test_line_kpis_have_all_fields():
    from tests.fixtures.mock_data.pro_tcl import LINE_KPIS

    for line_id, k in LINE_KPIS.items():
        for field in ("otp_pct", "avg_delay_min", "frequency_min", "load_pct", "trend", "trend_delta"):
            assert field in k, f"{line_id} manque {field}"


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
