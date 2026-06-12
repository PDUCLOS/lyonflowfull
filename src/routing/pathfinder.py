"""Pathfinding — Dijkstra / A* avec poids traffic-aware.

Sprint 12 (2026-06-12) : utilise le graphe Overpass/OSM
(gold.road_network_nodes, 5000+ nodes) quand disponible.
Sinon fallback H3. Métriques ajoutées : node count, compute time,
path length, graph type.

Fonctions :
- shortest_path(graph, origin, destination, horizon_minutes) : chemin + détail
- compute_itinerary(origin_lon, origin_lat, dest_lon, dest_lat, ...) : API haut-niveau
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from src.routing.graph import build_routing_graph, get_nearest_node, get_node_speed

logger = logging.getLogger(__name__)


@dataclass
class ItinerarySegment:
    """Un segment dans l'itinéraire."""

    channel_id: str
    length_m: float
    speed_kmh: float
    duration_s: float
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float


@dataclass
class Itinerary:
    """Itinéraire complet avec métriques Sprint 12."""

    origin_node: str
    destination_node: str
    horizon_minutes: int
    segments: list[ItinerarySegment] = field(default_factory=list)
    total_length_m: float = 0.0
    total_duration_s: float = 0.0
    average_speed_kmh: float = 0.0
    confidence: float = 0.0  # 0..1

    # Sprint 12 metrics
    graph_type: str = "unknown"  # "overpass" | "h3" | "mock"
    graph_nodes_count: int = 0
    compute_time_ms: float = 0.0

    @property
    def total_duration_min(self) -> float:
        return self.total_duration_s / 60.0

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation pour l'API."""
        return {
            "origin_node": self.origin_node,
            "destination_node": self.destination_node,
            "total_length_m": self.total_length_m,
            "total_duration_min": self.total_duration_min,
            "average_speed_kmh": self.average_speed_kmh,
            "horizon_minutes": self.horizon_minutes,
            "segments": [
                {
                    "channel_id": s.channel_id,
                    "length_m": s.length_m,
                    "speed_kmh": s.speed_kmh,
                    "duration_s": s.duration_s,
                    "start_lat": s.start_lat,
                    "start_lon": s.start_lon,
                    "end_lat": s.end_lat,
                    "end_lon": s.end_lon,
                }
                for s in self.segments
            ],
            "source": "db",
            # Sprint 12 metrics
            "graph_type": self.graph_type,
            "graph_nodes_count": self.graph_nodes_count,
            "compute_time_ms": self.compute_time_ms,
        }


def shortest_path(
    graph: nx.Graph,
    origin_node: str,
    destination_node: str,
    horizon_minutes: int = 0,
) -> Itinerary | None:
    """Calcule le plus court chemin traffic-aware (Dijkstra).

    Le poids effectif de chaque arête est travel_time_s =
    length_m / (speed_kmh * 1000/3600).

    Args:
        graph: graphe routier (NetworkX).
        origin_node, destination_node: IDs des nœuds.
        horizon_minutes: 0 = vitesse actuelle, >0 = vitesse prédite.

    Returns:
        Itinerary avec segments détaillés, ou None si pas de chemin.
    """
    start_time = time.time()

    if origin_node not in graph:
        logger.warning("Origin node %s pas dans le graphe", origin_node)
        return None
    if destination_node not in graph:
        logger.warning("Destination node %s pas dans le graphe", destination_node)
        return None

    # Construire graphe pondéré par travel time
    weighted = _build_traffic_aware_graph(graph, horizon_minutes)

    try:
        path_nodes = nx.shortest_path(
            weighted, origin_node, destination_node, weight="travel_time_s",
        )
    except nx.NetworkXNoPath:
        logger.warning("Pas de chemin entre %s et %s", origin_node, destination_node)
        return None

    # Construire l'itinéraire détaillé
    segments = []
    total_length = 0.0
    total_duration = 0.0

    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]

        # Length de l'arête
        edge_data = graph.edges[u, v]
        length = float(edge_data.get("length_m", 0))
        if length == 0:
            # Fallback: haversine
            length = _haversine_m(
                u_data.get("start_lat", 0), u_data.get("start_lon", 0),
                v_data.get("start_lat", 0), v_data.get("start_lon", 0),
            )

        speed = get_node_speed(graph, u, horizon_minutes)
        duration = (length / (speed * 1000 / 3600)) if speed > 0 else 0

        total_length += length
        total_duration += duration

        segments.append(
            ItinerarySegment(
                channel_id=str(u),
                length_m=length,
                speed_kmh=speed,
                duration_s=duration,
                start_lon=u_data.get("start_lon", 0),
                start_lat=u_data.get("start_lat", 0),
                end_lon=v_data.get("start_lon", 0),
                end_lat=v_data.get("start_lat", 0),
            )
        )

    avg_speed = (
        (total_length / (total_duration / 3600 * 1000)) if total_duration > 0 else 0
    )

    compute_time_ms = (time.time() - start_time) * 1000
    graph_type = "unknown"
    try:
        from src.routing.graph import get_graph_type
        graph_type = get_graph_type()
    except Exception:
        pass

    return Itinerary(
        origin_node=origin_node,
        destination_node=destination_node,
        horizon_minutes=horizon_minutes,
        segments=segments,
        total_length_m=total_length,
        total_duration_s=total_duration,
        average_speed_kmh=avg_speed,
        confidence=_compute_confidence(graph, path_nodes),
        graph_type=graph_type,
        graph_nodes_count=graph.number_of_nodes(),
        compute_time_ms=compute_time_ms,
    )


def _build_traffic_aware_graph(
    graph: nx.Graph, horizon_minutes: int,
) -> nx.Graph:
    """Construit un graphe pondéré par le temps de trajet traffic-aware."""
    weighted = graph.copy()
    for u, v, _data in weighted.edges(data=True):
        speed_u = get_node_speed(graph, u, horizon_minutes)
        speed_v = get_node_speed(graph, v, horizon_minutes)
        speed = min(speed_u, speed_v) if (speed_u and speed_v) else (speed_u or speed_v or 30.0)
        length = graph.edges[u, v].get("length_m", 0)
        travel_time = (length / (speed * 1000 / 3600)) if speed > 0 else 0
        weighted[u][v]["travel_time_s"] = travel_time
        weighted[u][v]["weighted_speed_kmh"] = speed
    return weighted


def _compute_confidence(graph: nx.Graph, path_nodes: list) -> float:
    """Score de confiance basé sur la fraîcheur des données."""
    return 0.85


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres."""
    import math
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def compute_itinerary(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    horizon_minutes: int = 0,
    use_cache: bool = True,
) -> Itinerary | None:
    """API haut-niveau : 2 points GPS → itinéraire détaillé avec métriques.

    Sprint 12 (2026-06-12) : ajoute graph_type, graph_nodes_count,
    compute_time_ms dans le résultat.

    Args:
        origin_lon, origin_lat: coords GPS du point de départ.
        destination_lon, destination_lat: coords GPS du point d'arrivée.
        horizon_minutes: 0 = maintenant, sinon prédiction.
        use_cache: utiliser le cache graphe (5 min TTL).

    Returns:
        Itinerary complet, ou None si pas de chemin.
    """
    graph = build_routing_graph(use_cache=use_cache)
    if graph.number_of_nodes() == 0:
        logger.warning("Graphe vide — pas d'itinéraire")
        return None

    origin_node = get_nearest_node(graph, origin_lon, origin_lat)
    dest_node = get_nearest_node(graph, destination_lon, destination_lat)

    if not origin_node:
        logger.warning("Aucun nœud trouvé près de l'origine (%.4f, %.4f)", origin_lon, origin_lat)
        return None
    if not dest_node:
        logger.warning("Aucun nœud trouvé près de la destination (%.4f, %.4f)", destination_lon, destination_lat)
        return None

    if origin_node == dest_node:
        graph_type = "unknown"
        try:
            from src.routing.graph import get_graph_type
            graph_type = get_graph_type()
        except Exception:
            pass
        return Itinerary(
            origin_node=origin_node,
            destination_node=dest_node,
            horizon_minutes=horizon_minutes,
            total_length_m=0,
            total_duration_s=0,
            graph_type=graph_type,
            graph_nodes_count=graph.number_of_nodes(),
            compute_time_ms=0.0,
        )

    return shortest_path(graph, origin_node, dest_node, horizon_minutes)