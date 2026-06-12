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

from src.config import get_settings
from src.db import execute_query

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
    """Construit le graphe routier depuis silver.trafic_boucles_clean.

    Args:
        use_cache: si True (défaut), réutilise le cache < 5 min.
        min_segment_length_m: ignore les segments plus courts.
        endpoint_tolerance_deg: tolérance pour match endpoint (~2m).

    Returns:
        networkx.Graph (undirected) :
        - nodes : channel_id
        - nodes_attrs : length_m, current_speed_kmh, predicted_speeds,
                        start_lon, start_lat, end_lon, end_lat
        - edges : (u, v) où u et v partagent un endpoint
        - edges_attrs : via (shared endpoint)
    """
    if use_cache and _is_cache_valid():
        return _graph_cache["graph"]

    s = get_settings()
    # En dev (APP_ENV=development) et sans DB → fallback mock
    if s.app_env == "development" and not _db_available():
        logger.info("DB indisponible en dev — utilisation graphe mock")
        graph = _build_mock_graph()
    else:
        try:
            graph = _build_graph_from_db(min_segment_length_m, endpoint_tolerance_deg)
        except Exception as e:
            logger.warning(f"Échec build graph DB ({e}) — fallback mock")
            graph = _build_mock_graph()

    _graph_cache["graph"] = graph
    _graph_cache["built_at"] = time.time()
    logger.info(f"Routing graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    return graph


def _is_cache_valid() -> bool:
    return _graph_cache["graph"] is not None and (time.time() - _graph_cache["built_at"]) < CACHE_TTL_SECONDS


def reset_cache() -> None:
    """Reset le cache module-level (utile pour les tests)."""
    global _graph_cache
    _graph_cache = {
        "graph": None,
        "node_to_idx": None,
        "idx_to_node": None,
        "built_at": 0.0,
    }


def _db_available() -> bool:
    from src.db import test_connection

    return test_connection()


def _build_graph_from_db(
    min_segment_length_m: float,
    endpoint_tolerance_deg: float,
) -> nx.Graph:
    """Construit le graphe routier depuis la DB.

    Sprint 8 hotfix 2 (2026-06-12) — Le bon graphe routier n'est PAS
    silver.trafic_boucles_clean (qui sont des Points isolés par
    capteur) mais le graphe H3 déjà construit en Sprint 5 :
    * gold.dim_spatial_grid_mapping : 1520 nœuds routiers H3 res 13
    * gold.dim_gnn_adjacency : 4072 arêtes K=2 (chaque nœud relié à
      ses voisins H3 les plus proches)

    On croise avec gold.traffic_features_live pour récupérer la
    vitesse temps réel du nœud H3 le plus proche du capteur
    (mapping approximatif via lat/lon).
    """
    # 1. Charger les nœuds H3 (lat/lon par node_idx)
    nodes_query = """
        SELECT node_idx, properties_twgid AS channel_id, lat, lon
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """
    nodes_rows = execute_query(nodes_query)
    if not nodes_rows:
        raise ValueError("Aucun noeud dans gold.dim_spatial_grid_mapping")

    G = nx.Graph()  # noqa: N806

    # 2. Charger la vitesse temps réel la plus récente par node H3
    # Sprint 10+ (2026-06-12) — Le JOIN direct ``m.properties_twgid =
    # t.channel_id`` ne matche JAMAIS (LYO0xxxx ≠ "537"). On passe par
    # ``gold.mv_twgid_to_lyo`` qui mappe par proximité géographique
    # (seuil 500m). Refresh manuel : REFRESH MATERIALIZED VIEW
    # gold.mv_twgid_to_lyo;
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

    # 3. Construire les nœuds du graphe
    for r in nodes_rows:
        node_idx = int(r["node_idx"])
        G.add_node(
            node_idx,
            **{
                "length_m": 50.0,  # défaut H3 res 13 ≈ 30-50m
                "current_speed_kmh": speed_map.get(node_idx, 30.0),
                "start_lon": float(r["lon"]),
                "start_lat": float(r["lat"]),
                "end_lon": float(r["lon"]),
                "end_lat": float(r["lat"]),
            },
        )

    # 4. Construire les arêtes via dim_gnn_adjacency (K=2 H3)
    edges_query = """
        SELECT node_u, node_v
        FROM gold.dim_gnn_adjacency
        WHERE is_connected = TRUE
    """
    edges_rows = execute_query(edges_query)
    for r in edges_rows:
        u, v = int(r["node_u"]), int(r["node_v"])
        if u in G.nodes and v in G.nodes:
            # Distance haversine pour l'arête (approx edge weight)
            u_data, v_data = G.nodes[u], G.nodes[v]
            d = _haversine_m_local(u_data["start_lat"], u_data["start_lon"],
                                  v_data["start_lat"], v_data["start_lon"])
            G.add_edge(u, v, via="h3_adjacency", length_m=d)

    return G


def _haversine_m_local(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres — version locale (évite round-trip DB)."""
    import math
    r = 6_371_000  # m
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
