"""Pathfinding — routing voiture via pgRouting (Sprint 26+).

Sprint 26 (2026-06-21) — Remplace A* sur graphe NetworkX H3 par
`pgr_dijkstra` côté PostgreSQL (réseau routier OSM réel).

API publique :
- ``compute_itinerary(origin_lon, origin_lat, dest_lon, dest_lat)`` —
  retourne un ``Itinerary`` avec géométrie multi-vertices par segment.

L'interface est rétro-compatible : ``plan_car_trip()`` et
``_road_itinerary_between()`` (pathfinder_multimodal.py) continuent
de fonctionner sans modification.

Sprint 16 Axe C : retourne aussi ``confidence`` (basée sur la
couverture des capteurs Grand Lyon via ``osm.mv_sensor_to_way``).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

from src.routing.graph import compute_route_pgrouting, compute_route_pgrouting_ksp

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Cache TTL simple pour _compute_pgrouting_confidence
# -----------------------------------------------------------------------------
# La métrique "couverture capteurs" est globale (pas per-route) et change
# lentement (1h suffit). On évite ainsi de re-calculer le COUNT/LEFT JOIN
# sur gold.traffic_features_live à CHAQUE itinéraire calculé — ce qui
# sature sdb en cas d'usage concurrent.
_CONFIDENCE_CACHE: dict[str, tuple[float, float]] = {}
_CONFIDENCE_TTL_S = 3600.0  # 1h


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres (utilisé en fallback)."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class ItinerarySegment:
    """Un segment dans l'itinéraire.

    Attributes:
        channel_id: identifiant lisible (nom de rue OSM ou edge_id).
        length_m: longueur du segment en mètres.
        speed_kmh: vitesse moyenne estimée sur le segment.
        duration_s: durée de parcours en secondes.
        start_lon, start_lat: coordonnées du point de départ (premier vertex).
        end_lon, end_lat: coordonnées du point d'arrivée (dernier vertex).
        geometry: polyline OSM [[lon, lat], ...] ou None si non disponible.
    """

    channel_id: str
    length_m: float
    speed_kmh: float
    duration_s: float
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    geometry: list[list[float]] | None = None


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
    confidence: float = 0.0  # 0..1, basé sur la couverture capteurs

    @property
    def total_duration_min(self) -> float:
        return self.total_duration_s / 60.0


def _compute_pgrouting_confidence() -> float:
    """Calcule la confiance basée sur la couverture réelle des capteurs.

    - coverage_ratio = % d'arêtes OSM qui ont un capteur Grand Lyon nearby
      avec vitesse temps réel < 1h
    - confidence = 0.5 + 0.5 * coverage_ratio (plancher 50%, max 100%)

    Sans capteur → utilise maxspeed_forward OSM (estimation moins fiable).
    Avec capteur → vitesse réelle = haute confiance.

    **Cache TTL 1h** : la métrique est globale (pas per-route) et change
    lentement. Sans cache, chaque appel fait un COUNT + LEFT JOIN lourd
    sur ``gold.traffic_features_live`` qui sature sdb en cas d'usage
    concurrent (cf. incident 2026-06-22).

    Returns:
        float entre 0.5 et 1.0
    """
    cache_key = "pgrouting_confidence"
    now = time.monotonic()
    cached = _CONFIDENCE_CACHE.get(cache_key)
    if cached is not None:
        cached_at, value = cached
        if now - cached_at < _CONFIDENCE_TTL_S:
            return value

    try:
        from src.db import execute_query

        rows = execute_query("""
            WITH coverage AS (
                SELECT
                    COUNT(*) AS total_ways,
                    COUNT(*) FILTER (
                        WHERE t.speed_kmh IS NOT NULL
                          AND t.computed_at >= NOW() - INTERVAL '1 hour'
                    ) AS covered_ways
                FROM osm.ways w
                LEFT JOIN osm.mv_sensor_to_way stw ON stw.way_gid = w.gid
                LEFT JOIN gold.traffic_features_live t
                  ON t.channel_id = stw.lyo_channel_id
            )
            SELECT
                CASE WHEN total_ways > 0
                     THEN covered_ways::FLOAT / total_ways::FLOAT
                     ELSE 0.0
                END AS coverage_ratio
            FROM coverage
        """)
        if rows and rows[0].get("coverage_ratio") is not None:
            cov = float(rows[0]["coverage_ratio"])
            value = min(1.0, max(0.5, 0.5 + 0.5 * cov))
            _CONFIDENCE_CACHE[cache_key] = (now, value)
            return value
    except Exception as e:
        logger.warning("Impossible de calculer coverage_ratio (%s) — fallback 0.75", e)
    # Fallback conservateur si DB indispo — ne PAS cacher (sinon on rate le retour DB)
    return 0.75


def compute_itinerary(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    horizon_minutes: int = 0,
    use_cache: bool = True,  # conservé pour rétro-compat — pas utilisé par pgRouting
) -> Itinerary | None:
    """Calcule un itinéraire voiture via pgRouting (réseau routier OSM réel).

    Appelle ``osm.route_car()`` côté PostgreSQL, qui exécute ``pgr_dijkstra``
    sur le graphe routier OSM importé via ``osm2pgrouting``. Chaque arête
    du chemin est retournée avec sa géométrie LineString (polyline OSM).

    Args:
        origin_lon, origin_lat: coords GPS du point de départ.
        destination_lon, destination_lat: coords GPS du point d'arrivée.
        horizon_minutes: 0 = maintenant, sinon utilise la prédiction.
            (Note : pgRouting gère des coûts statiques par arête — l'horizon
            influence le coût via ``osm.refresh_traffic_costs()`` qui tourne
            en DAG toutes les 15 min.)
        use_cache: conservé pour rétro-compat. pgRouting est stateless côté
            Python (le cache SQL est géré par PostgreSQL).

    Returns:
        Itinerary complet avec segments géométrie, ou None si pas de chemin.
    """
    edges = compute_route_pgrouting(
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        dest_lon=destination_lon,
        dest_lat=destination_lat,
    )
    return _build_itinerary_from_edges(edges, horizon_minutes) if edges else None


def _build_itinerary_from_edges(edges: list[dict], horizon_minutes: int) -> Itinerary | None:
    """Construit un Itinerary à partir d'une liste d'arêtes (DRY pour Dijkstra + KSP).

    Helper interne partagé par ``compute_itinerary`` (Dijkstra) et
    ``compute_itinerary_alternatives`` (KSP). Ne lance PAS la query SQL —
    les edges viennent déjà de ``compute_route_pgrouting`` ou
    ``compute_route_pgrouting_ksp``.
    """
    if not edges:
        return None

    segments: list[ItinerarySegment] = []
    total_length = 0.0
    total_duration = 0.0

    for edge in edges:
        coords = edge.get("geom_coordinates") or []
        if coords:
            start_lon, start_lat = float(coords[0][0]), float(coords[0][1])
            end_lon, end_lat = float(coords[-1][0]), float(coords[-1][1])
        else:
            start_lon = start_lat = end_lon = end_lat = 0.0
            logger.warning("Edge %s sans géométrie OSM", edge.get("edge_id"))

        seg = ItinerarySegment(
            channel_id=edge.get("road_name") or "",
            length_m=edge["length_m"],
            speed_kmh=edge["speed_kmh"],
            duration_s=edge["cost_s"],
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=end_lon,
            end_lat=end_lat,
            geometry=coords if coords else None,
        )
        segments.append(seg)
        total_length += edge["length_m"]
        total_duration += edge["cost_s"]

    avg_speed = (total_length / (total_duration / 3600 * 1000)) if total_duration > 0 else 0.0

    return Itinerary(
        origin_node=str(edges[0]["edge_id"]),
        destination_node=str(edges[-1]["edge_id"]),
        horizon_minutes=horizon_minutes,
        segments=segments,
        total_length_m=total_length,
        total_duration_s=total_duration,
        average_speed_kmh=avg_speed,
        confidence=_compute_pgrouting_confidence(),
    )


def compute_itinerary_alternatives(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    k: int = 3,
    horizon_minutes: int = 0,
) -> list[Itinerary] | None:
    """Calcule K itinéraires voiture alternatifs via pgr_ksp (Sprint 22).

    Wrapper sur ``compute_route_pgrouting_ksp()`` côté PostgreSQL.
    Retourne jusqu'à K ``Itinerary`` distincts que l'usager peut comparer.

    Args:
        origin_lon, origin_lat: coords GPS du point de départ.
        destination_lon, destination_lat: coords GPS du point d'arrivée.
        k: nombre d'alternatives (1..5, défaut 3).
        horizon_minutes: focus temporel (ignoré par KSP qui utilise les
            coûts courants de osm.ways, refresh toutes les 15 min par DAG).

    Returns:
        Liste de K ``Itinerary`` distincts (les moins chers en tête),
        ou ``None`` si DB indispo / pas de chemin.
    """
    routes_edges = compute_route_pgrouting_ksp(
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        dest_lon=destination_lon,
        dest_lat=destination_lat,
        k=k,
    )
    if not routes_edges:
        return None

    # Une seule confidence (métrique globale), partagée par tous les itinéraires
    confidence = _compute_pgrouting_confidence()

    itineraries: list[Itinerary] = []
    for route_edges in routes_edges:
        itin = _build_itinerary_from_edges(route_edges, horizon_minutes)
        if itin is not None:
            # Override la confidence (sinon recalcul 3x pour rien)
            itin = Itinerary(
                origin_node=itin.origin_node,
                destination_node=itin.destination_node,
                horizon_minutes=itin.horizon_minutes,
                segments=itin.segments,
                total_length_m=itin.total_length_m,
                total_duration_s=itin.total_duration_s,
                average_speed_kmh=itin.average_speed_kmh,
                confidence=confidence,
            )
            itineraries.append(itin)
    return itineraries if itineraries else None
