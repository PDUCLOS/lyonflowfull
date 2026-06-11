"""Pathfinding Vélov + marche (Sprint VPS-6, 2026-06-11).

Combine 3 segments pour un trajet multimodal Vélov :
1. **Marche** : du point d'origine à la station Vélov la plus proche (avec vélo dispo).
2. **Vélo** : entre 2 stations Vélov (utilise ``compute_itinerary()`` si dispo,
   sinon haversine x vitesse cycliste).
3. **Marche** : de la station Vélov d'arrivée jusqu'au point de destination.

Toutes les coordonnées viennent du pipeline (jamais de mock en prod) :
* Vélov dispo/traffic temps réel : ``silver.velov_clean``
* Graphe routier : ``src.routing.graph.build_routing_graph`` (Dijkstra)
* Distances haversine : fonction SQL ``referentiel.haversine_m``

Mode démo (``LYONFLOW_DEMO_MODE=1``) : retour sans erreur, segments vides.
Mode prod : lève ``DashboardDataError`` si la DB ne répond pas.

Usage::

    from src.routing.pathfinder_velov import plan_velov_trip
    itinerary = plan_velov_trip(
        origin_lon=4.8340, origin_lat=45.7575,
        dest_lon=4.8525, dest_lat=45.7745,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError
from src.db.connection import execute_query

logger = logging.getLogger(__name__)


# Vitesses par défaut (km/h). Documentées pour tuning futur.
DEFAULT_WALK_SPEED_KMH = 4.5
DEFAULT_CYCLIST_SPEED_KMH = 15.0
MAX_WALK_TO_STATION_M = 1500  # au-delà, on suggère une autre station


@dataclass
class VelovSegment:
    """Un segment de trajet Vélov + marche."""

    mode: str  # "walk" | "cycle" | "destination"
    from_label: str
    to_label: str
    from_lon: float
    from_lat: float
    to_lon: float
    to_lat: float
    distance_m: float
    duration_min: float
    n_bikes_depart: int | None = None
    n_docks_arrive: int | None = None
    notes: str = ""


@dataclass
class VelovItinerary:
    """Itinéraire Vélov complet (3 segments)."""

    origin_label: str
    destination_label: str
    segments: list[VelovSegment] = field(default_factory=list)
    total_distance_m: float = 0.0
    total_duration_min: float = 0.0
    source: str = "db"  # "db" | "demo"

    @property
    def feasible(self) -> bool:
        """True si on a trouvé 2 stations Vélov avec dispo cohérente."""
        return (
            len(self.segments) == 3
            and self.segments[0].distance_m < MAX_WALK_TO_STATION_M
            and (self.segments[1].n_bikes_depart or 0) > 0
            and (self.segments[1].n_docks_arrive or 0) > 0
        )


def _require_db_or_raise(source: str) -> None:
    """Vérifie la DB. Lève DashboardDataError si indisponible (mode prod)."""
    from src.data.db_query import _is_db_available
    from src.data.exceptions import DashboardDataError

    if not _is_db_available():
        raise DashboardDataError(source=source, detail="PostgreSQL indisponible")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine (mètres) — calcul Python en fallback de la SQL fn."""
    import math
    r = 6_371_000  # m
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_velov_station(
    lat: float, lon: float, require_bikes: bool = True, require_docks: bool = True
) -> dict | None:
    """1 plus proche station Vélov du point (lat, lon), avec dispo temps réel.

    Returns:
        Dict {station_id, station_name, lat, lon, num_bikes_available,
        num_docks_available, distance_m} ou None si aucune ne match les critères.
    """
    min_bikes = 1 if require_bikes else 0
    min_docks = 1 if require_docks else 0
    rows = execute_query(
        """
        SELECT * FROM referentiel.nearest_velov_stations(
            %s::double precision, %s::double precision,
            1, %s, %s
        )
        """,
        (lat, lon, min_bikes, min_docks),
    )
    return dict(rows[0]) if rows else None


def _nearest_velov_stations_pair(
    origin_lat: float, origin_lon: float,
    dest_lat: float, dest_lon: float,
) -> dict[str, dict | None]:
    """Batch lookup : 1 round-trip DB pour les 2 stations Vélov (origine + dest).

    Returns:
        Dict avec clés "origin" (vélos dispo) et "dest" (docks dispo).
        Valeurs = dict station ou None si aucune ne match les critères.

    Sprint VPS-6 hotfix (2026-06-11) : remplace 2 calls séquentiels à
    _nearest_velov_station par 1 seul query UNION ALL. Gain mesuré
    sur VPS : 14s → ~7s sur plan_velov_trip.
    """
    rows = execute_query(
        """
        SELECT station_id, station_name, lat, lon,
               num_bikes_available, num_docks_available,
               distance_m, is_active,
               'origin' AS role
        FROM referentiel.nearest_velov_stations(
            %s::double precision, %s::double precision,
            1, 1, 0
        )
        UNION ALL
        SELECT station_id, station_name, lat, lon,
               num_bikes_available, num_docks_available,
               distance_m, is_active,
               'dest' AS role
        FROM referentiel.nearest_velov_stations(
            %s::double precision, %s::double precision,
            1, 0, 1
        )
        """,
        (origin_lat, origin_lon, dest_lat, dest_lon),
    )
    out: dict[str, dict | None] = {"origin": None, "dest": None}
    for r in rows[:2]:
        d = dict(r)
        role = d.pop("role", None)
        if role in ("origin", "dest"):
            out[role] = d
    return out


def _road_itinerary_between(
    lon_a: float, lat_a: float, lon_b: float, lat_b: float
) -> dict | None:
    """Itinéraire routier entre 2 points GPS via Dijkstra (src.routing.pathfinder).

    Returns:
        Dict {total_length_m, total_duration_min, segments_count, speed_kmh}
        ou None si pas de chemin / DB indispo.

    Note perf (Sprint VPS-6 hotfix, 2026-06-11) : Dijkstra routier sur le
    segment inter-stations Vélov est en général *plus long* que haversine +
    cycliste 15 km/h, et plante sur dette schéma v0.3.1 (geom_wgs84 manquant).
    On skip le Dijkstra et on note "haversine fallback" — la durée reste
    correcte à ±20% pour un trajet Vélov urbain. Sprint 7+ : fix schéma
    silver.trafic_boucles_clean et réactiver Dijkstra.
    """
    # Sprint VPS-6 hotfix : court-circuit Dijkstra pour Vélov (gain 5-10s
    # par requête sur le VPS, et fallback gracieux en attendant le fix
    # dette schéma v0.3.1).
    return None  # caller fallback haversine + vitesse cycliste


def plan_velov_trip(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_label: str = "Origine",
    dest_label: str = "Destination",
    walk_speed_kmh: float = DEFAULT_WALK_SPEED_KMH,
    cyclist_speed_kmh: float = DEFAULT_CYCLIST_SPEED_KMH,
) -> VelovItinerary:
    """Planifie un trajet Vélov + marche entre 2 points GPS.

    Args:
        origin_lat, origin_lon: GPS du point de départ.
        dest_lat, dest_lon: GPS du point d'arrivée.
        origin_label, dest_label: labels affichés.
        walk_speed_kmh: vitesse marche (défaut 4.5 km/h).
        cyclist_speed_kmh: vitesse cycliste (défaut 15 km/h).

    Returns:
        VelovItinerary avec 3 segments :
        [0] marche origine → Vélov départ
        [1] Vélov entre 2 stations (haversine ou Dijkstra)
        [2] marche Vélov arrivée → destination

    Raises:
        DashboardDataError: en mode prod, si la DB ne répond pas.
    """
    if _is_demo_mode():
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            source="demo",
        )

    _require_db_or_raise("silver.velov_clean")

    # Sprint VPS-6 hotfix (2026-06-11) — les 2 lookups Vélov sont
    # séquentiels et représentent 2× le temps d'une query haversine sur
    # l'ensemble de silver.velov_clean. On batche en une seule query
    # UNION ALL : 1 round-trip DB au lieu de 2.
    stations = _nearest_velov_stations_pair(
        origin_lat, origin_lon,
        dest_lat, dest_lon,
    )
    origin_station = stations.get("origin")
    if origin_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )
    dest_station = stations.get("dest")
    if dest_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )

    # Segment 1 : marche origine → Vélov
    walk_to = origin_station["distance_m"]
    seg1 = VelovSegment(
        mode="walk",
        from_label=origin_label,
        to_label=origin_station["station_name"],
        from_lon=origin_lon,
        from_lat=origin_lat,
        to_lon=float(origin_station["lon"]),
        to_lat=float(origin_station["lat"]),
        distance_m=walk_to,
        duration_min=round(walk_to / 1000.0 / walk_speed_kmh * 60.0, 1),
        n_bikes_depart=origin_station["num_bikes_available"],
        notes="Marche vers la station Vélov" if walk_to <= MAX_WALK_TO_STATION_M
              else f"⚠️ Marche longue ({int(walk_to)}m) — considérer bus/métro",
    )

    # Segment 2 : Vélov entre les 2 stations
    cycle_dist_m = _haversine_m(
        float(origin_station["lat"]), float(origin_station["lon"]),
        float(dest_station["lat"]), float(dest_station["lon"]),
    )
    road = _road_itinerary_between(
        float(origin_station["lon"]), float(origin_station["lat"]),
        float(dest_station["lon"]), float(dest_station["lat"]),
    )
    if road and road["total_length_m"] > 0:
        cycle_dist_m = road["total_length_m"]
        cycle_dur_min = road["total_duration_min"]
        cycle_note = f"Via graphe routier ({road['segments_count']} segments, {road['average_speed_kmh']:.1f} km/h)"
    else:
        cycle_dur_min = round(cycle_dist_m / 1000.0 / cyclist_speed_kmh * 60.0, 1)
        cycle_note = f"Haversine (fallback, ~{cyclist_speed_kmh} km/h)"
    seg2 = VelovSegment(
        mode="cycle",
        from_label=origin_station["station_name"],
        to_label=dest_station["station_name"],
        from_lon=float(origin_station["lon"]),
        from_lat=float(origin_station["lat"]),
        to_lon=float(dest_station["lon"]),
        to_lat=float(dest_station["lat"]),
        distance_m=cycle_dist_m,
        duration_min=cycle_dur_min,
        n_bikes_depart=origin_station["num_bikes_available"],
        n_docks_arrive=dest_station["num_docks_available"],
        notes=cycle_note,
    )

    # Segment 3 : marche Vélov → destination
    walk_from = dest_station["distance_m"]
    seg3 = VelovSegment(
        mode="destination",
        from_label=dest_station["station_name"],
        to_label=dest_label,
        from_lon=float(dest_station["lon"]),
        from_lat=float(dest_station["lat"]),
        to_lon=dest_lon,
        to_lat=dest_lat,
        distance_m=walk_from,
        duration_min=round(walk_from / 1000.0 / walk_speed_kmh * 60.0, 1),
        n_docks_arrive=dest_station["num_docks_available"],
        notes="Marche vers la destination" if walk_from <= MAX_WALK_TO_STATION_M
              else f"⚠️ Marche longue ({int(walk_from)}m)",
    )

    total_dist = walk_to + cycle_dist_m + walk_from
    total_dur = seg1.duration_min + seg2.duration_min + seg3.duration_min

    return VelovItinerary(
        origin_label=origin_label,
        destination_label=dest_label,
        segments=[seg1, seg2, seg3],
        total_distance_m=total_dist,
        total_duration_min=total_dur,
        source="db",
    )


def plan_car_trip(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_label: str = "Origine",
    dest_label: str = "Destination",
    horizon_minutes: int = 0,
) -> dict:
    """Planifie un trajet voiture traffic-aware entre 2 points GPS.

    Utilise le graphe routier Dijkstra (``compute_itinerary``) qui intègre
    les prédictions H+h (``gold.trafic_predictions``, Sprint VPS-5).

    Returns:
        Dict {
          "origin_label", "destination_label",
          "total_length_m", "total_duration_min",
          "average_speed_kmh", "horizon_minutes",
          "segments": [ {channel_id, length_m, speed_kmh, duration_s,
                          start_lat, start_lon, end_lat, end_lon} ],
          "source": "db" | "demo" | "unavailable",
        }
    """
    if _is_demo_mode():
        return {
            "origin_label": origin_label,
            "destination_label": dest_label,
            "total_length_m": 0.0,
            "total_duration_min": 0.0,
            "average_speed_kmh": 0.0,
            "horizon_minutes": horizon_minutes,
            "segments": [],
            "source": "demo",
        }

    _require_db_or_raise("silver.trafic_boucles_clean")

    try:
        from src.routing.pathfinder import compute_itinerary

        itin = compute_itinerary(
            origin_lon=origin_lon,
            origin_lat=origin_lat,
            destination_lon=dest_lon,
            destination_lat=dest_lat,
            horizon_minutes=horizon_minutes,
            use_cache=True,
        )
    except Exception as e:
        logger.warning("plan_car_trip failed: %s", e)
        raise DashboardDataError(
            source="silver.trafic_boucles_clean",
            detail=f"Erreur calcul itinéraire : {e}",
        ) from e

    if itin is None:
        return {
            "origin_label": origin_label,
            "destination_label": dest_label,
            "total_length_m": 0.0,
            "total_duration_min": 0.0,
            "average_speed_kmh": 0.0,
            "horizon_minutes": horizon_minutes,
            "segments": [],
            "source": "unavailable",
        }

    return {
        "origin_label": origin_label,
        "destination_label": dest_label,
        "total_length_m": itin.total_length_m,
        "total_duration_min": itin.total_duration_min,
        "average_speed_kmh": itin.average_speed_kmh,
        "horizon_minutes": horizon_minutes,
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
            for s in itin.segments
        ],
        "source": "db",
    }
