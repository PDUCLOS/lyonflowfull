"""Routing — graphe routier OSM (Overpass API) ou H3 fallback.

Sprint 12 (2026-06-12) — Refacto complète du graphe routier :

NOUVEAU (OSM) :
  - Source : gold.road_network_nodes + gold.road_network_edges (Overpass API)
  - Nodes = OSM node IDs (int), coords (lat, lon)
  - Edges = segments routiers avec length_m, maxspeed_kmh, travel_time_s
  - ~5000-15000 nodes selon bbox Lyon

ANCIEN (H3 fallback) :
  - Source : gold.dim_spatial_grid_mapping + gold.dim_gnn_adjacency (H3 res 13)
  - Nodes = channel_id (str), coords (start_lat, start_lon)
  - Utilisé si gold.road_network_nodes est vide (dev sans DB, ou avant premier DAG run)

Attributs des nœuds (OSM) :
  - lat, lon : coordonnées GPS
  - highway_type : type de route (motorway, primary, secondary, ...)
  - current_speed_kmh : vitesse trafic (depuis gold.traffic_features_live,
    joiné par proximité < 500m — same pattern que mv_twgid_to_lyo)

Attributs des nœuds (H3) :
  - length_m, current_speed_kmh, start_lon, start_lat, end_lon, end_lat

Le graphe est :
- Construit depuis la DB (gold)
- Cache en mémoire pendant la session (rebuild toutes les 5 min en prod)
- Fallback mock pour dev sans DB

Usage :
    from src.routing import build_routing_graph
    graph = build_routing_graph()
    graph.graph["type"]          # "osm" | "h3" | "mock"
    graph.nodes[node_id]         # attributs selon type
    graph.edges[u, v]            # {length_m, ...}
"""

from __future__ import annotations

import logging
import time
from typing import Any

import networkx as nx

from src.config import get_settings
from src.db.connection import execute_query

logger = logging.getLogger(__name__)

# Cache module-level (TTL 5 min)
_graph_cache: dict[str, Any] = {
    "graph": None,
    "built_at": 0.0,
}
CACHE_TTL_SECONDS = 300  # 5 min


def build_routing_graph(
    use_cache: bool = True,
    min_segment_length_m: float = 5.0,
) -> nx.DiGraph:
    """Construit le graphe routier.

    Stratégie (Sprint 12) :
    1. Tente de charger depuis gold.road_network_nodes/edges (OSM)
    2. Si vide → fallback H3 (dim_spatial_grid_mapping + dim_gnn_adjacency)
    3. Si DB indisponible → mock

    Args:
        use_cache: si True (défaut), réutilise le cache < 5 min.
        min_segment_length_m: longueur minimale des arêtes (OSM only).

    Returns:
        networkx.DiGraph avec :
        - graph["type"] : "osm" | "h3" | "mock"
        - nodes[nid] : {lat, lon, highway_type, current_speed_kmh, ...}
        - edges[u,v] : {length_m, maxspeed_kmh, travel_time_s, ...}
    """
    if use_cache and _is_cache_valid():
        return _graph_cache["graph"]

    s = get_settings()

    # Dev sans DB → mock
    if s.app_env == "development" and not _db_available():
        logger.info("DB indisponible en dev — graphe mock")
        graph = _build_mock_graph()
    else:
        try:
            graph = _try_build_osm_graph()
            if graph is None:
                logger.info("gold.road_network_nodes vide — fallback H3")
                graph = _build_graph_from_h3(min_segment_length_m)
        except Exception as e:
            logger.warning("OSM build failed (%s) — fallback H3", e)
            try:
                graph = _build_graph_from_h3(min_segment_length_m)
            except Exception as e2:
                logger.warning("H3 build failed (%s) — fallback mock", e2)
                graph = _build_mock_graph()

    _graph_cache["graph"] = graph
    _graph_cache["graph_type"] = "mock"
    _graph_cache["built_at"] = time.time()
    logger.info(
        "Routing graph built (%s): %d nodes, %d edges",
        graph.graph.get("type", "?"),
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


def get_graph_type() -> str:
    """Retourne le type de graphe utilisé ('overpass' | 'h3' | 'mock')."""
    return _graph_cache.get("graph_type", "unknown")


def _is_cache_valid() -> bool:
    return _graph_cache["graph"] is not None and (time.time() - _graph_cache["built_at"]) < CACHE_TTL_SECONDS


def reset_cache() -> None:
    """Reset le cache module-level (utile pour les tests)."""
    global _graph_cache
    _graph_cache = {"graph": None, "built_at": 0.0}


def _db_available() -> bool:
    from src.db.connection import test_connection

    return test_connection()


def _try_build_osm_graph(
    min_length_m: float = 0.5,
) -> nx.DiGraph | None:
    """Charge le graphe OSM depuis gold.road_network_nodes/edges.

    Returns None si la table est vide (pas encore rafraîchie par le DAG).
    """
    from src.routing.gtfs_graph_builder import DEFAULT_SPEED

    count = execute_query("SELECT COUNT(*) AS c FROM gold.road_network_nodes")
    if not count or count[0]["c"] == 0:
        return None

    G = nx.DiGraph()  # noqa: N806
    G.graph["type"] = "osm"

    # Nodes
    nodes_rows = execute_query("SELECT osm_id, lat, lon, highway_type FROM gold.road_network_nodes")

    # Speed join (optionnel — le mapping OSM node → traffic sensor
    # sera fait en Sprint 13 via géocodage proximité)
    # Pour l'instant on garde les DEFAULT_SPEED du highway_type
    try:
        speed_rows = execute_query("""
            WITH latest AS (
                SELECT DISTINCT ON (t.channel_id)
                    t.channel_id, t.speed_kmh, t.computed_at
                FROM gold.traffic_features_live t
                WHERE t.speed_kmh IS NOT NULL
                  AND t.computed_at >= NOW() - INTERVAL '1 hour'
                ORDER BY t.channel_id, t.computed_at DESC
            )
            SELECT mv.node_idx, l.speed_kmh
            FROM latest l
            JOIN gold.mv_twgid_to_lyo mv ON mv.channel_id = l.channel_id
        """)
        _ = speed_rows  # Sprint 13: map OSM nodes to nearest traffic sensor
    except Exception as e:
        logger.debug("Speed join skipped (no OSM→traffic mapping yet): %s", e)

    for r in nodes_rows:
        osm_id = int(r["osm_id"])
        highway = r.get("highway_type")
        speed = DEFAULT_SPEED.get(highway, 50) if highway else 50
        G.add_node(
            osm_id,
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            highway_type=highway,
            current_speed_kmh=float(speed),
            # Pour compatibilité avec pathfinder : length_m = 0 sur node
            # (la longueur est sur l'arête)
            length_m=0.0,
        )

    # Edges
    edges_rows = execute_query(
        """
        SELECT from_osm_id, to_osm_id, length_m, maxspeed_kmh,
               highway_type, oneway
        FROM gold.road_network_edges
        WHERE length_m >= %s
        """,
        (min_length_m,),
    )
    for r in edges_rows:
        u, v = int(r["from_osm_id"]), int(r["to_osm_id"])
        if u not in G or v not in G:
            continue
        speed = int(r["maxspeed_kmh"]) if r["maxspeed_kmh"] else DEFAULT_SPEED.get(r["highway_type"], 50)
        length = float(r["length_m"])
        travel_time_s = (length / (speed * 1000 / 3600)) if speed > 0 else 0
        G.add_edge(
            u,
            v,
            length_m=length,
            maxspeed_kmh=speed,
            highway_type=r["highway_type"],
            travel_time_s=travel_time_s,
            oneway=bool(r["oneway"]),
        )

    logger.info(
        "OSM graph: %d nodes, %d edges",
        G.number_of_nodes(),
        G.number_of_edges(),
    )
    return G


def _build_graph_from_h3(
    min_segment_length_m: float,
    endpoint_tolerance_deg: float = 0.00002,
) -> nx.Graph:
    """Construit le graphe H3 legacy (fallback si road_network_nodes vide)."""
    G = nx.Graph()  # noqa: N806
    G.graph["type"] = "h3"

    nodes_rows = execute_query(
        """
        SELECT node_idx, properties_twgid AS channel_id, lat, lon
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        """
    )
    if not nodes_rows:
        raise ValueError("gold.dim_spatial_grid_mapping vide")

    # Vitesse temps réel
    speed_rows = execute_query("""
        WITH latest AS (
            SELECT DISTINCT ON (m.node_idx)
                m.node_idx, t.speed_kmh
            FROM gold.dim_spatial_grid_mapping m
            JOIN gold.mv_twgid_to_lyo mv
              ON mv.properties_twgid = m.properties_twgid
            JOIN gold.traffic_features_live t
              ON t.channel_id = mv.channel_id
            WHERE t.computed_at >= NOW() - INTERVAL '1 hour'
              AND t.speed_kmh IS NOT NULL
            ORDER BY m.node_idx, t.computed_at DESC
        )
        SELECT node_idx, speed_kmh FROM latest
    """)
    speed_map = {r["node_idx"]: float(r["speed_kmh"]) for r in speed_rows}

    for r in nodes_rows:
        node_idx = int(r["node_idx"])
        G.add_node(
            node_idx,
            length_m=50.0,
            current_speed_kmh=speed_map.get(node_idx, 30.0),
            start_lon=float(r["lon"]),
            start_lat=float(r["lat"]),
            end_lon=float(r["lon"]),
            end_lat=float(r["lat"]),
        )

    edges_rows = execute_query("SELECT node_u, node_v FROM gold.dim_gnn_adjacency WHERE is_connected = TRUE")
    for r in edges_rows:
        u, v = int(r["node_u"]), int(r["node_v"])
        if u in G and v in G:
            u_data, v_data = G.nodes[u], G.nodes[v]
            d = _haversine_m_local(
                u_data["start_lat"],
                u_data["start_lon"],
                v_data["start_lat"],
                v_data["start_lon"],
            )
            G.add_edge(u, v, via="h3_adjacency", length_m=d)

    return G, "h3"


def _haversine_m_local(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres."""
    import math

    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _build_mock_graph() -> nx.DiGraph:
    """Graphe mock pour dev sans DB.

    Simule 12 segments dans le centre de Lyon (Part-Dieu, Bellecour, etc.)
    avec adjacences réalistes et vitesses mock.
    """
    G = nx.DiGraph()  # noqa: N806
    G.graph["type"] = "mock"

    # OSM-style nodes with lat/lon
    segments = [
        ("MOCK_C3_S01", 4.8589, 45.7607, 580, 25, "secondary"),
        ("MOCK_C3_S02", 4.8520, 45.7620, 1800, 35, "primary"),
        ("MOCK_C3_S03", 4.8461, 45.7496, 1100, 22, "secondary"),
        ("MOCK_T1_S01", 4.8342, 45.7672, 1300, 18, "tertiary"),
        ("MOCK_T1_S02", 4.8324, 45.7575, 2400, 40, "primary"),
        ("MOCK_M_A_S01", 4.8340, 45.7480, 900, 30, "secondary"),
        ("MOCK_C13_S01", 4.8461, 45.7496, 2100, 28, "primary"),
        ("MOCK_T2_S01", 4.8501, 45.7450, 1100, 32, "tertiary"),
        ("MOCK_T3_S01", 4.8700, 45.7310, 600, 22, "residential"),
        ("MOCK_C14_S01", 4.8058, 45.7798, 950, 28, "secondary"),
        ("MOCK_C3_S04", 4.8417, 45.7456, 450, 26, "tertiary"),
        ("MOCK_C3_S05", 4.8408, 45.7431, 1500, 33, "secondary"),
    ]

    for cid, lon, lat, length, speed, hw_type in segments:
        G.add_node(
            cid,
            lat=lat,
            lon=lon,
            highway_type=hw_type,
            current_speed_kmh=float(speed),
            length_m=float(length),
        )

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
        u_data, v_data = G.nodes[u], G.nodes[v]
        d = _haversine_m_local(u_data["lat"], u_data["lon"], v_data["lat"], v_data["lon"])
        speed_u, speed_v = u_data["current_speed_kmh"], v_data["current_speed_kmh"]
        speed = min(speed_u, speed_v) if (speed_u and speed_v) else (speed_u or speed_v or 30)
        travel_time = (d / (speed * 1000 / 3600)) if speed > 0 else 0
        for _u, _v in [(u, v), (v, u)]:
            if not G.has_edge(_u, _v):
                G.add_edge(_u, _v, length_m=d, travel_time_s=travel_time, highway_type="mock")

    return G


def get_node_speed(graph: nx.Graph, node_id: Any, horizon_minutes: int = 0) -> float:
    """Récupère la vitesse d'un nœud (current ou prédite).

    OSM graph : current_speed_kmh dans node attrs (défaut basé sur highway_type)
    H3 graph  : current_speed_kmh dans node attrs (depuis traffic_features_live)
    Mock     : current_speed_kmh dans node attrs
    """
    data = graph.nodes.get(node_id)
    if not data:
        return 30.0
    return float(data.get("current_speed_kmh", 30.0))


def get_nearest_node(graph: nx.Graph, lon: float, lat: float) -> Any | None:
    """Trouve le nœud le plus proche d'un point (lon, lat).

    OSM graph : cherche sur lat/lon nodes
    H3 graph  : cherche sur start_lat/start_lon ou end_lat/end_lon
    Mock     : cherche sur lat/lon
    """
    if graph.number_of_nodes() == 0:
        return None

    graph_type = graph.graph.get("type", "h3")
    min_dist = float("inf")
    nearest = None

    for node_id, data in graph.nodes(data=True):
        if graph_type == "osm" or "lat" in data:
            node_lat = data.get("lat") or data.get("start_lat")
            node_lon = data.get("lon") or data.get("start_lon")
            if node_lat is None or node_lon is None:
                continue
            d = (node_lon - lon) ** 2 + (node_lat - lat) ** 2
            if d < min_dist:
                min_dist = d
                nearest = node_id
        else:
            # H3 legacy
            for ep_lon, ep_lat in [
                (data.get("start_lon"), data.get("start_lat")),
                (data.get("end_lon"), data.get("end_lat")),
            ]:
                if ep_lon is None or ep_lat is None:
                    continue
                d = (ep_lon - lon) ** 2 + (ep_lat - lat) ** 2
                if d < min_dist:
                    min_dist = d
                    nearest = node_id

    return nearest
