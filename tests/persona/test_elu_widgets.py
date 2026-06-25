"""Tests pour les widgets, pages et PDF Élu."""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# Sprint 15 prep (2026-06-19) — 4 tests mock-constants supprimés (test_mock_data_elu_imports,
# test_kpis_have_5_entries, test_bottlenecks_count, test_amenagements_passes_have_avant_apres).
# Backup local hors-repo: ~/.mavis/backups/sprint15-prep/persona/test_elu_widgets.py


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


# =============================================================================
# Sprint 22+ (2026-06-25) — Tests Fix 9 bugs Elu_2_Bottlenecks
# =============================================================================
# Vérifie que les widgets ont bien été migrés :
# - Bug 2 : bottleneck_map n'a plus de dict coords hardcodé, utilise lat/lon
# - Bug 4 : bottleneck_ranking affiche le diagnostic
# - Bug 7 : roi_calculator affiche le diagnostic sélectionné
# =============================================================================


def test_bottleneck_map_no_hardcoded_coords():
    """Bug 2 fix : suppression du dict coords hardcodé (10 rues), remplacé
    par lecture lat/lon depuis le dict bottleneck."""
    content = (WORKSPACE / "dashboard" / "components" / "widgets" / "elu" / "bottleneck_map.py").read_text(
        encoding="utf-8"
    )
    # Le dict coords avec "Rue Garibaldi" doit avoir disparu
    assert "Rue Garibaldi" not in content, "Bug 2 : le dict coords hardcodé doit être supprimé"
    assert "Cours Lafayette" not in content, "Bug 2 : idem Cours Lafayette"
    # Le widget doit lire b.get("lat") / b.get("lon")
    assert 'b.get("lat")' in content or "b.get('lat')" in content, (
        "Bug 2 : bottleneck_map doit lire lat/lon depuis le dict bottleneck"
    )
    assert 'b.get("lon")' in content or "b.get('lon')" in content


def test_bottleneck_map_color_by_diagnosis():
    """Bug 4 fix : couleur des marqueurs selon le diagnostic (pas le ROI)."""
    content = (WORKSPACE / "dashboard" / "components" / "widgets" / "elu" / "bottleneck_map.py").read_text(
        encoding="utf-8"
    )
    assert "_DIAGNOSIS_FOLIUM_COLOR" in content
    # Au moins les 4 diagnostics doivent être mappés
    for diag in ("infra", "operations", "bus_lane_ok", "ok"):
        assert f'"{diag}"' in content or f"'{diag}'" in content, f"Diagnostic manquant dans le mapping couleur : {diag}"


def test_bottleneck_ranking_has_diagnostic_column():
    """Bug 4 fix : colonne Diagnostic ajoutée au tableau ranking."""
    content = (WORKSPACE / "dashboard" / "components" / "widgets" / "elu" / "bottleneck_ranking.py").read_text(
        encoding="utf-8"
    )
    assert "_DIAGNOSIS_DISPLAY" in content
    assert "Diagnostic" in content
    # Vérifie que les 4 diagnostics sont gérés
    for diag in ("infra", "operations", "bus_lane_ok", "ok"):
        assert diag in content


def test_roi_calculator_shows_diagnosis():
    """Bug 7 fix : le calculateur ROI affiche le diagnostic sélectionné."""
    content = (WORKSPACE / "dashboard" / "components" / "widgets" / "elu" / "roi_calculator.py").read_text(
        encoding="utf-8"
    )
    assert "_DIAGNOSIS_ROI" in content
    assert "Diagnostic" in content
    # Vérifie qu'on lit b.get("diagnosis")
    assert 'b.get("diagnosis"' in content


def test_load_bottlenecks_top_no_hardcoded_values():
    """Bug 1/7 fix : aucune fonction linéaire de l'index ``i`` dans
    load_bottlenecks_top (anciennement ``5 + i``, ``2.5 - i * 0.15``…)."""
    import inspect

    from src.data import data_loader

    src = inspect.getsource(data_loader.load_bottlenecks_top)
    # Les anciennes formules hardcodées doivent avoir disparu
    assert "5 + i" not in src, "Bug 1 : gain_min hardcodé '5 + i' doit être viré"
    assert "2.5 - i * 0.15" not in src, "Bug 1 : cout_M_euros hardcodé doit être viré"
    assert "18 + i * 3" not in src, "Bug 7 : roi_mois hardcodé doit être viré"
    assert "6 + i * 2" not in src, "Bug 1 : delai_mois hardcodé doit être viré"
    # Le remplacement doit utiliser avg_delay_s + diagnosis
    assert "avg_bus_delay_s" in src
    assert "COUT_PAR_DIAGNOSTIC" in src


def test_bottleneck_description_is_diagnostic_driven():
    """Bug 1/4 fix : la description reflète le diagnostic (pas générique)."""
    import inspect

    from src.data import data_loader

    src = inspect.getsource(data_loader._build_bottleneck_description)
    # La fonction de build ne doit PAS contenir la chaîne "Amélioration #"
    # comme template (la docstring peut y faire référence pour le "avant").
    # On vérifie donc la présence de templates par diagnostic, ce qui prouve
    # que la description est bel et bien dérivée du diagnostic.
    for diag in ("infra", "operations", "bus_lane_ok", "ok"):
        assert f'"{diag}"' in src, f"Template manquant pour le diagnostic '{diag}' dans _build_bottleneck_description"
    # Vérifie aussi qu'au moins un template commence par "Aménagement"
    # (preuve qu'on n'utilise plus le format générique "Amélioration #N").
    assert "Aménagement" in src or "Ajustement" in src, (
        "Description doit utiliser des verbes d'action liés au diagnostic"
    )
