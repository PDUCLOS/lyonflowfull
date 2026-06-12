"""Tests pour les widgets, pages et PDF Élu."""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_mock_data_elu_imports():
    from tests.fixtures.mock_data import elu

    assert hasattr(elu, "KPI_12_MONTHS")
    assert hasattr(elu, "BOTTLENECKS_TOP_10")
    assert hasattr(elu, "AMENAGEMENTS_PASSES")
    assert hasattr(elu, "PROJETS_PLANIFIES")


def test_kpis_have_5_entries():
    from tests.fixtures.mock_data.elu import KPI_12_MONTHS

    assert len(KPI_12_MONTHS) == 5
    required = ["part_modale_tc", "ponctualite_reseau", "co2_evite", "bottlenecks_actifs", "satisfaction_usager"]
    for k in required:
        assert k in KPI_12_MONTHS
        kpi = KPI_12_MONTHS[k]
        for field in ("label", "current", "delta_ytd", "target_2026", "history"):
            assert field in kpi, f"{k} manque {field}"
        assert len(kpi["history"]) == 12


def test_bottlenecks_count():
    from tests.fixtures.mock_data.elu import BOTTLENECKS_TOP_10

    assert len(BOTTLENECKS_TOP_10) == 10
    for b in BOTTLENECKS_TOP_10:
        for field in (
            "rank",
            "zone",
            "lines_impacted",
            "voyageurs_jour",
            "gain_min",
            "cout_M_euros",
            "roi_mois",
            "delai_mois",
        ):
            assert field in b, f"Bottleneck {b.get('rank')} manque {field}"
        # ROI doit être calculé (entier)
        assert isinstance(b["roi_mois"], int | float)
        assert b["roi_mois"] > 0


def test_amenagements_passes_have_avant_apres():
    from tests.fixtures.mock_data.elu import AMENAGEMENTS_PASSES

    assert len(AMENAGEMENTS_PASSES) >= 5
    for a in AMENAGEMENTS_PASSES:
        assert "avant" in a
        assert "apres" in a
        assert "nom" in a
        assert "annee" in a


def test_widget_modules_elu_importable():
    from dashboard.components.widgets import elu

    assert hasattr(elu, "render_kpi_cards")
    assert hasattr(elu, "render_executive_summary")
    assert hasattr(elu, "render_trend_chart")
    assert hasattr(elu, "render_top_decisions")
    assert hasattr(elu, "render_news_section")
    assert hasattr(elu, "render_bottleneck_ranking")
    assert hasattr(elu, "render_bottleneck_map")
    assert hasattr(elu, "render_roi_calculator")
    assert hasattr(elu, "render_project_selector")
    assert hasattr(elu, "render_delta_kpis")
    assert hasattr(elu, "render_map_painter")
    assert hasattr(elu, "render_impact_projection")
    assert hasattr(elu, "render_cost_estimate")
    assert hasattr(elu, "render_pdf_generator")
    assert hasattr(elu, "render_template_selector")
    assert hasattr(elu, "render_slide_builder")


def test_elu_pages_exist():
    pages_dir = WORKSPACE / "dashboard" / "pages"
    expected = [
        "Elu_1_Synthese.py",
        "Elu_2_Bottlenecks.py",
        "Elu_3_Avant_Apres.py",
        "Elu_4_Simulateur.py",
        "Elu_5_Rapport.py",
    ]
    for page in expected:
        path = pages_dir / page
        assert path.exists(), f"Page manquante : {path}"
        content = path.read_text(encoding="utf-8")
        assert "apply_persona_guard" in content
        assert 'expected_persona="elu"' in content


def test_synthese_has_5_kpi_cards():
    """La page Synthèse doit afficher 5 KPI cards."""
    content = (WORKSPACE / "dashboard" / "pages" / "Elu_1_Synthese.py").read_text(encoding="utf-8")
    assert "render_kpi_cards" in content
    # Vérifier que render_kpi_cards est appelé une fois (sans args = 5 KPIs par défaut)
    assert content.count("render_kpi_cards()") >= 1
