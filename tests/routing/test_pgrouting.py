"""Tests unitaires pgRouting — dataclasses + parsing (sans DB).

Sprint 26+ : le routing voiture utilise pgRouting (réseau routier OSM).
Ces tests vérifient les dataclasses et le parsing côté Python sans
toucher la DB (les tests @pytest.mark.integration sont dans
tests/persona/test_routing.py).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_itinerary_segment_geometry_field():
    """ItinerarySegment accepte un champ geometry optionnel."""
    from src.routing.pathfinder import ItinerarySegment

    seg_no_geom = ItinerarySegment(
        channel_id="Rue X", length_m=100, speed_kmh=30,
        duration_s=12, start_lon=4.83, start_lat=45.76,
        end_lon=4.84, end_lat=45.77,
    )
    assert seg_no_geom.geometry is None

    seg_with_geom = ItinerarySegment(
        channel_id="Rue Y", length_m=200, speed_kmh=40,
        duration_s=18, start_lon=4.83, start_lat=45.76,
        end_lon=4.85, end_lat=45.78,
        geometry=[[4.83, 45.76], [4.835, 45.765], [4.84, 45.77], [4.85, 45.78]],
    )
    assert seg_with_geom.geometry is not None
    assert len(seg_with_geom.geometry) == 4


def test_itinerary_total_duration_min():
    """Itinerary.total_duration_min = total_duration_s / 60."""
    from src.routing.pathfinder import Itinerary

    itin = Itinerary(
        origin_node="1", destination_node="2",
        horizon_minutes=0,
        total_duration_s=300.0,
    )
    assert itin.total_duration_min == pytest.approx(5.0)


def test_itinerary_empty_segments():
    """Itinerary vide a des segments vides et durée 0."""
    from src.routing.pathfinder import Itinerary

    itin = Itinerary(origin_node="1", destination_node="2", horizon_minutes=0)
    assert len(itin.segments) == 0
    assert itin.total_duration_s == 0.0
    assert itin.total_length_m == 0.0


def test_compute_route_pgrouting_parses_geojson():
    """compute_route_pgrouting parse correctement le GeoJSON retourné par SQL."""
    from src.routing.graph import compute_route_pgrouting

    mock_geojson = json.dumps({
        "type": "LineString",
        "coordinates": [[4.83, 45.76], [4.832, 45.761], [4.834, 45.762]],
    })
    mock_rows = [
        {
            "seq": 1, "edge_id": 42, "node_id": 1,
            "cost_s": 12.5, "agg_cost_s": 12.5,
            "length_m": 150.0, "speed_kmh": 43.2,
            "road_name": "Rue de la République",
            "geom_geojson": mock_geojson,
        },
        {
            "seq": 2, "edge_id": 43, "node_id": 2,
            "cost_s": 8.0, "agg_cost_s": 20.5,
            "length_m": 100.0, "speed_kmh": 45.0,
            "road_name": "Place Bellecour",
            "geom_geojson": json.dumps({
                "type": "LineString",
                "coordinates": [[4.834, 45.762], [4.835, 45.763]],
            }),
        },
    ]

    with patch("src.db.execute_query", return_value=mock_rows):
        result = compute_route_pgrouting(4.83, 45.76, 4.835, 45.763)

    assert result is not None
    assert len(result) == 2
    assert result[0]["road_name"] == "Rue de la République"
    assert result[0]["geom_coordinates"] == [[4.83, 45.76], [4.832, 45.761], [4.834, 45.762]]
    assert result[1]["edge_id"] == 43


def test_compute_route_pgrouting_handles_null_geojson():
    """compute_route_pgrouting gère les arêtes sans géométrie."""
    from src.routing.graph import compute_route_pgrouting

    mock_rows = [
        {
            "seq": 1, "edge_id": 99, "node_id": 1,
            "cost_s": 5.0, "agg_cost_s": 5.0,
            "length_m": 50.0, "speed_kmh": 30.0,
            "road_name": None,
            "geom_geojson": None,
        },
    ]

    with patch("src.db.execute_query", return_value=mock_rows):
        result = compute_route_pgrouting(4.83, 45.76, 4.84, 45.77)

    assert result is not None
    assert len(result) == 1
    assert result[0]["geom_coordinates"] == []
    assert result[0]["road_name"] == ""


def test_compute_route_pgrouting_returns_none_on_empty():
    """compute_route_pgrouting retourne None si pas de chemin."""
    from src.routing.graph import compute_route_pgrouting

    with patch("src.db.execute_query", return_value=[]):
        result = compute_route_pgrouting(4.83, 45.76, 4.84, 45.77)

    assert result is None


def test_compute_itinerary_builds_segments_from_pgrouting():
    """compute_itinerary construit des ItinerarySegment depuis pgRouting."""
    from src.routing.pathfinder import compute_itinerary

    mock_edges = [
        {
            "seq": 1, "edge_id": 10,
            "cost_s": 15.0, "agg_cost_s": 15.0,
            "length_m": 200.0, "speed_kmh": 48.0,
            "road_name": "Avenue Foch",
            "geom_coordinates": [[4.83, 45.76], [4.832, 45.761], [4.834, 45.762]],
        },
        {
            "seq": 2, "edge_id": 11,
            "cost_s": 10.0, "agg_cost_s": 25.0,
            "length_m": 150.0, "speed_kmh": 54.0,
            "road_name": "Rue Garibaldi",
            "geom_coordinates": [[4.834, 45.762], [4.836, 45.764]],
        },
    ]

    with patch("src.routing.pathfinder.compute_route_pgrouting", return_value=mock_edges):
        with patch("src.routing.pathfinder._compute_pgrouting_confidence", return_value=0.85):
            itin = compute_itinerary(4.83, 45.76, 4.836, 45.764)

    assert itin is not None
    assert len(itin.segments) == 2
    assert itin.total_length_m == pytest.approx(350.0)
    assert itin.total_duration_s == pytest.approx(25.0)
    assert itin.confidence == pytest.approx(0.85)

    seg0 = itin.segments[0]
    assert seg0.channel_id == "Avenue Foch"
    assert seg0.start_lon == pytest.approx(4.83)
    assert seg0.start_lat == pytest.approx(45.76)
    assert seg0.end_lon == pytest.approx(4.834)
    assert seg0.end_lat == pytest.approx(45.762)
    assert seg0.geometry is not None
    assert len(seg0.geometry) == 3


def test_compute_itinerary_returns_none_on_no_route():
    """compute_itinerary retourne None si pgRouting ne trouve pas de chemin."""
    from src.routing.pathfinder import compute_itinerary

    with patch("src.routing.pathfinder.compute_route_pgrouting", return_value=None):
        itin = compute_itinerary(4.83, 45.76, 10.0, 50.0)

    assert itin is None


def test_compute_route_pgrouting_handles_invalid_geojson():
    """compute_route_pgrouting gère le GeoJSON invalide sans crash."""
    from src.routing.graph import compute_route_pgrouting

    mock_rows = [
        {
            "seq": 1, "edge_id": 77, "node_id": 1,
            "cost_s": 5.0, "agg_cost_s": 5.0,
            "length_m": 50.0, "speed_kmh": 30.0,
            "road_name": "Broken",
            "geom_geojson": "NOT JSON {{{",
        },
    ]

    with patch("src.db.execute_query", return_value=mock_rows):
        result = compute_route_pgrouting(4.83, 45.76, 4.84, 45.77)

    assert result is not None
    assert result[0]["geom_coordinates"] == []
