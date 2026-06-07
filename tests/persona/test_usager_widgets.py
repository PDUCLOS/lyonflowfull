"""Tests pour les widgets et pages Usager.

Lance avec : cd /Users/patriceduclos/Documents/Lyonfull && python -m pytest tests/persona/test_usager_widgets.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ajouter le workspace au path pour les imports
WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_mock_data_usager_imports():
    """Le module mock data usager doit s'importer sans erreur."""
    from src.data.mock import usager  # noqa: F401

    assert hasattr(usager, "TCL_LINES")
    assert hasattr(usager, "MOCK_TRIP_RESULTS")
    assert hasattr(usager, "VELOV_STATIONS")
    assert hasattr(usager, "MOCK_ALERTS")
    assert hasattr(usager, "MOCK_WEATHER")
    assert hasattr(usager, "MOCK_TRAFFIC")
    assert hasattr(usager, "MOCK_FAVORITES")


def test_tcl_lines_have_required_fields():
    """Chaque ligne TCL doit avoir id, name, mode, color, icon."""
    from src.data.mock.usager import TCL_LINES

    assert len(TCL_LINES) >= 10, f"Attendu ≥ 10 lignes, trouvé {len(TCL_LINES)}"
    for line in TCL_LINES:
        for field in ("id", "name", "mode", "color", "icon"):
            assert field in line, f"Ligne {line.get('id')} manque le champ {field}"


def test_velov_stations_have_lyon_coordinates():
    """Les stations Vélov doivent avoir des coordonnées réalistes Lyon."""
    from src.data.mock.usager import VELOV_STATIONS

    assert len(VELOV_STATIONS) >= 3
    for s in VELOV_STATIONS:
        lat = s.get("lat", 0)
        lon = s.get("lon", 0)
        # Lyon est autour de lat 45.76, lon 4.85
        assert 45.70 <= lat <= 45.80, f"Station {s.get('name')} lat hors Lyon: {lat}"
        assert 4.78 <= lon <= 4.90, f"Station {s.get('name')} lon hors Lyon: {lon}"


def test_mock_alerts_have_required_fields():
    """Chaque alerte doit avoir line, title, description, action, severity."""
    from src.data.mock.usager import MOCK_ALERTS

    assert len(MOCK_ALERTS) >= 3
    for a in MOCK_ALERTS:
        for field in ("line", "title", "description", "action", "severity"):
            assert field in a, f"Alerte {a.get('id')} manque {field}"


def test_mock_favorites_have_route_info():
    """Chaque favori doit avoir name, origin, destination, usual_mode."""
    from src.data.mock.usager import MOCK_FAVORITES

    assert len(MOCK_FAVORITES) >= 3
    for f in MOCK_FAVORITES:
        for field in ("name", "origin", "destination", "usual_mode", "next_departure"):
            assert field in f, f"Favori {f.get('id')} manque {field}"


def test_widget_modules_importable():
    """Tous les modules widgets usager doivent s'importer."""
    from dashboard.components.widgets import usager  # noqa: F401

    # Vérifier que les fonctions principales sont exposées
    assert hasattr(usager, "render_search_bar")
    assert hasattr(usager, "render_recommendation_card")
    assert hasattr(usager, "render_alternative_card")
    assert hasattr(usager, "render_why_explainer")
    assert hasattr(usager, "render_weather_widget")
    assert hasattr(usager, "render_velov_widget")
    assert hasattr(usager, "render_traffic_widget")
    assert hasattr(usager, "render_alert_card")
    assert hasattr(usager, "render_alert_timeline")
    assert hasattr(usager, "render_alert_settings")
    assert hasattr(usager, "render_favorite_list")
    assert hasattr(usager, "render_recurrent_trip_card")


def test_usager_pages_exist():
    """Les 3 pages Usager doivent exister et être importables."""
    # Import dynamique (Streamlit page files ne s'importent pas comme modules normaux
    # à cause de st.set_page_config en top-level, donc on vérifie juste l'existence)
    pages_dir = WORKSPACE / "dashboard" / "pages"
    expected = ["Usager_1_Mon_Trajet.py", "Usager_2_Alertes.py", "Usager_3_Favoris.py"]
    for page in expected:
        path = pages_dir / page
        assert path.exists(), f"Page manquante : {path}"
        # Vérifier qu'elle utilise apply_persona_guard
        content = path.read_text(encoding="utf-8")
        assert "apply_persona_guard" in content, f"{page} n'utilise pas apply_persona_guard"
        assert 'expected_persona="usager"' in content, f"{page} ne vérifie pas le persona usager"


def test_usager_pages_have_widgets_imports():
    """Les pages Usager doivent importer les widgets."""
    pages_dir = WORKSPACE / "dashboard" / "pages"

    # Mon Trajet doit utiliser search_bar, recommendation_card, etc.
    content = (pages_dir / "Usager_1_Mon_Trajet.py").read_text(encoding="utf-8")
    assert "render_search_bar" in content
    assert "render_recommendation_card" in content
    assert "render_weather_widget" in content

    # Alertes doit utiliser alert_card, alert_timeline
    content = (pages_dir / "Usager_2_Alertes.py").read_text(encoding="utf-8")
    assert "render_alert_card" in content
    assert "render_alert_timeline" in content

    # Favoris doit utiliser favorite_list
    content = (pages_dir / "Usager_3_Favoris.py").read_text(encoding="utf-8")
    assert "render_favorite_list" in content
