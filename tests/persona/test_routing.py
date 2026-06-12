"""Tests pour le module routing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_routing_module_importable():
    """Le module routing doit s'importer."""
    from src.routing import (
        Itinerary,
        ItinerarySegment,
        build_routing_graph,
        compute_itinerary,
        shortest_path,
    )

    assert callable(build_routing_graph)
    assert callable(compute_itinerary)
    assert callable(shortest_path)
    assert Itinerary is not None
    assert ItinerarySegment is not None


def test_build_routing_graph_mock():
    """Le graphe mock doit fonctionner sans DB."""
    # Force le mock en mettant APP_ENV=development (déjà par défaut)
    import os

    from src.routing import build_routing_graph

    os.environ["APP_ENV"] = "development"

    graph = build_routing_graph(use_cache=False)
    assert graph is not None
    assert graph.number_of_nodes() > 0, "Mock graphe doit avoir des nœuds"
    assert graph.number_of_edges() > 0, "Mock graphe doit avoir des arêtes"

    # Vérifier les attributs des nœuds
    for _node_id, data in graph.nodes(data=True):
        assert "length_m" in data
        assert "current_speed_kmh" in data
        assert data["length_m"] > 0
        assert data["current_speed_kmh"] > 0


def test_compute_itinerary_mock():
    """compute_itinerary doit retourner un itinéraire entre 2 points."""
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


def test_itinerary_segments_have_geometry():
    """Chaque segment doit avoir start_lon, start_lat, end_lon, end_lat."""
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


def test_get_nearest_node():
    """get_nearest_node doit retourner un node_id valide."""
    from src.routing import build_routing_graph, get_nearest_node

    graph = build_routing_graph(use_cache=False)
    # Coord au centre de Lyon
    nearest = get_nearest_node(graph, 4.85, 45.75)
    assert nearest is not None
    assert nearest in graph.nodes


def test_shortest_path_direct():
    """shortest_path entre 2 nœuds adjacents doit retourner un chemin de 1 arête (2 nœuds)."""
    from src.routing import build_routing_graph, shortest_path

    graph = build_routing_graph(use_cache=False)
    # Récupère 2 nœuds connectés
    edge = next(iter(graph.edges()))
    u, v = edge[0], edge[1]

    itinerary = shortest_path(graph, u, v)
    assert itinerary is not None
    assert len(itinerary.segments) == 1  # 2 nodes → 1 edge → 1 segment
    assert itinerary.origin_node == u
    assert itinerary.destination_node == v
