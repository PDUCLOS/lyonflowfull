"""Tests Régression des modes existants (Vélov + Voiture).

Couvre (sans mock — vérifications d'import et de structure) :
- Vélov toujours fonctionnel après enrichissement (2 tests)
- Voiture toujours fonctionnel après ajout (1 test)
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# =============================================================================
# 1. Vélov (2 tests — pas de régression sur plan_velov_trip + VelovSegment)
# =============================================================================


def test_plan_velov_trip_still_importable_after_sprint14():
    """plan_velov_trip reste importable après enrichissement VelovSegment."""
    from src.routing.pathfinder_multimodal import VelovItinerary, plan_velov_trip

    assert callable(plan_velov_trip)
    assert VelovItinerary is not None

    # Vérifier que VelovItinerary a toujours ses champs existants
    import dataclasses

    fields_before_sprint14 = {
        "origin_label",
        "destination_label",
        "segments",
        "total_distance_m",
        "total_duration_min",
        "source",
    }
    actual_fields = {f.name for f in dataclasses.fields(VelovItinerary)}
    assert fields_before_sprint14.issubset(actual_fields), f"Champs perdus : {fields_before_sprint14 - actual_fields}"


def test_velov_widget_render_velov_trip_still_callable():
    """dashboard.components.widgets.usager.velov_trip.render_velov_trip reste OK."""
    from dashboard.components.widgets.usager import velov_trip

    assert hasattr(velov_trip, "render_velov_trip")
    assert callable(velov_trip.render_velov_trip)
    # Le widget expose toujours ses fonctions de rendu legacy
    for fn in ("_render_velov_summary", "_render_velov_map", "_render_velov_segments", "_render_alternatives_card"):
        assert hasattr(velov_trip, fn), f"Fonction {fn} doit toujours exister"


# =============================================================================
# 2. Voiture (1 test — pas de régression sur plan_car_trip)
# =============================================================================


def test_plan_car_trip_still_importable_after_sprint14():
    """plan_car_trip reste importable + signature inchangée après Sprint 14.
    Convention canonique hotfix 7 : (lon, lat, lon, lat)
      Convention canonique hotfix 7 : (lon, lat, lon, lat)
    """
    import inspect

    from src.routing.pathfinder_multimodal import plan_car_trip

    assert callable(plan_car_trip)
    sig = inspect.signature(plan_car_trip)
    sig = inspect.signature(plan_car_trip)
    # Convention (lon, lat) — noms courts depuis hotfix 7
    assert "origin_lat" in sig.parameters
    assert "dest_lon" in sig.parameters
    assert "dest_lat" in sig.parameters
    # Optionnels
    assert "horizon_minutes" in sig.parameters
    assert "origin_label" in sig.parameters
    assert "dest_label" in sig.parameters


# =============================================================================
# 3. Page Usager_1_Mon_Trajet — section TC bien câblée
# =============================================================================


def test_usager_page_has_has_tc_check():
    """Usager_1_Mon_Trajet.py doit calculer has_tc et afficher la section TC."""
    page_path = Path(__file__).resolve().parents[2] / "dashboard" / "pages" / "Usager_1_Mon_Trajet.py"
    source = page_path.read_text(encoding="utf-8")

    # has_tc calculé depuis le multiselect
    assert 'has_tc = any("Transport en commun" in m for m in modes)' in source, (
        "Usager_1_Mon_Trajet.py doit définir has_tc"
    )

    # Section if has_tc avec render_transit_trip
    assert "if has_tc:" in source, "Section conditionnelle if has_tc doit exister"
    assert "render_transit_trip(" in source, "render_transit_trip doit être appelé dans la section TC"

    # Import de render_transit_trip
    assert "render_transit_trip" in source, "render_transit_trip doit être importé"


# =============================================================================
# 4. __init__.py widgets/usager exporte render_transit_trip
# =============================================================================


def test_widgets_usager_init_exports_render_transit_trip():
    """dashboard.components.widgets.usager doit exporter render_transit_trip."""
    from dashboard.components.widgets import usager

    assert hasattr(usager, "render_transit_trip")
    assert "render_transit_trip" in usager.__all__
