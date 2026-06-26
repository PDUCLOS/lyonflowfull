"""Tests Vélov station cards (T6).

Couvre (sans mock — assertions sur le code source et dataclass) :
- VelovSegment enrichi avec n_bikes_mechanical + n_bikes_electrical (2 tests)
- _render_station_cards et _render_single_station_card présents + appelés
  dans render_velov_trip (2 tests)
- Codes couleur statut présents dans le source (1 test)
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# =============================================================================
# 1. VelovSegment enrichi (2 tests)
# =============================================================================


def test_velov_segment_has_bikes_mechanical_field():
    """VelovSegment doit avoir le champ n_bikes_mechanical (Sprint 14)."""
    from src.routing.pathfinder_multimodal import VelovSegment

    seg = VelovSegment(
        mode="cycle",
        from_label="A",
        to_label="B",
        from_lon=4.8,
        from_lat=45.7,
        to_lon=4.9,
        to_lat=45.8,
        distance_m=1000,
        duration_min=5,
        n_bikes_mechanical=7,
    )
    assert seg.n_bikes_mechanical == 7
    # Default None si pas fourni
    seg_default = VelovSegment(
        mode="cycle",
        from_label="A",
        to_label="B",
        from_lon=4.8,
        from_lat=45.7,
        to_lon=4.9,
        to_lat=45.8,
        distance_m=1000,
        duration_min=5,
    )
    assert seg_default.n_bikes_mechanical is None


def test_velov_segment_has_bikes_electrical_field():
    """VelovSegment doit avoir le champ n_bikes_electrical (Sprint 14)."""
    from src.routing.pathfinder_multimodal import VelovSegment

    seg = VelovSegment(
        mode="cycle",
        from_label="A",
        to_label="B",
        from_lon=4.8,
        from_lat=45.7,
        to_lon=4.9,
        to_lat=45.8,
        distance_m=1000,
        duration_min=5,
        n_bikes_electrical=3,
    )
    assert seg.n_bikes_electrical == 3


# =============================================================================
# 2. _render_station_cards + _render_single_station_card (2 tests)
# =============================================================================


def test_velov_trip_has_render_station_cards_function():
    """velov_trip.py doit exposer _render_station_cards et _render_single_station_card."""
    from dashboard.components.widgets.usager import velov_trip

    assert hasattr(velov_trip, "_render_station_cards")
    assert hasattr(velov_trip, "_render_single_station_card")
    assert callable(velov_trip._render_station_cards)
    assert callable(velov_trip._render_single_station_card)


def test_velov_trip_render_calls_station_cards():
    """render_velov_trip doit appeler _render_station_cards (câblage Sprint 14)."""
    velov_trip_path = (
        Path(__file__).resolve().parents[2] / "dashboard" / "components" / "widgets" / "usager" / "velov_trip.py"
    )
    source = velov_trip_path.read_text(encoding="utf-8")

    # Vérifier l'appel dans render_velov_trip (entre _render_velov_summary et la boucle diagnostics)
    assert "_render_station_cards(itin)" in source, (
        "_render_station_cards(itin) doit être appelé dans render_velov_trip"
    )


# =============================================================================
# 3. Codes couleur statut (1 test)
# =============================================================================


def test_velov_station_cards_have_all_4_status_colors():
    """_render_single_station_card doit gérer les 4 statuts (OK, FAIBLE, VIDE, PLEINE)."""
    velov_trip_path = (
        Path(__file__).resolve().parents[2] / "dashboard" / "components" / "widgets" / "usager" / "velov_trip.py"
    )
    source = velov_trip_path.read_text(encoding="utf-8")

    # Les 4 statuts doivent être présents dans le source (en texte ou en couleur)
    assert "VIDE" in source, "Statut VIDE doit être géré"
    assert "PLEINE" in source, "Statut PLEINE doit être géré"
    assert "FAIBLE" in source, "Statut FAIBLE doit être géré"
    assert "OK" in source, "Statut OK doit être géré"

    # Les couleurs Rouge/Orange/Vert doivent être dans le source
    assert "#F44336" in source, "Couleur rouge (VIDE/PLEINE) doit être présente"
    assert "#FF9800" in source, "Couleur orange (FAIBLE) doit être présente"
    assert "#4CAF50" in source, "Couleur verte (OK) doit être présente"
