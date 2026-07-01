"""Routing — Intégration du réseau routier OSM via pgRouting.

Le calcul des chemins optimaux en voiture est délégué à la fonction PostGIS
`pgr_dijkstra` côté base de données PostgreSQL, sur le réseau routier
OpenStreetMap (OSM) importé via `osm2pgrouting`.

Fonctions publiques exposées :
- ``compute_route_pgrouting(origin_lon, origin_lat, dest_lon, dest_lat)`` — Appel SQL pgRouting.
- ``compute_route_pgrouting_ksp(...)`` — K itinéraires alternatifs (Yen).
- ``get_nearest_osm_node(lon, lat)`` — Trouve le nœud OSM le plus proche d'un point GPS.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Routing voiture via pgRouting (extension PostgreSQL)
# =============================================================================
def compute_route_pgrouting(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
) -> list[dict] | None:
    """Calcule un itinéraire voiture via pgr_dijkstra (réseau routier OSM).

    Appelle la fonction SQL `osm.route_car()` qui :
    1. Trouve les nœuds OSM les plus proches de l'origine / destination
    2. Exécute pgr_dijkstra dirigé avec coûts trafic temps réel
    3. Retourne le chemin avec la géométrie réelle de chaque arête (LineString)

    Args:
        origin_lon, origin_lat: coords GPS du point de départ.
        dest_lon, dest_lat: coords GPS du point d'arrivée.

    Returns:
        Liste de dicts par arête du chemin :
        {seq, edge_id, cost_s, agg_cost_s, length_m, speed_kmh,
         road_name, geom_coordinates}
        où ``geom_coordinates`` est une liste de [lon, lat] représentant
        la polyline OSM de l'arête (peut être multi-vertices).
        Retourne ``None`` si pas de chemin ou DB indispo.
    """
    from src.db import execute_query

    rows = execute_query(
        "SELECT * FROM osm.route_car(%s, %s, %s, %s)",
        (origin_lon, origin_lat, dest_lon, dest_lat),
    )
    if not rows:
        return None

    result = []
    for r in rows:
        geojson_str = r.get("geom_geojson")
        geom_coords: list[list[float]] = []
        if geojson_str:
            try:
                geom = json.loads(geojson_str)
                # GeoJSON LineString : {"type": "LineString", "coordinates": [[lon, lat], ...]}
                geom_coords = geom.get("coordinates", [])
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.warning("geom_geojson invalide pour edge_id=%s", r.get("edge_id"))
        result.append(
            {
                "seq": int(r["seq"]),
                "edge_id": int(r["edge_id"]),
                "cost_s": float(r["cost_s"] or 0.0),
                "agg_cost_s": float(r["agg_cost_s"] or 0.0),
                "length_m": float(r["length_m"] or 0.0),
                "speed_kmh": float(r["speed_kmh"] or 30.0),
                "road_name": r.get("road_name") or "",
                "geom_coordinates": geom_coords,
            }
        )
    return result


# =============================================================================
# K-shortest paths pour afficher des alternatives à l'usager
# =============================================================================
def compute_route_pgrouting_ksp(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    k: int = 3,
) -> list[list[dict]] | None:
    """Calcule K itinéraires voiture alternatifs via pgr_ksp (algorithme Yen).

      Wrapper sur ``osm.route_car_ksp()`` côté PostgreSQL. Chaque route retournée
      est une liste d'arêtes avec géométrie OSM (identique au contrat de
      ``compute_route_pgrouting``).

    (2026-06-22) : usager veut comparer des alternatives réelles
      au lieu d'avoir toujours le même Dijkstra (surtout quand capteurs
      trafic couvrent mal la zone).

      Args:
          origin_lon, origin_lat: coords GPS du point de départ.
          dest_lon, dest_lat: coords GPS du point d'arrivée.
          k: nombre d'alternatives (1..5, défaut 3).

      Returns:
          Liste de K routes, chaque route étant une liste de dicts d'arêtes
          (même format que ``compute_route_pgrouting``). Chaque arête a en
          plus la clé ``total_length_m`` / ``total_cost_s`` (dupliqués sur
          toutes les lignes pour affichage rapide client).
          ``None`` si pas de chemin ou DB indispo.
    """
    from src.db import execute_query

    rows = execute_query(
        "SELECT * FROM osm.route_car_ksp(%s, %s, %s, %s, %s)",
        (origin_lon, origin_lat, dest_lon, dest_lat, k),
    )
    if not rows:
        return None

    # Grouper par route_id (1..K)
    routes_dict: dict[int, list[dict]] = {}
    for r in rows:
        route_id = int(r["route_id"])
        geojson_str = r.get("geom_geojson")
        geom_coords: list[list[float]] = []
        if geojson_str:
            try:
                geom = json.loads(geojson_str)
                geom_coords = geom.get("coordinates", [])
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.warning("geom_geojson invalide pour route=%s edge=%s", route_id, r.get("edge_id"))

        routes_dict.setdefault(route_id, []).append(
            {
                "seq": int(r["seq"]),
                "edge_id": int(r["edge_id"]),
                "cost_s": float(r["cost_s"] or 0.0),
                "agg_cost_s": float(r["agg_cost_s"] or 0.0),
                "length_m": float(r["length_m"] or 0.0),
                "speed_kmh": float(r["speed_kmh"] or 30.0),
                "road_name": r.get("road_name") or "",
                "geom_coordinates": geom_coords,
                "total_length_m": float(r["total_length_m"] or 0.0),
                "total_cost_s": float(r["total_cost_s"] or 0.0),
            }
        )

    # Trier par route_id pour ordre stable, et par seq dans chaque route
    routes = []
    for route_id in sorted(routes_dict.keys()):
        route_edges = sorted(routes_dict[route_id], key=lambda e: e["seq"])
        routes.append(route_edges)
    return routes if routes else None


def get_nearest_osm_node(lon: float, lat: float) -> int | None:
    """Trouve le nœud OSM le plus proche d'un point GPS.

    Args:
        lon, lat: coordonnées GPS (WGS84).

    Returns:
        ID du nœud OSM (ways_vertices_pgr.id) ou None si aucun résultat.
    """
    from src.db import execute_query

    rows = execute_query(
        """
        SELECT id FROM osm.ways_vertices_pgr
        ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1
        """,
        (lon, lat),
    )
    return int(rows[0]["id"]) if rows else None
