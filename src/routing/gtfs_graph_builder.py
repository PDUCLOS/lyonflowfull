"""Build road network graph from OpenStreetMap (Overpass API).

Sprint 12 (2026-06-12) — Remplace le graphe H3 res 13 sparse par un vrai
graphe routier OSM. Lyon bbox : [45.65, 4.75, 45.80, 4.95].

Fonctions publiques :
- fetch_osm_roads(bbox)     → liste de ways OSM avec géométrie
- build_graph_from_osm(roads) → networkx.DiGraph (nodes = intersections,
                               edges = segments, poids = length_m + travel_time)
- store_graph_to_db()       → persiste dans gold.road_network_nodes/edges
- build_and_store()        → fetch + build + store (usage DAG)

Le graphe OSM est un DiGraph : chaque way OSM crée 2 arêtes (A→B et B→A)
sauf si oneway=yes (alors 1 seule arête A→B).

Usage standalone (dev) :
    from src.routing.gtfs_graph_builder import build_and_store
    build_and_store()
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import time
from typing import Any

import networkx as nx
import psycopg2.extras
import requests

from src.db.connection import raw_connection

logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass.openstreetmap.fr/api/interpreter",  # French server, closer to Lyon
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Lyon intra-muros + proches suburbs
LYON_BBOX = [45.65, 4.75, 45.80, 4.95]  # [lat_s, lon_w, lat_n, lon_e]

# Highway types à récupérer (hierarchy, du plus important au plus secondaire)
HIGHWAY_TYPES = [
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
]

# Vitesses par défaut Lyon (km/h) — used quand maxspeed manquant
DEFAULT_SPEED: dict[str, int] = {
    "motorway": 130,
    "motorway_link": 70,
    "trunk": 110,
    "trunk_link": 70,
    "primary": 80,
    "primary_link": 50,
    "secondary": 70,
    "secondary_link": 50,
    "tertiary": 60,
    "tertiary_link": 50,
    "unclassified": 50,
    "residential": 30,
}

# Cache Overpass (TTL 6h — le réseau OSM ne change pas toutes les heures)
_overpass_cache: dict[str, tuple[list[dict], float]] = {}
_CACHE_TTL = 6 * 3600


# ---------------------------------------------------------------------------
# Overpass fetch
# ---------------------------------------------------------------------------


def _overpass_cache_key(bbox: list[float]) -> str:
    """Hash stable pour le cache Overpass (basé sur bbox uniquement)."""
    key = json.dumps({"bbox": bbox}, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _build_overpass_query(bbox: list[float]) -> str:
    """Construit la requête Overpass pour les routes Lyon."""
    lat_s, lon_w, lat_n, lon_e = bbox
    # Regex OR sur highway_type : "highway"~"motorway|trunk|primary|..."
    highway_regex = "|".join(HIGHWAY_TYPES)
    return f"""[out:json][timeout:90];
way({lat_s},{lon_w},{lat_n},{lon_e})["highway"~"{highway_regex}"];
out body;
>;
out skel qt;
"""


def fetch_osm_roads(bbox: list[float] = LYON_BBOX, use_cache: bool = True) -> list[dict[str, Any]]:
    """Fetch les ways routiers OSM dans une bbox via Overpass API.

    Args:
        bbox: [lat_s, lon_w, lat_n, lon_e]
        use_cache: utiliser le cache 6h (défaut True).

    Returns:
        Liste de dicts way OSM avec clés : {id, tags, geometry: [{lat,lon}]}.
        Vide si Overpass échoue.

    Performance :
    - Overpass API publique : ~2-5s pour Lyon intra-muros
    - Rate limit : 10 req/s (on est bien en dessous)
    """
    cache_key = _overpass_cache_key(bbox)

    if use_cache:
        cached = _overpass_cache.get(cache_key)
        if cached and (time.time() - cached[1]) < _CACHE_TTL:
            logger.info("Overpass cache hit (%s) — %d ways", cache_key, len(cached[0]))
            return cached[0]

    query = _build_overpass_query(bbox)
    logger.info("Fetching Overpass for bbox=%s (cache_key=%s)", bbox, cache_key)

    last_error = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(
                url,
                data={"data": query},
                timeout=60,
                headers={"User-Agent": "LyonFlow/1.0 (traffic-routing; patrice@lyonflow.local)"},
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except (requests.RequestException, json.JSONDecodeError) as e:
            last_error = e
            logger.warning("Overpass query failed for %s: %s", url, e)
            continue
    else:
        # All endpoints failed
        logger.error("All Overpass endpoints failed. Last error: %s", last_error)
        return []

    elements = data.get("elements", [])

    # Séparer nodes (géométrie) et ways (topologie)
    nodes_map: dict[int, dict] = {}
    ways: list[dict[str, Any]] = []

    for el in elements:
        if el["type"] == "node":
            nodes_map[el["id"]] = {"id": el["id"], "lat": el["lat"], "lon": el["lon"]}
        elif el["type"] == "way":
            ways.append(
                {
                    "id": el["id"],
                    "tags": el.get("tags", {}),
                    "node_refs": el.get("nodes", []),
                }
            )

    # Attacher la géométrie à chaque way
    for way in ways:
        way["geometry"] = [nodes_map[nid] for nid in way["node_refs"] if nid in nodes_map]

    # Filter : au moins 2 points de géométrie
    ways = [w for w in ways if len(w["geometry"]) >= 2]

    _overpass_cache[cache_key] = (ways, time.time())
    logger.info("Overpass fetched %d ways, %d nodes", len(ways), len(nodes_map))
    return ways


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_maxspeed(tag: str | None) -> int | None:
    """Parse la valeur maxspeed OSM en km/h (int) ou None."""
    if not tag:
        return None
    tag = tag.strip().lower()
    if tag.endswith(" km/h"):
        try:
            return int(tag.replace(" km/h", ""))
        except ValueError:
            return None
    if tag.endswith(" mph"):
        try:
            return int(float(tag.replace(" mph", "")) * 1.60934)
        except ValueError:
            return None
    if tag == "national":
        return 110
    if tag == "urban":
        return 50
    if tag == "living_street":
        return 10
    try:
        return int(tag)
    except ValueError:
        return None


def _get_speed_kmh(tags: dict, highway_type: str) -> int:
    """Retourne la vitesse max en km/h (défaut basé sur highway_type)."""
    raw = tags.get("maxspeed")
    parsed = _parse_maxspeed(raw)
    if parsed:
        return parsed
    return DEFAULT_SPEED.get(highway_type, 50)


def build_graph_from_osm(
    roads: list[dict[str, Any]],
) -> nx.DiGraph:
    """Construit un DiGraph NetworkX depuis les ways OSM.

    Stratégie :
    - Chaque node OSM = un nœud du graphe (osm_id → node key)
    - Chaque segment entre 2 nodes adjacents d'un même way = une arête
    - oneway=yes → 1 arête (A→B), sinon 2 arêtes (A→B et B→A)
    - Attributs edge : length_m, maxspeed_kmh, highway_type, travel_time_s

    Les ways avec des nœuds intermédiaires (intersections au milieu)
    créent plusieurs arêtes → le graphe est correct topologiquement.

    Args:
        roads: résultat de fetch_osm_roads().

    Returns:
        networkx.DiGraph avec :
        - nodes[osm_id] : {lat, lon, highway_type}
        - edges[u→v]   : {length_m, maxspeed_kmh, highway_type, travel_time_s,
                          osm_way_id, oneway}
    """
    G = nx.DiGraph()  # noqa: N806  # noqa: N806

    for way in roads:
        way_id = way["id"]
        tags = way["tags"]
        geom = way["geometry"]
        highway = tags.get("highway", "unclassified")
        speed_kmh = _get_speed_kmh(tags, highway)

        # Pour chaque paire de nœuds consécutifs dans le way
        for i in range(len(geom) - 1):
            a, b = geom[i], geom[i + 1]
            a_id = a["id"]
            b_id = b["id"]

            # Ajouter les nœuds (premier vu = définit le highway_type)
            for nd in (a, b):
                if nd["id"] not in G:
                    G.add_node(nd["id"], lat=nd["lat"], lon=nd["lon"], highway_type=highway)

            length_m = _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            # travel_time_s : length_m / (speed_kmh * 1000/3600)
            travel_time_s = (length_m / (speed_kmh * 1000 / 3600)) if speed_kmh > 0 else 0

            oneway_val = tags.get("oneway", "no")
            edge_attrs = {
                "length_m": length_m,
                "maxspeed_kmh": speed_kmh,
                "highway_type": highway,
                "osm_way_id": way_id,
                "travel_time_s": travel_time_s,
                "oneway": oneway_val in ("yes", "true", "1", "-1"),
            }
            if oneway_val == "-1":
                # Sens inverse uniquement : b → a
                G.add_edge(b_id, a_id, **edge_attrs)
            elif oneway_val in ("yes", "true", "1"):
                # Sens normal uniquement : a → b
                G.add_edge(a_id, b_id, **edge_attrs)
            else:
                # Bidirectionnel : a → b ET b → a
                G.add_edge(a_id, b_id, **edge_attrs)
                G.add_edge(b_id, a_id, **edge_attrs)

    # Post-processing : supprimer les arêtes de longueur nulle (nœud dup)
    for u, v in list(G.edges()):
        if G[u][v]["length_m"] < 1.0:
            G.remove_edge(u, v)

    logger.info(
        "Graph built from OSM: %d nodes, %d edges",
        G.number_of_nodes(),
        G.number_of_edges(),
    )
    return G


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


def store_graph_to_db(
    G: nx.DiGraph,  # noqa: N803
    bbox: list[float] = LYON_BBOX,
    status: str = "success",
    error_msg: str | None = None,
) -> dict[str, int]:
    """Persiste le graphe dans gold.road_network_nodes/edges.

    Idempotent : TRUNCATE avant INSERT (le graphe entier est rechargé à chaque
    refresh, pas de versioning incrémental).

    Args:
        G: DiGraph NetworkX (résultat de build_graph_from_osm).
        bbox: bbox utilisée pour le fetch Overpass.
        status: 'success' | 'error'
        error_msg: message d'erreur si status='error'.

    Returns:
        {nodes_stored, edges_stored, refresh_id}
    """
    with raw_connection() as conn, conn.cursor() as cur:
        # 1. TRUNCATE (réinitialise le graphe)
        cur.execute("TRUNCATE gold.road_network_nodes CASCADE")
        cur.execute("TRUNCATE gold.road_network_edges RESTART IDENTITY")

        # 2. Insert nodes
        node_rows: list[tuple] = []
        for osm_id, data in G.nodes(data=True):
            node_rows.append(
                (
                    osm_id,
                    float(data["lat"]),
                    float(data["lon"]),
                    data.get("highway_type"),
                )
            )

        if node_rows:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO gold.road_network_nodes
                    (osm_id, lat, lon, highway_type)
                VALUES %s
                ON CONFLICT (osm_id) DO UPDATE SET
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    highway_type = EXCLUDED.highway_type
                """,
                node_rows,
                page_size=500,
            )

        # 3. Insert edges
        edge_rows: list[tuple] = []
        for u, v, data in G.edges(data=True):
            edge_rows.append(
                (
                    u,
                    v,
                    float(data["length_m"]),
                    data.get("maxspeed_kmh"),
                    data.get("highway_type"),
                    data.get("osm_way_id"),
                    bool(data.get("oneway", False)),
                )
            )

        if edge_rows:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO gold.road_network_edges
                    (from_osm_id, to_osm_id, length_m, maxspeed_kmh, highway_type,
                     osm_way_id, oneway)
                VALUES %s
                ON CONFLICT (from_osm_id, to_osm_id) DO UPDATE SET
                    length_m = EXCLUDED.length_m,
                    maxspeed_kmh = EXCLUDED.maxspeed_kmh,
                    highway_type = EXCLUDED.highway_type,
                    osm_way_id = EXCLUDED.osm_way_id,
                    oneway = EXCLUDED.oneway
                """,
                edge_rows,
                page_size=500,
            )

        # 4. Log entry
        bbox_str = str(bbox)
        query_hash = _overpass_cache_key(bbox)
        cur.execute(
            """
            INSERT INTO gold.road_network_refresh_log
                (nodes_count, edges_count, bbox_used, osm_query_hash, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (len(node_rows), len(edge_rows), bbox_str, query_hash, status),
        )
        refresh_id = cur.fetchone()[0]

    logger.info(
        "Stored %d nodes, %d edges to gold.road_network_* (refresh_id=%d)",
        len(node_rows),
        len(edge_rows),
        refresh_id,
    )
    return {
        "nodes_stored": len(node_rows),
        "edges_stored": len(edge_rows),
        "refresh_id": refresh_id,
    }


def build_and_store(
    bbox: list[float] = LYON_BBOX,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch Overpass + build graph + store to DB.

    Usage DAG :
        build_and_store() → {roads_fetched, nodes, edges, refresh_id}

    Args:
        bbox: bbox Lyon.
        use_cache: cache Overpass.

    Returns:
        Dict avec counts et refresh_id, ou {error: str} si échec.
    """
    started = time.time()
    logger.info("Starting road network build for bbox=%s", bbox)

    try:
        roads = fetch_osm_roads(bbox=bbox, use_cache=use_cache)
        if not roads:
            raise RuntimeError("Overpass returned 0 ways")

        G = build_graph_from_osm(roads)  # noqa: N806
        result = store_graph_to_db(G, bbox=bbox, status="success")
        duration = time.time() - started
        logger.info(
            "Road network build complete in %.1fs: %d nodes, %d edges",
            duration,
            result["nodes_stored"],
            result["edges_stored"],
        )
        return {
            "roads_fetched": len(roads),
            "nodes_stored": result["nodes_stored"],
            "edges_stored": result["edges_stored"],
            "refresh_id": result["refresh_id"],
            "duration_s": round(duration, 1),
        }

    except Exception as e:
        logger.error("Road network build failed: %s", e)
        # Log error even on failure
        with contextlib.suppress(Exception):
            store_graph_to_db(nx.DiGraph(), bbox=bbox, status="error", error_msg=str(e))
        return {"error": str(e)}


def load_graph_from_db() -> nx.DiGraph:
    """Charge le graphe depuis gold.road_network_nodes/edges (pas Overpass).

    Utilisé par graph.py pour remplacer le build H3.
    """
    G = nx.DiGraph()  # noqa: N806  # noqa: N806

    with raw_connection() as conn, conn.cursor() as cur:
        # Charger nodes
        cur.execute(
            """
            SELECT osm_id, lat, lon, highway_type
            FROM gold.road_network_nodes
            """
        )
        for row in cur:
            osm_id, lat, lon, highway_type = row
            G.add_node(osm_id, lat=float(lat), lon=float(lon), highway_type=highway_type)

        # Charger edges
        cur.execute(
            """
            SELECT from_osm_id, to_osm_id, length_m, maxspeed_kmh, highway_type
            FROM gold.road_network_edges
            """
        )
        for row in cur:
            from_id, to_id, length_m, maxspeed, htype = row
            speed = int(maxspeed) if maxspeed else DEFAULT_SPEED.get(htype, 50)
            travel_time_s = (float(length_m) / (speed * 1000 / 3600)) if speed > 0 else 0
            G.add_edge(
                from_id,
                to_id,
                length_m=float(length_m),
                maxspeed_kmh=speed,
                highway_type=htype,
                travel_time_s=travel_time_s,
                oneway=False,
            )

    logger.info("Loaded road graph from DB: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def reset_overpass_cache() -> None:
    """Reset le cache Overpass (utile pour forcer un re-fetch)."""
    _overpass_cache.clear()
