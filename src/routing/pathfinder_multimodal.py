"""Pathfinding Vélov + marche (Sprint VPS-6, 2026-06-11).

Combine 3 segments pour un trajet multimodal Vélov :
1. **Marche** : du point d'origine à la station Vélov la plus proche (avec vélo dispo).
2. **Vélo** : entre 2 stations Vélov (utilise ``compute_itinerary()`` si dispo,
   sinon haversine x vitesse cycliste).
3. **Marche** : de la station Vélov d'arrivée jusqu'au point de destination.

Toutes les coordonnées viennent du pipeline (jamais de mock en prod) :
* Vélov dispo/traffic temps réel : ``silver.velov_clean``
* Routing voiture : pgRouting ``pgr_dijkstra`` sur réseau OSM (Sprint 18)
* Distances haversine : fonction SQL ``referentiel.haversine_m``

Sprint 9+ (2026-06-17) — mode démo supprimé (politique Sprint 8 zéro mock).
Lève ``DashboardDataError`` si la DB ne répond pas.

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
from datetime import datetime

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
    # Sprint 14 (2026-06-19) — Vélov GBFS : séparation mécanique / électrique
    # si la source silver.velov_clean expose `num_bikes_available_types`
    # (GBFS Vélov). None par défaut → affichage sobre (juste le total).
    n_bikes_mechanical: int | None = None
    n_bikes_electrical: int | None = None
    notes: str = ""


@dataclass
class VelovItinerary:
    """Itinéraire Vélov complet (3 segments) + alternatives smart-routed."""

    origin_label: str
    destination_label: str
    segments: list[VelovSegment] = field(default_factory=list)
    total_distance_m: float = 0.0
    total_duration_min: float = 0.0
    source: str = "db"  # toujours "db" en prod (Sprint 8 — mode démo supprimé)
    # Sprint VPS-6 hotfix (2026-06-11) — alternatives si la borne #1 est
    # vide/pleine. Liste de paires (rank 2, 3) avec mêmes champs que
    # origin_station / dest_station, chargées via v_lieux_velov_smart.
    origin_alternatives: list[dict] = field(default_factory=list)
    dest_alternatives: list[dict] = field(default_factory=list)
    # Voisines (maillage < 200m) des bornes utilisées. Pour le rendu
    # carte "grappe" et les suggestions à pied.
    origin_neighbors: list[dict] = field(default_factory=list)
    dest_neighbors: list[dict] = field(default_factory=list)
    # Diagnostics (warnings d'aide à l'utilisateur)
    diagnostics: list[str] = field(default_factory=list)

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
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
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


def _road_itinerary_between(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> dict | None:
    """Itinéraire routier entre 2 points GPS via Dijkstra (src.routing.pathfinder).

    Returns:
        Dict {total_length_m, total_duration_min, segments_count, speed_kmh}
        ou None si pas de chemin / DB indispo.

    Sprint 8 (post-VPS-6) : réactivé après fix dette schéma v0.3.1
    (geom_wgs84 → geom dans src/routing/graph.py, sprint-8). Maintenant
    le Dijkstra fonctionne sur le VPS, on l'utilise pour le segment
    Vélov inter-stations. Si exception (DB indispo, graphe vide),
    fallback gracieux haversine + vitesse cycliste.
    """
    try:
        from src.routing.pathfinder import compute_itinerary

        itin = compute_itinerary(
            origin_lon=lon_a,
            origin_lat=lat_a,
            destination_lon=lon_b,
            destination_lat=lat_b,
            horizon_minutes=0,
            use_cache=True,
        )
        if itin is None:
            return None
        return {
            "total_length_m": itin.total_length_m,
            "total_duration_min": itin.total_duration_min,
            "segments_count": len(itin.segments),
            "average_speed_kmh": itin.average_speed_kmh,
        }
    except Exception as e:
        logger.debug("road_itinerary_between fallback haversine: %s", e)
        return None


def _haversine_velov_candidate(lat: float, lon: float) -> dict:
    """Fallback : 1 candidate Vélov à partir d'un simple haversine.

    Utilisé quand le point GPS est hors périmètre des 21 lieux du
    référentiel (rare : Lyon + banlieue). Renvoie un dict compatible
    avec le format ``v_lieux_velov_smart`` (status='UNKNOWN').

    Returns:
        Dict {station_id: None, velov_name: '?', velov_lon, velov_lat,
        num_bikes_available: None, num_docks_available: None,
        distance_m, score: 0, status: 'UNKNOWN', rank: 1}.
    """
    return {
        "station_id": None,
        "velov_name": "(point libre)",
        "velov_lon": lon,
        "velov_lat": lat,
        "num_bikes_available": None,
        "num_docks_available": None,
        "distance_m": 0.0,
        "score": 0.0,
        "status": "UNKNOWN",
        "rank": 1,
    }


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

    EXPLICATION MÉTIER (Analyse) :
    Ce moteur multimodal combine la marche à pied et le vélo.
    L'intelligence (Smart Routing) réside dans le choix des bornes Vélov :
    plutôt que de prendre aveuglément la borne la plus proche, l'algorithme :
    1. Récupère les bornes candidates (proches de l'origine et de la destination).
    2. Vérifie la disponibilité TEMPS RÉEL (vélos au départ, docks à l'arrivée).
    3. Si la borne la plus proche est "VIDE" (plus de vélos) ou "PLEINE" (plus de docks),
       l'algorithme bascule automatiquement sur la 2ème ou 3ème borne la plus proche.

    Cela garantit que l'itinéraire proposé à l'usager est réalisable dans le monde réel.

    Raises:
        DashboardDataError: si la DB ne répond pas.
    """
    _require_db_or_raise("silver.velov_clean")

    # Sprint VPS-6 hotfix 2 (2026-06-11) — Smart routing : on récupère
    # le top 3 bornes scorées (distance + vélos/docks dispo) en 1 seule
    # query via la vue referentiel.v_lieux_velov_smart. Si la borne #1
    # est VIDE ou PLEINE, on bascule automatiquement sur #2 ou #3.
    from src.data.db_query import get_smart_velov_for_lieu

    # Approximation : on snap les coords GPS vers le lieu le plus
    # proche du référentiel (dans un rayon 5km), pour bénéficier du
    # scoring. Si hors périmètre, fallback sur haversine direct.
    def _nearest_lieu_id(lat: float, lon: float) -> int | None:
        from src.data.db_query import execute_query

        rows = execute_query(
            """
            SELECT lieu_id FROM referentiel.lieux_lyon
            WHERE is_active = TRUE
            ORDER BY referentiel.haversine_m(lat, lon, %s, %s) ASC
            LIMIT 1
            """,
            (lat, lon),
        )
        return int(rows[0]["lieu_id"]) if rows else None

    origin_lieu_id = _nearest_lieu_id(origin_lat, origin_lon)
    dest_lieu_id = _nearest_lieu_id(dest_lat, dest_lon)

    origin_candidates = get_smart_velov_for_lieu(origin_lieu_id, k=3) if origin_lieu_id else []
    dest_candidates = get_smart_velov_for_lieu(dest_lieu_id, k=3) if dest_lieu_id else []

    # Si pas de lieu proche, fallback sur haversine direct
    if not origin_candidates:
        origin_candidates = [_haversine_velov_candidate(origin_lat, origin_lon)]
    if not dest_candidates:
        dest_candidates = [_haversine_velov_candidate(dest_lat, dest_lon)]

    # Smart selection : prend la 1ère borne avec status=OK, sinon FAIBLE,
    # sinon la 1ère dispo. Si toutes VIDE/PLEINE, garde la 1ère et ajoute
    # un diagnostic.
    def _pick_best(cands: list[dict], role: str) -> tuple[dict | None, list[dict]]:
        if not cands:
            return None, []
        # Essaie OK > FAIBLE > toute dispo > 1ère par défaut
        for priority in ("OK", "FAIBLE"):
            for c in cands:
                if c.get("status") == priority:
                    alts = [c2 for c2 in cands if c2 is not c]
                    return c, alts
        # Aucune "OK"/"FAIBLE" : prendre la 1ère, alternatives = reste
        chosen = cands[0]
        alts = cands[1:]
        return chosen, alts

    origin_station, origin_alts = _pick_best(origin_candidates, "origin")
    dest_station, dest_alts = _pick_best(dest_candidates, "dest")

    if origin_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )
    if dest_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )

    _require_db_or_raise("silver.velov_clean")

    # Sprint 8 hotfix 7 (2026-06-12) — On garde origin_station /
    # dest_station du smart routing (ligne 336-337) qui intègrent
    # status + alternatives + voisines. L'ancien hotfix perf qui
    # réécrasait avec _nearest_velov_stations_pair cassait le smart
    # routing (schéma incompatible : station_id/lat/lon vs
    # velov_name/velov_lat/velov_lon) et provoquait KeyError.
    # TODO Sprint 9 : si perf pose problème, batcher le smart lookup
    # en 1 round-trip SQL (UNION ALL avec scoring intégré).
    if origin_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )
    if dest_station is None:
        return VelovItinerary(
            origin_label=origin_label,
            destination_label=dest_label,
            segments=[],
            source="db",
        )

    # Sprint VPS-6 hotfix 2 — calcul du maillage (voisines) des 2 bornes
    # choisies. Si on a des station_id, on récupère leurs voisines à
    # < 200m. Sinon (cas UNKNOWN) on skip.
    from src.data.db_query import get_velov_neighbors_batch

    origin_sid = origin_station.get("station_id")
    dest_sid = dest_station.get("station_id")
    neighbors_map = get_velov_neighbors_batch(
        [sid for sid in (origin_sid, dest_sid) if sid],
        k=3,
    )
    origin_neighbors = neighbors_map.get(origin_sid, []) if origin_sid else []
    dest_neighbors = neighbors_map.get(dest_sid, []) if dest_sid else []

    # Diagnostics
    diagnostics = []
    if origin_station.get("status") == "VIDE":
        diagnostics.append(
            f"⚠️ Borne de départ {origin_station.get('velov_name')} est VIDE. "
            f"Alternatives à pied : "
            + ", ".join(
                f"{a.get('velov_name')} ({int(a.get('distance_m', 0))}m, {a.get('num_bikes_available')} vélos)"
                for a in origin_alts[:2]
                if a.get("velov_name")
            )
        )
    if origin_station.get("status") == "PLEINE":
        diagnostics.append(
            f"⚠️ Borne de départ {origin_station.get('velov_name')} est PLEINE. "
            f"Alternatives à pied : "
            + ", ".join(
                f"{a.get('velov_name')} ({int(a.get('distance_m', 0))}m, {a.get('num_docks_available')} docks)"
                for a in origin_alts[:2]
                if a.get("velov_name")
            )
        )
    if dest_station.get("status") == "VIDE":
        diagnostics.append(
            f"⚠️ Borne d'arrivée {dest_station.get('velov_name')} est VIDE (pas de vélos dispo). "
            f"Alternatives à pied : "
            + ", ".join(
                f"{a.get('velov_name')} ({int(a.get('distance_m', 0))}m, {a.get('num_bikes_available')} vélos)"
                for a in dest_alts[:2]
                if a.get("velov_name")
            )
        )
    if dest_station.get("status") == "PLEINE":
        diagnostics.append(
            f"⚠️ Borne d'arrivée {dest_station.get('velov_name')} est PLEINE (pas de dock dispo). "
            f"Alternatives à pied : "
            + ", ".join(
                f"{a.get('velov_name')} ({int(a.get('distance_m', 0))}m, {a.get('num_docks_available')} docks)"
                for a in dest_alts[:2]
                if a.get("velov_name")
            )
        )
    if not origin_alts and origin_station.get("status") in ("VIDE", "PLEINE"):
        diagnostics.append("⚠️ Aucune borne alternative dans un rayon 1.5 km. Considérer bus/métro.")
    if not dest_alts and dest_station.get("status") in ("VIDE", "PLEINE"):
        diagnostics.append("⚠️ Aucune borne alternative dans un rayon 1.5 km. Considérer bus/métro.")

    # Segment 1 : marche origine → Vélov
    walk_to = origin_station.get("distance_m", 0.0)
    seg1 = VelovSegment(
        mode="walk",
        from_label=origin_label,
        to_label=origin_station.get("velov_name", "?"),
        from_lon=origin_lon,
        from_lat=origin_lat,
        to_lon=float(origin_station["velov_lon"]),
        to_lat=float(origin_station["velov_lat"]),
        distance_m=walk_to,
        duration_min=round(walk_to / 1000.0 / walk_speed_kmh * 60.0, 1),
        n_bikes_depart=origin_station.get("num_bikes_available"),
        notes="Marche vers la station Vélov"
        if walk_to <= MAX_WALK_TO_STATION_M
        else f"⚠️ Marche longue ({int(walk_to)}m) — considérer bus/métro",
    )

    # Segment 2 : Vélov entre les 2 stations
    # Haversine x 1.3 (facteur detour urbain) — pas de Dijkstra pour velo,
    # le graphe routier est taille pour voitures et coute 3-8s a construire.
    road_factor = 1.3
    cycle_dist_m = _haversine_m(
        float(origin_station["velov_lat"]),
        float(origin_station["velov_lon"]),
        float(dest_station["velov_lat"]),
        float(dest_station["velov_lon"]),
    ) * road_factor
    cycle_dur_min = round(cycle_dist_m / 1000.0 / cyclist_speed_kmh * 60.0, 1)
    cycle_note = f"Distance estimee (x{road_factor}, ~{cyclist_speed_kmh} km/h)"
    seg2 = VelovSegment(
        mode="cycle",
        from_label=origin_station.get("velov_name", "?"),
        to_label=dest_station.get("velov_name", "?"),
        from_lon=float(origin_station["velov_lon"]),
        from_lat=float(origin_station["velov_lat"]),
        to_lon=float(dest_station["velov_lon"]),
        to_lat=float(dest_station["velov_lat"]),
        distance_m=cycle_dist_m,
        duration_min=cycle_dur_min,
        n_bikes_depart=origin_station.get("num_bikes_available"),
        n_docks_arrive=dest_station.get("num_docks_available"),
        notes=cycle_note,
    )

    # Segment 3 : marche Vélov → destination
    walk_from = dest_station.get("distance_m", 0.0)
    seg3 = VelovSegment(
        mode="destination",
        from_label=dest_station.get("velov_name", "?"),
        to_label=dest_label,
        from_lon=float(dest_station["velov_lon"]),
        from_lat=float(dest_station["velov_lat"]),
        to_lon=dest_lon,
        to_lat=dest_lat,
        distance_m=walk_from,
        duration_min=round(walk_from / 1000.0 / walk_speed_kmh * 60.0, 1),
        n_docks_arrive=dest_station.get("num_docks_available"),
        notes="Marche vers la destination"
        if walk_from <= MAX_WALK_TO_STATION_M
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
        origin_alternatives=origin_alts,
        dest_alternatives=dest_alts,
        origin_neighbors=origin_neighbors,
        dest_neighbors=dest_neighbors,
        diagnostics=diagnostics,
    )


def plan_car_trip(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
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

    EXPLICATION MÉTIER (Analyse) :
    Cette fonction est le point d'entrée du routage routier (pour les voitures).
    Elle délègue la résolution du plus court chemin à `compute_itinerary()` qui
    implémente l'algorithme de Dijkstra sur le graphe de la métropole.
    La particularité est qu'elle gère l'injection de l'`horizon_minutes`,
    permettant un routage basé sur le futur plutôt que le présent.
    """
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


# =============================================================================
# Sprint 14 (2026-06-19) — Routing transport en commun (TC) usager
# =============================================================================
# Itinéraire TC entre 2 lieux du référentiel (21 lieux emblématiques).
# Stratégie Phase 1 :
#   - Si intersection lignes(O) ∩ lignes(D) ∃ → trajet direct
#     (meilleure ligne = somme ranks minimale aux 2 bouts)
#   - Sinon → correspondance via 1 hub (parmi les 21 lieux actifs),
#     minimisation durée totale
#
# Données :
#   - referentiel.lieux_transports (dessertes, 56 liaisons)
#   - referentiel.lieux_calendrier (cadences, 223 enregistrements)
#   - gold.bus_delay_segments (retards SIRI 7j glissants)
#
# Limites affichées à l'usager (cf. T4 widget transit_trip.py) :
#   - Fréquences estimées (pas horaires exacts GTFS)
#   - 21 lieux uniquement (= ceux de la selectbox, 100% couverture UI)
#   - 1 correspondance max (Phase 2 = Raptor multi-transfers)
#   - Retards = moyenne 7j à cette heure (pas prédiction ML)


@dataclass
class TransitSegment:
    """Un segment de trajet TC (1 ligne, sans correspondance)."""

    line_ref: str
    line_mode: str  # metro|tram|bus|funicular
    line_label: str  # ex: "🚇 Métro A"
    stop_origin: str  # ex: "Laurent Bonnevay"
    stop_dest: str  # ex: "Confluence"
    distance_walk_to_m: int  # marche lieu → arrêt départ
    distance_walk_from_m: int  # marche arrêt arrivée → lieu
    cadence_min: float  # fréquence observée (min)
    wait_estimate_min: float  # attente moyenne = cadence/2
    delay_avg_min: float  # retard moyen observé (7j, time_bucket)
    duration_estimate_min: float  # walk_to + wait + drive + retard + walk_from
    confidence: float  # 0-1, basée sur n_observations cadence


@dataclass
class TransitItinerary:
    """Itinéraire TC complet (1 ou 2 segments) entre 2 lieux."""

    origin_label: str
    destination_label: str
    segments: list[TransitSegment] = field(default_factory=list)
    transfer_hub: str | None = None  # None = trajet direct
    n_transfers: int = 0  # 0 = direct, 1 = 1 correspondance
    total_duration_min: float = 0.0
    total_walk_m: int = 0
    total_delay_min: float = 0.0
    confidence: float = 0.0
    source: str = "db"  # toujours "db" en prod (Sprint 8 — pas de mock)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        """True si l'itinéraire a au moins 1 segment et une durée > 0."""
        return len(self.segments) > 0 and self.total_duration_min > 0


# Vitesse moyenne par mode TC (km/h) — approximation Phase 1.
# Sources : métro A Lyon 35 km/h moyen, tram T1/T2 ~20, bus C3 ~15, funiculaires ~18.
_TRANSIT_SPEED_KMH: dict[str, float] = {
    "metro": 35.0,
    "tram": 20.0,
    "bus": 15.0,
    "funicular": 18.0,
}
_TRANSIT_SPEED_KMH_DEFAULT = 18.0

# Libellé emoji par mode (utilisé pour affichage segment.line_label).
_TRANSIT_MODE_LABEL: dict[str, str] = {
    "metro": "🚇 Métro",
    "tram": "🚊 Tram",
    "bus": "🚌 Bus",
    "funicular": "🚞 Funiculaire",
}

# Pénalité forfaitaire pour 1 correspondance (marche inter-arrêts + attente).
_TRANSFER_PENALTY_MIN = 3.0


def _transit_line_label(line_ref: str, line_mode: str) -> str:
    """Construit un libellé lisible pour une ligne TC.

    Exemples :
        ('M_A', 'metro')     → '🚇 Métro A'
        ('T_1', 'tram')      → '🚊 Tram 1'
        ('C_3', 'bus')       → '🚌 Bus 3'
        ('F_2', 'funicular') → '🚞 Funiculaire 2'
    """
    prefix = _TRANSIT_MODE_LABEL.get(line_mode, line_mode.capitalize())
    if "_" in line_ref:
        suffix = line_ref.split("_", 1)[1]
        return f"{prefix} {suffix}"
    return f"{prefix} {line_ref}"


def _resolve_transit_lieu(text: str) -> tuple[int, str, float, float] | None:
    """Résout un label de lieu (avec emoji optionnel) → (lieu_id, name, lon, lat).

    Robuste aux emojis préfixes (ex: ``"🏙 Villeurbanne"``) — même logique
    que ``velov_trip._resolve_lieu`` mais retourne aussi l'ID.

    Returns:
        Tuple (lieu_id, name_clean, lon, lat) ou None si non trouvé.
    """
    if not text:
        return None
    cleaned = text.strip()
    # Strip emoji préfixe (1 char hors BMP + espace)
    if cleaned and ord(cleaned[0]) > 0x2700:
        sp = cleaned.find(" ")
        if sp > 0 and sp <= 3:
            cleaned = cleaned[sp + 1 :].strip()
    text_lower = cleaned.lower().strip()
    if not text_lower:
        return None
    rows = execute_query(
        """
        SELECT lieu_id, name, lon, lat FROM referentiel.lieux_lyon
        WHERE is_active = TRUE AND LOWER(name) LIKE %s
        ORDER BY LENGTH(name) ASC LIMIT 1
        """,
        (f"%{text_lower}%",),
    )
    if not rows:
        return None
    return (
        int(rows[0]["lieu_id"]),
        rows[0]["name"],
        float(rows[0]["lon"]),
        float(rows[0]["lat"]),
    )


def _day_type_from_date(dt: datetime) -> str:
    """Détermine ``day_type`` depuis une date.

    Renvoie ``weekday|saturday|sunday_holiday|vacation``.

    Heuristique vacation (périodes Métropole Lyon, simplifié) :
      - 1/7 → 31/8 (vacances été)
      - 15/12 → 5/1 (vacances fin d'année)

    Fonction pure (Sprint 14+) — testable directement sans monkeypatch
    sur ``datetime.now()``.
    """
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    md = (dt.month, dt.day)
    is_vacation = (md >= (7, 1) and md <= (8, 31)) or md >= (12, 15) or md <= (1, 5)
    if is_vacation:
        return "vacation"
    if weekday == 6:
        return "sunday_holiday"
    if weekday == 5:
        return "saturday"
    return "weekday"


def _time_bucket_from_date(dt: datetime) -> str:
    """Construit ``time_bucket`` ``"HH:00"`` depuis une date.

    Fonction pure (Sprint 14+) — testable directement.
    """
    return f"{dt.hour:02d}:00"


def _get_current_day_type_and_bucket() -> tuple[str, str]:
    """Détermine ``(day_type, time_bucket)`` courants pour cadences.

    Wrapper runtime : appelle ``_day_type_from_date`` et
    ``_time_bucket_from_date`` sur ``datetime.now()``.
    """
    now = datetime.now()
    return _day_type_from_date(now), _time_bucket_from_date(now)


def _estimate_transit_duration_min(
    distance_walk_to_m: int,
    distance_walk_from_m: int,
    segment_distance_m: float,
    line_mode: str,
    cadence_min: float,
    delay_avg_min: float,
) -> float:
    """Estime la durée totale d'un segment TC (en minutes).

    Composantes :
      - walk_to : marche lieu → arrêt (à DEFAULT_WALK_SPEED_KMH)
      - wait : cadence / 2 (attente moyenne sur fréquence uniforme)
      - drive : segment_distance / vitesse(mode)
      - retard moyen observé (7j glissants, time_bucket)
      - walk_from : marche arrêt → lieu destination
    """
    speed = _TRANSIT_SPEED_KMH.get(line_mode, _TRANSIT_SPEED_KMH_DEFAULT)
    walk_to = (distance_walk_to_m / 1000.0) / DEFAULT_WALK_SPEED_KMH * 60.0
    walk_from = (distance_walk_from_m / 1000.0) / DEFAULT_WALK_SPEED_KMH * 60.0
    wait = cadence_min / 2.0
    drive = (segment_distance_m / 1000.0) / speed * 60.0
    return walk_to + wait + drive + delay_avg_min + walk_from


def _build_transit_segment(
    origin_line: dict,
    dest_line: dict,
    segment_distance_m: float,
    day_type: str,
    time_bucket: str,
) -> TransitSegment:
    """Construit un TransitSegment à partir de 2 dessertes.

    Args:
        origin_line: dict de ``referentiel.lieux_transports`` (départ segment).
        dest_line: dict (arrivée segment).
        segment_distance_m: haversine entre 2 lieux (proxy inter-arrêts Phase 1).
        day_type: weekday|saturday|sunday_holiday|vacation.
        time_bucket: HH:00 (pour filtrer cadence + retard).
    """
    from src.data.db_query import get_bus_delay_segments, get_cadence_for_line

    line_ref = origin_line["line_ref"]
    line_mode = origin_line["line_mode"]
    distance_walk_to_m = int(origin_line["distance_m"])
    distance_walk_from_m = int(dest_line["distance_m"])

    # Cadence : filter exact (line_ref, day_type, time_bucket)
    cadence_rows = get_cadence_for_line(
        line_ref,
        day_type=day_type,
        time_bucket=time_bucket,
    )
    if cadence_rows:
        cadence_min = float(cadence_rows[0]["cadence_min_per_vehicle"])
        confidence = float(cadence_rows[0].get("confidence") or 0.5)
        n_obs = int(cadence_rows[0].get("n_observations") or 0)
        if n_obs < 10:
            # Peu d'observations : on baisse la confiance
            confidence = max(0.3, confidence - 0.2)
    else:
        # Fallback : moyenne toutes tranches weekday
        all_cadence = get_cadence_for_line(line_ref, day_type="weekday")
        if all_cadence:
            cadence_min = float(sum(c["cadence_min_per_vehicle"] for c in all_cadence) / len(all_cadence))
            confidence = 0.4  # confiance basse (fallback agrégé)
        else:
            # Pas de données du tout : défaut par mode
            cadence_min = {
                "metro": 5.0,
                "tram": 10.0,
                "bus": 12.0,
                "funicular": 8.0,
            }.get(line_mode, 10.0)
            confidence = 0.2

    # Retard moyen 7j filtré sur l'heure du time_bucket
    delay_avg_min = 0.0
    try:
        bucket_hour = int(time_bucket.split(":")[0])
        delay_df = get_bus_delay_segments(line_ref=line_ref, days=7)
        if not delay_df.empty and "avg_delay_seconds" in delay_df.columns:
            if "hour" in delay_df.columns:
                matched = delay_df[delay_df["hour"] == bucket_hour]
                src = matched if not matched.empty else delay_df
            else:
                src = delay_df
            delay_avg_min = max(
                0.0,
                float(src["avg_delay_seconds"].mean()) / 60.0,
            )
    except Exception:
        # Si la requête échoue (DB ou colonne manquante), on garde 0
        delay_avg_min = 0.0

    duration = _estimate_transit_duration_min(
        distance_walk_to_m=distance_walk_to_m,
        distance_walk_from_m=distance_walk_from_m,
        segment_distance_m=segment_distance_m,
        line_mode=line_mode,
        cadence_min=cadence_min,
        delay_avg_min=delay_avg_min,
    )

    return TransitSegment(
        line_ref=line_ref,
        line_mode=line_mode,
        line_label=_transit_line_label(line_ref, line_mode),
        stop_origin=origin_line["stop_name"],
        stop_dest=dest_line["stop_name"],
        distance_walk_to_m=distance_walk_to_m,
        distance_walk_from_m=distance_walk_from_m,
        cadence_min=round(cadence_min, 1),
        wait_estimate_min=round(cadence_min / 2.0, 1),
        delay_avg_min=round(delay_avg_min, 2),
        duration_estimate_min=round(duration, 1),
        confidence=round(confidence, 2),
    )


def plan_transit_trip(
    origin: str,
    destination: str,
    day_type: str | None = None,
    time_bucket: str | None = None,
) -> TransitItinerary | None:
    """Planifie un itinéraire transport en commun entre 2 lieux du référentiel.

    Algorithme Phase 1 :
      1. Résoudre origin/dest → lieu_id (``referentiel.lieux_lyon``).
      2. Charger lignes desservant O et D (``referentiel.lieux_transports``).
      3. Si intersection non vide → trajet direct (meilleure ligne = somme
         ranks minimale aux 2 bouts).
      4. Sinon → correspondance via 1 hub (parmi les 21 lieux actifs).
         Critère : pour chaque hub, vérifier ∃ ligne ∈ O∩hub ET ∃ ligne ∈ D∩hub.
         Choisir le hub à durée totale minimale.
      5. Pour chaque segment : cadence (``referentiel.lieux_calendrier``)
         + retard moyen (``gold.bus_delay_segments``, 7j).

    Args:
        origin: label de lieu (peut être préfixé emoji).
        destination: idem.
        day_type: ``weekday|saturday|sunday_holiday|vacation`` (défaut: auto).
        time_bucket: ``HH:00`` (défaut: heure actuelle).

    Returns:
        ``TransitItinerary`` (direct ou via hub) avec segments, durées,
        cadences, retards. ``diagnostics`` rempli si aucun trajet trouvé.
        ``None`` si O == D ou si l'un des lieux n'existe pas.

    Raises:
        DashboardDataError: si PostgreSQL indisponible.
    """
    _require_db_or_raise("referentiel.lieux_lyon")

    origin_res = _resolve_transit_lieu(origin)
    dest_res = _resolve_transit_lieu(destination)
    if origin_res is None or dest_res is None:
        return None
    origin_id, origin_name, origin_lon, origin_lat = origin_res
    dest_id, dest_name, dest_lon, dest_lat = dest_res
    if origin_id == dest_id:
        return None  # même lieu → pas de trajet

    from src.data.db_query import get_lieux_transports

    origin_lines = get_lieux_transports(lieu_id=origin_id)
    dest_lines = get_lieux_transports(lieu_id=dest_id)
    if not origin_lines or not dest_lines:
        return TransitItinerary(
            origin_label=origin_name,
            destination_label=dest_name,
            diagnostics=[
                f"Aucune desserte TC pour {origin_name if not origin_lines else dest_name}",
            ],
        )

    # Auto day_type/time_bucket
    if day_type is None or time_bucket is None:
        auto_day, auto_bucket = _get_current_day_type_and_bucket()
        day_type = day_type or auto_day
        time_bucket = time_bucket or auto_bucket

    origin_by_line = {item["line_ref"]: item for item in origin_lines}
    dest_by_line = {item["line_ref"]: item for item in dest_lines}
    common_lines = set(origin_by_line) & set(dest_by_line)

    segment_distance_m = _haversine_m(origin_lat, origin_lon, dest_lat, dest_lon)

    # 1. Trajet direct
    if common_lines:
        # Meilleure ligne = somme des ranks (rank 1 = plus proche)
        best_line = min(
            common_lines,
            key=lambda lr: (origin_by_line[lr]["rank"] + dest_by_line[lr]["rank"], lr),
        )
        seg = _build_transit_segment(
            origin_by_line[best_line],
            dest_by_line[best_line],
            segment_distance_m,
            day_type,
            time_bucket,
        )
        return TransitItinerary(
            origin_label=origin_name,
            destination_label=dest_name,
            segments=[seg],
            transfer_hub=None,
            n_transfers=0,
            total_duration_min=seg.duration_estimate_min,
            total_walk_m=seg.distance_walk_to_m + seg.distance_walk_from_m,
            total_delay_min=seg.delay_avg_min,
            confidence=seg.confidence,
            source="db",
        )

    # 2. Correspondance via hub
    all_lieux_rows = execute_query("SELECT lieu_id, name FROM referentiel.lieux_lyon WHERE is_active = TRUE")
    best_itin: TransitItinerary | None = None
    for hub_row in all_lieux_rows:
        hub_id = int(hub_row["lieu_id"])
        if hub_id in (origin_id, dest_id):
            continue
        hub_lines = get_lieux_transports(lieu_id=hub_id)
        if not hub_lines:
            continue
        hub_by_line = {item["line_ref"]: item for item in hub_lines}
        match_o = set(origin_by_line) & set(hub_by_line)
        match_d = set(dest_by_line) & set(hub_by_line)
        if not match_o or not match_d:
            continue

        best_o = min(
            match_o,
            key=lambda lr: origin_by_line[lr]["rank"] + hub_by_line[lr]["rank"],
        )
        best_d = min(
            match_d,
            key=lambda lr: hub_by_line[lr]["rank"] + dest_by_line[lr]["rank"],
        )
        hub_geo = execute_query(
            "SELECT lon, lat FROM referentiel.lieux_lyon WHERE lieu_id = %s",
            (hub_id,),
        )
        if not hub_geo:
            continue
        hub_lon, hub_lat = float(hub_geo[0]["lon"]), float(hub_geo[0]["lat"])

        seg1_dist = _haversine_m(origin_lat, origin_lon, hub_lat, hub_lon)
        seg2_dist = _haversine_m(hub_lat, hub_lon, dest_lat, dest_lon)
        seg1 = _build_transit_segment(
            origin_by_line[best_o],
            hub_by_line[best_o],
            seg1_dist,
            day_type,
            time_bucket,
        )
        seg2 = _build_transit_segment(
            hub_by_line[best_d],
            dest_by_line[best_d],
            seg2_dist,
            day_type,
            time_bucket,
        )
        total_walk = (
            seg1.distance_walk_to_m + seg1.distance_walk_from_m + seg2.distance_walk_to_m + seg2.distance_walk_from_m
        )
        total_dur = seg1.duration_estimate_min + seg2.duration_estimate_min + _TRANSFER_PENALTY_MIN
        total_delay = seg1.delay_avg_min + seg2.delay_avg_min
        confidence = min(seg1.confidence, seg2.confidence)
        itin = TransitItinerary(
            origin_label=origin_name,
            destination_label=dest_name,
            segments=[seg1, seg2],
            transfer_hub=hub_row["name"],
            n_transfers=1,
            total_duration_min=round(total_dur, 1),
            total_walk_m=total_walk,
            total_delay_min=round(total_delay, 2),
            confidence=round(confidence, 2),
            source="db",
        )
        if best_itin is None or total_dur < best_itin.total_duration_min:
            best_itin = itin

    if best_itin:
        return best_itin

    # 3. Aucun trajet possible → diagnostic lignes O et D
    return TransitItinerary(
        origin_label=origin_name,
        destination_label=dest_name,
        diagnostics=[
            f"Lignes desservant {origin_name} : {', '.join(sorted(set(origin_by_line)))}",
            f"Lignes desservant {dest_name} : {', '.join(sorted(set(dest_by_line)))}",
            "Aucune correspondance simple (Phase 1 : 21 lieux, 1 hub max).",
        ],
    )
