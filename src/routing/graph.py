"""Routing — graphe routier à partir de silver.trafic_boucles_clean.

Construit un graphe NetworkX où :
- Nœuds = channel_id (segments de capteurs)
- Arêtes = paires de segments partageant un endpoint (start ↔ end)
- Attributs : length_m (mètres), current_speed (km/h), predicted_speeds (dict horizon→km/h)

Le graphe est :
- Construit depuis la DB (silver)
- Cache en mémoire pendant la session (rebuild toutes les 5 min en prod)
- Fallback mock pour dev sans DB

Pour Lyon :
- ~1100 segments (capteurs pvotrafic)
- ~5000-8000 arêtes (K=2 + endpoints partagés)
- Latence pathfinding < 50ms pour 4 hops

Usage :
    from src.routing import build_routing_graph
    graph = build_routing_graph()
    # graph.nodes → {channel_id: {length_m, current_speed, ...}}
    # graph.edges → {(u, v): {length_m, ...}}
"""

from __future__ import annotations

import logging
import time

import networkx as nx

from src.db import execute_query
from src.routing.gtfs_graph_builder import load_graph_from_db

logger = logging.getLogger(__name__)


# Cache module-level (TTL 5 min)
_graph_cache: dict = {
    "graph": None,
    "node_to_idx": None,
    "idx_to_node": None,
    "built_at": 0.0,
}
CACHE_TTL_SECONDS = 300  # 5 min


def build_routing_graph(
    use_cache: bool = True,
    min_segment_length_m: float = 5.0,
    endpoint_tolerance_deg: float = 0.00002,  # ~2m à 45° lat
) -> nx.Graph:
    """Construit le graphe routier.

    Priorité :
    1. gold.road_network_nodes/edges (Overpass/OSM, Sprint 12) — 112k nodes
    2. Graphe H3 (fallback Sprint 8)
    3. Graphe mock (dev sans DB)
    """
    if use_cache and _is_cache_valid():
        return _graph_cache["graph"]

    # 1. Essayer Overpass/OSM graph (Sprint 12)
    try:
        G_diag = load_graph_from_db()  # returns nx.DiGraph  # noqa: N806
        # Convert to undirected for pathfinding
        G = G_diag.to_undirected()  # noqa: N806
        # Add node attrs needed by pathfinder (start/end coords)
        for node_id in G.nodes:
            nd = G.nodes[node_id]
            lat = nd.get("lat")
            lon = nd.get("lon")
            highway = nd.get("highway_type", "road")
            speed = _speed_from_highway(highway)
            nd.setdefault("start_lon", lon)
            nd.setdefault("start_lat", lat)
            nd.setdefault("end_lon", lon)
            nd.setdefault("end_lat", lat)
            nd.setdefault("current_speed_kmh", speed)
            nd.setdefault("length_m", 50.0)
        graph_type = "overpass"
        logger.info(f"Routing graph (Overpass): {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    except Exception as e:
        logger.warning(f"Overpass graph failed ({e})")
        # 2. Fallback H3 graph (Sprint 8 legacy — kept for dev without OSM data)
        try:
            from src.routing.h3_graph import build_h3_graph as _build_h3
            G, graph_type = _build_h3(min_segment_length_m)  # noqa: N806
            logger.info(f"Routing graph (H3): {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        except Exception as e2:
            logger.warning(f"H3 graph failed ({e2}) — fallback mock")
            G = _build_mock_graph()  # noqa: N806
            graph_type = "mock"

    _graph_cache["graph"] = G
    _graph_cache["built_at"] = time.time()
    _graph_cache["graph_type"] = graph_type
    return G


def get_graph_type() -> str:
    """Retourne le type de graphe utilisé ('overpass' | 'h3' | 'mock')."""
    return _graph_cache.get("graph_type", "unknown")


def _is_cache_valid() -> bool:
    return _graph_cache["graph"] is not None and (time.time() - _graph_cache["built_at"]) < CACHE_TTL_SECONDS


def _db_available() -> bool:
    from src.db import test_connection

    return test_connection()


def _build_graph_from_db(
    min_segment_length_m: float,
    endpoint_tolerance_deg: float,
) -> nx.Graph:
    """Construit le graphe depuis la DB en SQL.

    Requiert l'extension PostGIS (ST_StartPoint, ST_EndPoint, ST_Length).
    """
    query = """
        WITH latest AS (
            SELECT DISTINCT ON (channel_id)
                channel_id,
                ST_StartPoint(geom_wgs84) AS start_pt,
                ST_EndPoint(geom_wgs84) AS end_pt,
                ST_X(ST_StartPoint(geom_wgs84)) AS start_lon,
                ST_Y(ST_StartPoint(geom_wgs84)) AS start_lat,
                ST_X(ST_EndPoint(geom_wgs84)) AS end_lon,
                ST_Y(ST_EndPoint(geom_wgs84)) AS end_lat,
                ST_Length(geom_wgs84::geography) AS length_m,
                vitesse_kmh AS current_speed_kmh,
                measurement_time
            FROM silver.trafic_boucles_clean
            WHERE geom_wgs84 IS NOT NULL
              AND vitesse_kmh IS NOT NULL
              AND measurement_time > NOW() - INTERVAL '1 hour'
            ORDER BY channel_id, measurement_time DESC
        )
        SELECT
            channel_id,
            start_lon, start_lat, end_lon, end_lat,
            length_m,
            current_speed_kmh
        FROM latest
        WHERE length_m > %s
    """
    rows = execute_query(query, (min_segment_length_m,))
    if not rows:
        raise ValueError("Aucun segment dans silver.trafic_boucles_clean")

    G = nx.Graph()  # noqa: N806

    # 1. Ajouter les nœuds
    for r in rows:
        channel_id = r["channel_id"]
        G.add_node(
            channel_id,
            **{
                "length_m": float(r["length_m"]),
                "current_speed_kmh": float(r["current_speed_kmh"]),
                "start_lon": float(r["start_lon"]),
                "start_lat": float(r["start_lat"]),
                "end_lon": float(r["end_lon"]),
                "end_lat": float(r["end_lat"]),
            },
        )

    # 2. Construire les arêtes par matching d'endpoints
    #    On indexe les endpoints (start + end) et on groupe
    nodes_data = list(G.nodes(data=True))
    endpoint_index: dict[tuple[float, float], list[str]] = {}
    for cid, data in nodes_data:
        for ep in [(data["start_lon"], data["start_lat"]), (data["end_lon"], data["end_lat"])]:
            # Quantize for tolerance
            key = (round(ep[0] / endpoint_tolerance_deg), round(ep[1] / endpoint_tolerance_deg))
            endpoint_index.setdefault(key, []).append(cid)

    # 3. Pour chaque endpoint partagé, créer les arêtes
    edge_set: set[tuple[str, str]] = set()
    for cid_list in endpoint_index.values():
        if len(cid_list) < 2:
            continue
        for i, u in enumerate(cid_list):
            for v in cid_list[i + 1 :]:
                edge = tuple(sorted([u, v]))
                if edge not in edge_set:
                    edge_set.add(edge)
                    G.add_edge(u, v, via="shared_endpoint")

    return G, "h3"


def _build_mock_graph() -> nx.Graph:
    """Graphe mock pour dev sans DB.

    Simule 12 segments dans le centre de Lyon (Part-Dieu, Bellecour, etc.)
    avec adjacences réalistes et vitesses mock.
    """
    G = nx.Graph()  # noqa: N806

    # Centre Lyon : Presqu'île + Part-Dieu + Confluence
    # Format : (channel_id, start_lon, start_lat, end_lon, end_lat, length_m, speed)
    segments = [
        # Autour de Part-Dieu
        ("MOCK_C3_S01", 4.8589, 45.7607, 4.8520, 45.7620, 580, 25),
        ("MOCK_C3_S02", 4.8520, 45.7620, 4.8461, 45.7496, 1800, 35),
        ("MOCK_C3_S03", 4.8461, 45.7496, 4.8417, 45.7456, 1100, 22),
        # Vers Bellecour
        ("MOCK_T1_S01", 4.8342, 45.7672, 4.8324, 45.7575, 1300, 18),
        ("MOCK_T1_S02", 4.8324, 45.7575, 4.8165, 45.7405, 2400, 40),
        # Confluence → Perrache
        ("MOCK_M_A_S01", 4.8340, 45.7480, 4.8360, 45.7513, 900, 30),
        # Saxe
        ("MOCK_C13_S01", 4.8461, 45.7496, 4.8343, 45.7673, 2100, 28),
        # Berthelot
        ("MOCK_T2_S01", 4.8501, 45.7450, 4.8350, 45.7450, 1100, 32),
        # Mermoz
        ("MOCK_T3_S01", 4.8700, 45.7310, 4.8700, 45.7290, 600, 22),
        # Vaise
        ("MOCK_C14_S01", 4.8058, 45.7798, 4.8059, 45.7722, 950, 28),
        # Jean Macé
        ("MOCK_C3_S04", 4.8417, 45.7456, 4.8408, 45.7431, 450, 26),
        # Guillotière
        ("MOCK_C3_S05", 4.8408, 45.7431, 4.8325, 45.7324, 1500, 33),
    ]

    for cid, slon, slat, elon, elat, length, speed in segments:
        G.add_node(
            cid,
            **{
                "length_m": length,
                "current_speed_kmh": speed,
                "start_lon": slon,
                "start_lat": slat,
                "end_lon": elon,
                "end_lat": elat,
            },
        )

    # Adjacences mockées (segments qui se touchent)
    adjacencies = [
        ("MOCK_C3_S01", "MOCK_C3_S02"),
        ("MOCK_C3_S02", "MOCK_C3_S03"),
        ("MOCK_C3_S02", "MOCK_C13_S01"),
        ("MOCK_C3_S03", "MOCK_C3_S04"),
        ("MOCK_C3_S04", "MOCK_C3_S05"),
        ("MOCK_C3_S03", "MOCK_T1_S01"),
        ("MOCK_T1_S01", "MOCK_T1_S02"),
        ("MOCK_T1_S02", "MOCK_M_A_S01"),
        ("MOCK_C13_S01", "MOCK_M_A_S01"),
        ("MOCK_T2_S01", "MOCK_C3_S04"),
        ("MOCK_T3_S01", "MOCK_T2_S01"),
        ("MOCK_C14_S01", "MOCK_C13_S01"),
    ]
    for u, v in adjacencies:
        G.add_edge(u, v, via="mock")

    return G


def get_node_speed(graph: nx.Graph, node_id: str, horizon_minutes: int = 0) -> float:
    """Récupère la vitesse d'un nœud (current ou prédite)."""
    data = graph.nodes.get(node_id)
    if not data:
        return 30.0  # fallback

    # Pour l'instant on retourne current_speed_kmh
    # Sprint 6+ : intégrer gold.trafic_predictions pour horizon > 0
    return float(data.get("current_speed_kmh", 30.0))



def _speed_from_highway(highway: str | None) -> float:
    """Retourne la vitesse par défaut pour un type de route (km/h)."""
    defaults = {
        "motorway": 130, "motorway_link": 80,
        "trunk": 110, "trunk_link": 80,
        "primary": 90, "primary_link": 65,
        "secondary": 70, "secondary_link": 55,
        "tertiary": 50, "tertiary_link": 40,
        "unclassified": 50, "residential": 30,
        "living_street": 10, "pedestrian": 5,
        "track": 20, "service": 20, "road": 50,
    }
    return defaults.get(highway, 50.0)


def get_nearest_node(graph: nx.Graph, lon: float, lat: float) -> str | None:
    """Trouve le nœud le plus proche d'un point (lon, lat)."""
    if graph.number_of_nodes() == 0:
        return None

    min_dist = float("inf")
    nearest = None
    for node_id, data in graph.nodes(data=True):
        # Distance euclidienne sur les endpoints
        for ep_lon, ep_lat in [(data["start_lon"], data["start_lat"]), (data["end_lon"], data["end_lat"])]:
            d = (ep_lon - lon) ** 2 + (ep_lat - lat) ** 2
            if d < min_dist:
                min_dist = d
                nearest = node_id
    return nearest


