"""Tests pour le module routing.

Sprint 26+ : pgRouting remplace NetworkX H3 pour le routing voiture.
- `compute_itinerary` appelle `osm.route_car()` côté DB → tests marqués @pytest.mark.integration
- `shortest_path` et `get_nearest_node` retirés (pgRouting fait tout côté SQL)
- `build_routing_graph` et `get_node_speed` conservés pour le GNN
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_routing_module_importable():
    """Le module routing doit s'importer avec les nouveaux exports pgRouting."""
    from src.routing import (
        Itinerary,
        ItinerarySegment,
        compute_itinerary,
        compute_route_pgrouting,
        get_nearest_osm_node,
        get_node_speed,
    )

    assert callable(compute_itinerary)
    assert callable(compute_route_pgrouting)
    assert callable(get_nearest_osm_node)
    assert callable(get_node_speed)
    assert Itinerary is not None
    assert ItinerarySegment is not None


def test_build_routing_graph_for_gnn():
    """build_routing_graph reste utilisable pour le GNN (H3 KNN legacy)."""
    import os

    from src.routing.graph import build_routing_graph

    os.environ["APP_ENV"] = "development"

    graph = build_routing_graph(use_cache=False)
    assert graph is not None
    assert graph.number_of_nodes() > 0, "Mock graphe doit avoir des nœuds"
    assert graph.number_of_edges() > 0, "Mock graphe doit avoir des arêtes"

    # Vérifier les attributs des nœuds (utilisés par le GNN)
    for _node_id, data in graph.nodes(data=True):
        assert "length_m" in data
        assert "current_speed_kmh" in data


# =============================================================================
# Tests pgRouting — marqués @pytest.mark.integration car touchent la DB live
# Exécutés uniquement via : pytest -m integration tests/persona/test_routing.py
# (ou directement sur le VPS où la DB est dispo)
# =============================================================================


@pytest.mark.integration
def test_compute_itinerary_pgrouting():
    """compute_itinerary retourne un itinéraire entre 2 points via pgRouting."""
    from src.routing import compute_itinerary

    # Part-Dieu vers Bellecour (coords approx)
    # Part-Dieu : 4.8589, 45.7607
    # Bellecour : 4.8324, 45.7575
    itinerary = compute_itinerary(
        origin_lon=4.8589,
        origin_lat=45.7607,
        destination_lon=4.8324,
        destination_lat=45.7575,
        horizon_minutes=0,
    )
    assert itinerary is not None
    assert len(itinerary.segments) > 0, "Itinéraire doit avoir au moins 1 segment"
    assert itinerary.total_length_m > 0
    assert itinerary.total_duration_s > 0
    assert itinerary.average_speed_kmh > 0


@pytest.mark.integration
def test_itinerary_segments_have_geometry():
    """Chaque segment doit avoir une géométrie OSM multi-vertices (pgRouting)."""
    from src.routing import compute_itinerary

    itinerary = compute_itinerary(
        origin_lon=4.8589,
        origin_lat=45.7607,
        destination_lon=4.8324,
        destination_lat=45.7575,
    )
    for seg in itinerary.segments:
        assert seg.start_lon is not None
        assert seg.start_lat is not None
        assert seg.end_lon is not None
        assert seg.end_lat is not None
        assert seg.geometry is not None, "Géométrie OSM requise (pgRouting)"
        assert len(seg.geometry) >= 2, "Géométrie doit avoir au moins 2 points"


@pytest.mark.integration
def test_itinerary_total_duration_reasonable():
    """La durée totale doit être réaliste (pas 0, pas astronomique)."""
    from src.routing import compute_itinerary

    # 3 km en ville Lyon → 10-30 min attendu (trafic)
    itinerary = compute_itinerary(
        origin_lon=4.8589,
        origin_lat=45.7607,
        destination_lon=4.8324,
        destination_lat=45.7575,
    )
    assert itinerary.total_duration_s > 60, "Au moins 1 min pour 3km"
    assert itinerary.total_duration_s < 7200, "Pas plus de 2h pour 3km"


@pytest.mark.integration
def test_compute_route_pgrouting_returns_edges_with_geometry():
    """compute_route_pgrouting retourne des arêtes avec géométrie OSM."""
    from src.routing import compute_route_pgrouting

    edges = compute_route_pgrouting(
        origin_lon=4.8589,
        origin_lat=45.7607,
        dest_lon=4.8324,
        dest_lat=45.7575,
    )
    assert edges is not None
    assert len(edges) > 0
    for edge in edges:
        assert "edge_id" in edge
        assert "cost_s" in edge
        assert "length_m" in edge
        assert "speed_kmh" in edge
        assert "road_name" in edge
        assert "geom_coordinates" in edge
        assert len(edge["geom_coordinates"]) >= 2, "Géométrie OSM doit avoir ≥ 2 points"


@pytest.mark.integration
def test_get_nearest_osm_node():
    """get_nearest_osm_node retourne un ID de nœud OSM valide."""
    from src.routing import get_nearest_osm_node

    node_id = get_nearest_osm_node(4.85, 45.75)
    assert node_id is not None
    assert isinstance(node_id, int)


@pytest.mark.integration
def test_itinerary_confidence_is_reasonable():
    """confidence doit être entre 0.5 et 1.0 (basée sur coverage_ratio)."""
    from src.routing import compute_itinerary

    itinerary = compute_itinerary(
        origin_lon=4.8589,
        origin_lat=45.7607,
        destination_lon=4.8324,
        destination_lat=45.7575,
    )
    assert 0.5 <= itinerary.confidence <= 1.0
