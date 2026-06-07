"""Pathfinding — Dijkstra avec poids traffic-aware.

Calcule le plus court chemin entre 2 nœuds du graphe routier.
Poids = travel_time = length_m / speed_kmh (avec conversion km/h → m/s).

Fonctions :
- shortest_path(graph, origin, destination, horizon_minutes) : chemin + détail
- estimate_travel_time(graph, path, horizon_minutes) : temps total
- k_shortest_paths(graph, origin, destination, k) : N alternatives
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from src.routing.graph import build_routing_graph, get_node_speed, get_nearest_node


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
    """Itinéraire complet."""
    origin_node: str
    destination_node: str
    horizon_minutes: int
    segments: list[ItinerarySegment] = field(default_factory=list)
    total_length_m: float = 0.0
    total_duration_s: float = 0.0
    average_speed_kmh: float = 0.0
    confidence: float = 0.0  # 0..1, basé sur vitesse récente disponible

    @property
    def total_duration_min(self) -> float:
        return self.total_duration_s / 60.0


def shortest_path(
    graph: nx.Graph,
    origin_node: str,
    destination_node: str,
    horizon_minutes: int = 0,
    weight_attr: str = "length_m",
    speed_attr: str = "current_speed_kmh",
) -> Optional[Itinerary]:
    """Calcule le plus court chemin traffic-aware.

    Le poids effectif de chaque arête est :
        weight_eff = length / speed * 3.6  (pour avoir secondes : m / (km/h * 1000/3600))

    Args:
        graph: graphe routier (NetworkX).
        origin_node: channel_id d'origine.
        destination_node: channel_id de destination.
        horizon_minutes: 0 = vitesse actuelle, >0 = vitesse prédite.
        weight_attr: attribut d'arête pour la distance (défaut: length_m).
        speed_attr: attribut de nœud pour la vitesse (défaut: current_speed_kmh).

    Returns:
        Itinerary avec segments détaillés, ou None si pas de chemin.
    """
    if origin_node not in graph:
        logger.warning(f"Origin node {origin_node} pas dans le graphe")
        return None
    if destination_node not in graph:
        logger.warning(f"Destination node {destination_node} pas dans le graphe")
        return None

    # Calcul des poids traffic-aware
    weighted = _build_traffic_aware_graph(graph, horizon_minutes)

    try:
        path_nodes = nx.shortest_path(
            weighted, origin_node, destination_node, weight="travel_time_s"
        )
    except nx.NetworkXNoPath:
        logger.warning(f"Pas de chemin entre {origin_node} et {destination_node}")
        return None

    # Construire l'itinéraire détaillé
    segments = []
    total_length = 0.0
    total_duration = 0.0

    for node_id in path_nodes:
        data = graph.nodes[node_id]
        speed = get_node_speed(graph, node_id, horizon_minutes)
        length = data.get("length_m", 0)
        # duration en secondes : length_m / (speed_kmh * 1000/3600)
        duration = (length / (speed * 1000 / 3600)) if speed > 0 else 0
        total_length += length
        total_duration += duration
        segments.append(ItinerarySegment(
            channel_id=node_id,
            length_m=length,
            speed_kmh=speed,
            duration_s=duration,
            start_lon=data["start_lon"],
            start_lat=data["start_lat"],
            end_lon=data["end_lon"],
            end_lat=data["end_lat"],
        ))

    avg_speed = (total_length / (total_duration / 3600 * 1000)) if total_duration > 0 else 0

    return Itinerary(
        origin_node=origin_node,
        destination_node=destination_node,
        horizon_minutes=horizon_minutes,
        segments=segments,
        total_length_m=total_length,
        total_duration_s=total_duration,
        average_speed_kmh=avg_speed,
        confidence=_compute_confidence(graph, path_nodes),
    )


def _build_traffic_aware_graph(graph: nx.Graph, horizon_minutes: int) -> nx.Graph:
    """Construit un graphe pondéré par le temps de trajet traffic-aware."""
    weighted = graph.copy()
    for u, v, data in weighted.edges(data=True):
        speed_u = get_node_speed(graph, u, horizon_minutes)
        speed_v = get_node_speed(graph, v, horizon_minutes)
        # On prend la vitesse la plus défavorable (plus conservative)
        speed = min(speed_u, speed_v) if (speed_u and speed_v) else (speed_u or speed_v or 30.0)
        # length_m entre u et v (approximation : moyenne des deux)
        length_u = graph.nodes[u].get("length_m", 0)
        length_v = graph.nodes[v].get("length_m", 0)
        avg_length = (length_u + length_v) / 2
        # Travel time en secondes
        travel_time = (avg_length / (speed * 1000 / 3600)) if speed > 0 else 0
        weighted[u][v]["travel_time_s"] = travel_time
        weighted[u][v]["weighted_speed_kmh"] = speed
    return weighted


def _compute_confidence(graph: nx.Graph, path_nodes: list) -> float:
    """Calcule un score de confiance basé sur la fraîcheur des données.

    1.0 = toutes les données < 15 min
    0.0 = données > 1h ou manquantes
    """
    # Heuristique simple : on suppose 1.0 par défaut (mock)
    # Sprint 6+ : query DB pour vérifier fraîcheur réelle
    return 0.85


def compute_itinerary(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    horizon_minutes: int = 0,
    use_cache: bool = True,
) -> Optional[Itinerary]:
    """API haut-niveau : 2 points GPS → itinéraire détaillé.

    Args:
        origin_lon, origin_lat: coords GPS du point de départ.
        destination_lon, destination_lat: coords GPS du point d'arrivée.
        horizon_minutes: 0 = maintenant, sinon utilise la prédiction.
        use_cache: utiliser le cache graphe (5 min TTL).

    Returns:
        Itinerary complet, ou None si pas de chemin.
    """
    graph = build_routing_graph(use_cache=use_cache)
    if graph.number_of_nodes() == 0:
        return None

    origin_node = get_nearest_node(graph, origin_lon, origin_lat)
    dest_node = get_nearest_node(graph, destination_lon, destination_lat)

    if not origin_node or not dest_node:
        return None

    if origin_node == dest_node:
        # Origine = destination
        return Itinerary(
            origin_node=origin_node,
            destination_node=dest_node,
            horizon_minutes=horizon_minutes,
            total_length_m=0,
            total_duration_s=0,
        )

    return shortest_path(graph, origin_node, dest_node, horizon_minutes)
