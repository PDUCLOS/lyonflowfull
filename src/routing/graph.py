"""Routing — graphe routier à partir de gold.road_network_nodes (Overpass/OSM).

Sprint 12 (2026-06-12) — Le graphe Overpass est préféré au H3 sparse
quand gold.road_network_nodes contient >= 5000 nœuds.

Hiérarchie :
1. gold.road_network_nodes + gold.road_network_edges  (Overpass/OSM, preferred)
2. gold.dim_spatial_grid_mapping + gold.dim_gnn_adjacency (H3 fallback)

Les graphes sont :
- Construits depuis la DB (silver / gold)
- Cache en mémoire pendant la session (rebuild toutes les 5 min en prod)
- Fallback mock pour dev sans DB
"""
from __future__ import annotations

import logging
import time

import networkx as nx

from src.config import get_settings
from src.db import execute_query

logger = logging.getLogger(__name__)

# Cache module-level (TTL 5 min)
_graph_cache: dict = {
    "graph": None,
    "graph_type": None,  # "overpass" | "h3" | "mock"
    "node_to_idx": None,
    "idx_to_node": None,
    "built_at": 0.0,
}
CACHE_TTL_SECONDS = 300  # 5 min


def build_routing_graph(
    use_cache: bool = True,
    min_segment_length_m: float = 5.0,
) -> nx.Graph:
    """Construit le graphe routier (Overpass preferred, H3 fallback).

    Sprint 12 (2026-06-12) : tente d'abord build_road_network_graph()
    (Overpass/OSM, 5000+ nodes). Si < 5000 nodes ou erreur → H3 fallback.

    Args:
        use_cache: si True (défaut), réutilise le cache < 5 min.
        min_segment_length_m: ignore les segments plus courts.

    Returns:
        networkx.Graph (undirected) :
        - nodes : node_id (osm_id ou node_idx H3)
        - nodes_attrs : length_m, current_speed_kmh, start_lon, start_lat, end_lon, end_lat
        - edges : (u, v)
        - edges_attrs : length_m, via, road_gid
    """
    if use_cache and _is_cache_valid():
        return _graph_cache["graph"]

    from src.data.db_query import _is_db_available

    if not _db_available():
        logger.info("DB indisponible — graphe mock")
        graph = _build_mock_graph()
        _graph_cache["graph"] = graph
        _graph_cache["graph_type"] = "mock"
        _graph_cache["built_at"] = time.time()
        return graph

    # Sprint 12: essayer Overpass d'abord
    try:
        graph, gtype = build_road_network_graph(min_segment_length_m)
        _graph_cache["graph"] = graph
        _graph_cache["graph_type"] = gtype
        _graph_cache["built_at"] = time.time()
        logger.info(
            "Routing graph (%s): %d nodes, %d edges",
            gtype, graph.number_of_nodes(), graph.number_of_edges(),
        )
        return graph
    except Exception as e:
        logger.warning("Overpass graph failed (%s) — H3 fallback", e)

    # Fallback H3
    try:
        graph, gtype = build_h3_graph(min_segment_length_m)
        _graph_cache["graph"] = graph
        _graph_cache["graph_type"] = gtype
        _graph_cache["built_at"] = time.time()
        logger.info(
            "Routing graph (%s): %d nodes, %d edges",
            gtype, graph.number_of_nodes(), graph.number_of_edges(),
        )
        return graph
    except Exception as e:
        logger.warning("H3 graph failed (%s) — mock fallback", e)
        graph = _build_mock_graph()

    _graph_cache["graph"] = graph
    _graph_cache["graph_type"] = "mock"
    _graph_cache["built_at"] = time.time()
    return graph


def get_graph_type() -> str:
    """Retourne le type de graphe utilisé ('overpass' | 'h3' | 'mock')."""
    return _graph_cache.get("graph_type", "unknown")


def _is_cache_valid() -> bool:
    return (
        _graph_cache["graph"] is not None
        and (time.time() - _graph_cache["built_at"]) < CACHE_TTL_SECONDS
    )


def reset_cache() -> None:
    """Reset le cache module-level (utile pour les tests)."""
    global _graph_cache
    _graph_cache = {
        "graph": None,
        "graph_type": None,
        "node_to_idx": None,
        "idx_to_node": None,
        "built_at": 0.0,
    }


def _db_available() -> bool:
    from src.db import test_connection
    return test_connection()


# ── Overpass/OSM graph ───────────────────────────────────────────────────────

def build_road_network_graph(
    min_segment_length_m: float = 5.0,
) -> tuple[nx.Graph, str]:
    """Construit le graphe depuis gold.road_network_nodes (Overpass/OSM).

    Sprint 12 (2026-06-12) : chaque nœud = 1 OSM node, chaque arête = 1
    segment routier avec length_m et maxspeed_kmh.

    Returns:
        (graph, "overpass")
    """
    # 1. Charger les nœuds
    nodes_query = """
        SELECT osm_id, lat, lon, highway_type, ways_count
        FROM gold.road_network_nodes
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """
    nodes_rows = execute_query(nodes_query)
    if not nodes_rows:
        raise ValueError("gold.road_network_nodes est vide")

    # 2. Charger les arêtes
    edges_query = """
        SELECT from_osm_id, to_osm_id, length_m, maxspeed_kmh, highway_type, oneway
        FROM gold.road_network_edges
        WHERE length_m >= %s
    """
    edges_rows = execute_query(edges_query, (min_segment_length_m,))

    # 3. Charger la vitesse temps réel
    speed_query = """
        WITH latest AS (
            SELECT DISTINCT ON (mv.node_idx)
                mv.node_idx, t.speed_kmh
            FROM gold.dim_spatial_grid_mapping m
            JOIN gold.mv_twgid_to_lyo mv ON mv.properties_twgid = m.properties_twgid
            JOIN gold.traffic_features_live t ON t.channel_id = mv.channel_id
            WHERE t.computed_at >= NOW() - INTERVAL '1 hour'
              AND t.speed_kmh IS NOT NULL
            ORDER BY m.node_idx, t.computed_at DESC
        )
        SELECT node_idx, speed_kmh FROM latest
    """
    speed_map = {r["node_idx"]: float(r["speed_kmh"]) for r in execute_query(speed_query)}

    G = nx.Graph()  # noqa: N806

    # 4. Ajouter les nœuds
    for r in nodes_rows:
        osm_id = str(r["osm_id"])
        highway = r.get("highway_type")
        default_speed = _speed_from_highway(highway) if highway else 50.0
        G.add_node(
            osm_id,
            **{
                "length_m": 50.0,  # default, overridden by edge length
                "current_speed_kmh": default_speed,
                "start_lon": float(r["lon"]),
                "start_lat": float(r["lat"]),
                "end_lon": float(r["lon"]),
                "end_lat": float(r["lat"]),
                "highway_type": highway,
                "ways_count": r.get("ways_count", 1),
            },
        )

    # 5. Ajouter les arêtes
    for r in edges_rows:
        from_id = str(r["from_osm_id"])
        to_id = str(r["to_osm_id"])
        if from_id not in G.nodes or to_id not in G.nodes:
            continue

        length_m = float(r["length_m"])
        maxspeed = float(r["maxspeed_kmh"]) if r.get("maxspeed_kmh") else None
        highway = r.get("highway_type")

        # Use maxspeed if available, else default from highway type
        speed = maxspeed if maxspeed else _speed_from_highway(highway)
        travel_time_s = (length_m / (speed * 1000 / 3600)) if speed > 0 else 0

        G.add_edge(
            from_id, to_id,
            length_m=length_m,
            via="overpass",
            road_gid=r.get("osm_way_id"),
            travel_time_s=travel_time_s,
            weighted_speed_kmh=speed,
        )

    return G, "overpass"


def _speed_from_highway(highway: str | None) -> float:
    """Retourne la vitesse par défaut pour un type de route (km/h)."""
    defaults = {
        "motorway": 130,
        "motorway_link": 80,
        "trunk": 110,
        "trunk_link": 80,
        "primary": 90,
        "primary_link": 65,
        "secondary": 70,
        "secondary_link": 55,
        "tertiary": 50,
        "tertiary_link": 40,
        "unclassified": 50,
        "residential": 30,
        "living_street": 10,
        "pedestrian": 5,
        "track": 20,
        "service": 20,
        "road": 50,
    }
    return defaults.get(highway, 50.0)


# ── H3 fallback graph ───────────────────────────────────────────────────────

def build_h3_graph(
    min_segment_length_m: float = 5.0,
) -> tuple[nx.Graph, str]:
    """Construit le graphe H3 (fallback Sprint 8)."""
    nodes_query = """
        SELECT node_idx, properties_twgid AS channel_id, lat, lon
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """
    nodes_rows = execute_query(nodes_query)
    if not nodes_rows:
        raise ValueError("gold.dim_spatial_grid_mapping est vide")

    speed_query = """
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
    """
    speed_map = {r["node_idx"]: float(r["speed_kmh"]) for r in execute_query(speed_query)}

    G = nx.Graph()  # noqa: N806

    for r in nodes_rows:
        node_idx = int(r["node_idx"])
        G.add_node(
            node_idx,
            **{
                "length_m": 50.0,
                "current_speed_kmh": speed_map.get(node_idx, 30.0),
                "start_lon": float(r["lon"]),
                "start_lat": float(r["lat"]),
                "end_lon": float(r["lon"]),
                "end_lat": float(r["lat"]),
            },
        )

    edges_query = """
        SELECT node_u, node_v
        FROM gold.dim_gnn_adjacency
        WHERE is_connected = TRUE
    """
    edges_rows = execute_query(edges_query)
    for r in edges_rows:
        u, v = int(r["node_u"]), int(r["node_v"])
        if u in G.nodes and v in G.nodes:
            u_data, v_data = G.nodes[u], G.nodes[v]
            d = _haversine_m_local(
                u_data["start_lat"], u_data["start_lon"],
                v_data["start_lat"], v_data["start_lon"],
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


# ── Mock graph ────────────────────────────────────────────────────────────────

def _build_mock_graph() -> nx.Graph:
    """Graphe mock pour dev sans DB."""
    G = nx.Graph()  # noqa: N806

    segments = [
        ("MOCK_C3_S01", 4.8589, 45.7607, 4.8520, 45.7620, 580, 25),
        ("MOCK_C3_S02", 4.8520, 45.7620, 4.8461, 45.7496, 1800, 35),
        ("MOCK_C3_S03", 4.8461, 45.7496, 4.8417, 45.7456, 1100, 22),
        ("MOCK_T1_S01", 4.8342, 45.7672, 4.8324, 45.7575, 1300, 18),
        ("MOCK_T1_S02", 4.8324, 45.7575, 4.8165, 45.7405, 2400, 40),
        ("MOCK_M_A_S01", 4.8340, 45.7480, 4.8360, 45.7513, 900, 30),
        ("MOCK_C13_S01", 4.8461, 45.7496, 4.8343, 45.7673, 2100, 28),
        ("MOCK_T2_S01", 4.8501, 45.7450, 4.8350, 45.7450, 1100, 32),
        ("MOCK_T3_S01", 4.8700, 45.7310, 4.8700, 45.7290, 600, 22),
        ("MOCK_C14_S01", 4.8058, 45.7798, 4.8059, 45.7722, 950, 28),
        ("MOCK_C3_S04", 4.8417, 45.7456, 4.8408, 45.7431, 450, 26),
        ("MOCK_C3_S05", 4.8408, 45.7431, 4.8325, 45.7324, 1500, 33),
    ]

    for cid, slon, slat, elon, elat, length, speed in segments:
        G.add_node(
            cid,
            length_m=length,
            current_speed_kmh=speed,
            start_lon=slon,
            start_lat=slat,
            end_lon=elon,
            end_lat=elat,
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
        G.add_edge(u, v, via="mock")

    return G


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_node_speed(graph: nx.Graph, node_id, horizon_minutes: int = 0) -> float:
    """Récupère la vitesse d'un nœud (current ou prédite)."""
    data = graph.nodes.get(node_id)
    if not data:
        return 30.0
    return float(data.get("current_speed_kmh", 30.0))


def get_nearest_node(graph: nx.Graph, lon: float, lat: float) -> str | None:
    """Trouve le nœud le plus proche d'un point (lon, lat)."""
    if graph.number_of_nodes() == 0:
        return None

    min_dist = float("inf")
    nearest = None
    for node_id, data in graph.nodes(data=True):
        for ep_lon, ep_lat in [
            (data["start_lon"], data["start_lat"]),
            (data["end_lon"], data["end_lat"]),
        ]:
            d = (ep_lon - lon) ** 2 + (ep_lat - lat) ** 2
            if d < min_dist:
                min_dist = d
                nearest = node_id
    return nearest