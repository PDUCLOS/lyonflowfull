"""Tests pour les widgets et pages Usager.

Lance avec : cd /Users/patriceduclos/Documents/Lyonfull && python -m pytest tests/persona/test_usager_widgets.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# prep (2026-06-19) — 4 tests mock-constants supprimés (test_mock_data_usager_imports,
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

    for removed in (
        "render_recommendation_card",
        "render_alternative_card",
        "render_why_explainer",
        "render_why_summary",
        "render_favorite_list",
        "render_recurrent_trip_card",
        "render_steps",
    ):
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


# =============================================================================
# lieux_velov_map — chemins dégradés (mypy clean 2026-09-24)
# =============================================================================
# Régression : `show_error` n'était pas importé et `_render_lieux_velov_list`
# n'existait pas → NameError à l'exécution dès que la DB tombait ou que folium
# manquait. Les tests ci-dessous exercent les deux chemins sans DB ni folium.

_LIEUX_SAMPLE = [
    {
        "lieu_name": "Part-Dieu",
        "lieu_type": "gare",
        "lieu_lat": 45.76,
        "lieu_lon": 4.86,
        "bornes": [
            {
                "velov_name": "Gare Part-Dieu Villette",
                "distance_m": 120.0,
                "num_bikes_available": 5,
                "num_docks_available": 12,
            }
        ],
    }
]


def _capture_streamlit(monkeypatch):
    """Remplace les appels Streamlit d'affichage par un enregistreur (nom, args)."""
    import streamlit as st

    calls: list[tuple[str, tuple]] = []
    for name in ("warning", "markdown", "caption", "info"):
        monkeypatch.setattr(st, name, lambda *a, _n=name, **k: calls.append((_n, a)))
    return calls


def test_lieux_velov_map_list_fallback_without_folium(monkeypatch):
    """Sans folium : warning + liste texte (1 markdown par lieu, 1 caption par borne)."""
    from dashboard.components.widgets.usager import lieux_velov_map

    calls = _capture_streamlit(monkeypatch)
    # `import folium` lève ImportError quand sys.modules["folium"] vaut None
    monkeypatch.setitem(sys.modules, "folium", None)

    lieux_velov_map.render_lieux_velov_map(_LIEUX_SAMPLE)

    names = [n for n, _ in calls]
    assert names == ["warning", "markdown", "caption"]
    assert "Part-Dieu" in calls[1][1][0]
    assert "Gare Part-Dieu Villette" in calls[2][1][0]
    assert "120m" in calls[2][1][0]


def test_lieux_velov_map_db_down_shows_error(monkeypatch):
    """DashboardDataError au chargement → show_error('db_down', ...) puis retour."""
    from dashboard.components.widgets.usager import lieux_velov_map
    from src.data import db_query
    from src.data.exceptions import DashboardDataError

    calls = _capture_streamlit(monkeypatch)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(lieux_velov_map, "show_error", lambda t, d="": errors.append((t, d)))

    def _raise(k: int = 1):
        raise DashboardDataError("postgresql", "connexion refusée")

    monkeypatch.setattr(db_query, "get_lieux_with_velov", _raise)

    lieux_velov_map.render_lieux_velov_map(None)

    assert errors == [("db_down", "[postgresql] Données du pipeline indisponibles — connexion refusée")]
    assert calls == []


def test_lieux_velov_map_empty_list_shows_info(monkeypatch):
    """Liste vide → st.info, rien d'autre."""
    from dashboard.components.widgets.usager import lieux_velov_map

    calls = _capture_streamlit(monkeypatch)
    lieux_velov_map.render_lieux_velov_map([])
    assert [n for n, _ in calls] == ["info"]
