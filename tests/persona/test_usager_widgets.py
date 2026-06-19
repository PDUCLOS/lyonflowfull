"""Tests pour les widgets et pages Usager.

Lance avec : cd /Users/patriceduclos/Documents/Lyonfull && python -m pytest tests/persona/test_usager_widgets.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# Sprint 15 prep (2026-06-19) — 4 tests mock-constants supprimés (test_mock_data_usager_imports,
# test_tcl_lines_have_required_fields, test_velov_stations_have_lyon_coordinates,
# test_mock_alerts_have_required_fields). Backup: ~/.mavis/backups/sprint15-prep/persona/test_usager_widgets.py


def test_widget_modules_importable():
    """Tous les modules widgets usager doivent s'importer."""
    from dashboard.components.widgets import usager

    assert hasattr(usager, "render_search_bar")
    assert hasattr(usager, "render_weather_widget")
    assert hasattr(usager, "render_velov_widget")
    assert hasattr(usager, "render_traffic_widget")
    assert hasattr(usager, "render_alert_card")
    assert hasattr(usager, "render_alert_timeline")
    assert hasattr(usager, "render_alert_settings")
    assert hasattr(usager, "render_itinerary_result")
    assert hasattr(usager, "render_velov_trip")
    assert hasattr(usager, "render_lieux_velov_map")


def test_orphan_widgets_removed():
    """Widgets orphelins (recommendation_card, alternative_card, why_explainer, favorite_list) supprimes."""
    from dashboard.components.widgets import usager

    for removed in ("render_recommendation_card", "render_alternative_card",
                    "render_why_explainer", "render_why_summary",
                    "render_favorite_list", "render_recurrent_trip_card", "render_steps"):
        assert not hasattr(usager, removed), f"{removed} should be removed"


def test_usager_pages_exist():
    """Les 2 pages Usager doivent exister."""
    pages_dir = WORKSPACE / "dashboard" / "pages"
    expected = ["Usager_1_Mon_Trajet.py", "Usager_2_Alertes.py"]
    for page in expected:
        path = pages_dir / page
        assert path.exists(), f"Page manquante : {path}"
        content = path.read_text(encoding="utf-8")
        assert "apply_persona_guard" in content, f"{page} n'utilise pas apply_persona_guard"
        assert 'expected_persona="usager"' in content, f"{page} ne verifie pas le persona usager"


def test_dead_pages_removed():
    """Pages mortes (Favoris, Files) supprimees."""
    pages_dir = WORKSPACE / "dashboard" / "pages"
    for dead in ("Usager_3_Favoris.py", "Usager_4_Files.py"):
        assert not (pages_dir / dead).exists(), f"{dead} should be removed"


def test_usager_pages_have_widgets_imports():
    """Les pages Usager doivent importer les widgets."""
    pages_dir = WORKSPACE / "dashboard" / "pages"

    content = (pages_dir / "Usager_1_Mon_Trajet.py").read_text(encoding="utf-8")
    assert "render_search_bar" in content
    assert "render_weather_widget" in content
    assert "render_traffic_widget" in content

    content = (pages_dir / "Usager_2_Alertes.py").read_text(encoding="utf-8")
    assert "render_alert_card" in content
    assert "render_alert_timeline" in content
