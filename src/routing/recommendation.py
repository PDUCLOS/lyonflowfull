"""Recommandation multimodale basée sur les trajets favoris (Sprint 10).

Quand un utilisateur consulte un favori (ex: "Maison → Boulot en Métro A"),
propose des alternatives multimodales intelligentes en s'appuyant sur :
- silver.velov_clean        → stations Vélov proches, dispo temps réel
- silver.trafic_boucles_clean → temps de trajet réels estimés
- referentiel.lieux_lyon    → snap GPS → lieu référentiel
- referentiel.lieux_transports → lignes TCL dispo par lieu

Règles métier (pas de ML complexe) :
- Si favori = métro → proposer bus + Vélov + VTC avec estimation temps
- Si favori = bus   → proposer métro + Vélov + marche
- Score confiance basé sur : dispo Vélov, trafic prévu, cadence TCL
- Raison contextualisée (chantier, heure de pointe, météo, dispo)

Usage::

    from src.routing.recommendation import get_alternatives

    alternatives = get_alternatives(favorite_dict)
    # → [{mode, temps, score_confiance, raison}, ...]
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

from src.data.data_loader import _is_demo_mode
from src.data.db_query import (
    _is_db_available,
    execute_query,
    get_lieux_transports,
    get_smart_velov_for_lieu,
)
from src.data.exceptions import DashboardDataError

logger = logging.getLogger(__name__)


# =============================================================================
# Types
# =============================================================================
Mode = Literal["metro", "bus", "velov", "walk", "car", "vtc"]

# Correspondance mode usager → mode transport normalisé
MODE_LABEL: dict[str, str] = {
    "M A": "metro",
    "M B": "metro",
    "M C": "metro",
    "M D": "metro",
    "T1": "tram",
    "T2": "tram",
    "T3": "tram",
    "T6": "tram",
    "C3": "bus",
    "C13": "bus",
    "C14": "bus",
    "C17": "bus",
}


@dataclass
class Alternative:
    """Une alternative multimodale à un trajet favori."""

    mode: Mode
    mode_label: str
    mode_icon: str
    temps_min: int
    score_confiance: float  # 0.0 – 1.0  # noqa: RUF003
    raison: str

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "mode_label": self.mode_label,
            "mode_icon": self.mode_icon,
            "temps_min": self.temps_min,
            "score_confiance": round(self.score_confiance, 2),
            "raison": self.raison,
        }


# =============================================================================
# Helpers
# =============================================================================
def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _walk_duration_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Durée marche (min) à 4.5 km/h."""
    dist_m = _haversine_m(lat1, lon1, lat2, lon2)
    return max(1, int(round(dist_m / 1000.0 / 4.5 * 60.0)))  # noqa: RUF046


def _velov_duration_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Durée Vélov (min) à 15 km/h."""
    dist_m = _haversine_m(lat1, lon1, lat2, lon2)
    return max(1, int(round(dist_m / 1000.0 / 15.0 * 60.0)))  # noqa: RUF046


def _snap_to_lieu(lat: float, lon: float) -> dict | None:
    """Snap un point GPS sur le lieu référentiel le plus proche (< 5km)."""
    rows = execute_query(
        """
        SELECT lieu_id, name, lon, lat, type
        FROM referentiel.lieux_lyon
        WHERE is_active = TRUE
        ORDER BY referentiel.haversine_m(lat, lon, %s, %s) ASC
        LIMIT 1
        """,
        (lat, lon),
    )
    return dict(rows[0]) if rows else None


def _traffic_delay_factor(lieu_id: int) -> float:
    """Retard moyen actuel sur les lignes TCL (0 = fluide, 1 = bloqué)."""
    try:
        rows = execute_query(
            """
            SELECT
                AVG(
                    CASE
                        WHEN avg_speed_kmh IS NOT NULL AND vitesse_limite_kmh > 0
                        THEN GREATEST(0.0, 1.0 - avg_speed_kmh / NULLIF(vitesse_limite_kmh, 0))
                        ELSE 0.0
                    END
                ) AS congestion_factor
            FROM gold.traffic_features_live
            WHERE computed_at >= NOW() - INTERVAL '1 hour'
              AND avg_speed_kmh IS NOT NULL
            LIMIT 1
            """,
            (),
        )
        if rows and rows[0].get("congestion_factor") is not None:
            return float(rows[0]["congestion_factor"])
    except Exception as e:
        logger.debug("traffic_delay_factor DB error: %s", e)
    return 0.0


def _velov_availability_score(lieu_id: int) -> float:
    """Score dispo Vélov pour un lieu (0 = aucun vélos, 1 = abondance)."""
    try:
        velovs = get_smart_velov_for_lieu(lieu_id, k=3)
        if not velovs:
            return 0.0
        total_bikes = sum(v.get("num_bikes_available", 0) or 0 for v in velovs)
        total_docks = sum(v.get("num_docks_available", 0) or 0 for v in velovs)
        bikes_score = min(1.0, total_bikes / 10.0)
        docks_score = min(1.0, total_docks / 10.0)
        return round(bikes_score * docks_score, 2)
    except Exception as e:
        logger.debug("velov_availability_score error: %s", e)
        return 0.5


def _get_hour_bucket() -> str:
    """Bucket horaire actuel (ex: '08:00') pour filtrer les cadences TCL."""
    try:
        rows = execute_query("SELECT TO_CHAR(NOW(), 'HH24:00') AS bucket")
        if rows:
            return rows[0]["bucket"]
    except Exception:
        pass
    return "08:00"


def _get_cadence_for_lieu_line(lieu_id: int, line_ref: str) -> int | None:
    """Cadence observée (min) pour une ligne à un lieu, à l'heure courante."""
    try:
        bucket = _get_hour_bucket()
        rows = execute_query(
            """
            SELECT cadence_min_per_vehicle, confidence
            FROM referentiel.lieux_calendrier
            WHERE lieu_id = %s AND line_ref = %s AND time_bucket = %s
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (lieu_id, line_ref, bucket),
        )
        if rows and rows[0].get("cadence_min_per_vehicle") is not None:
            return int(rows[0]["cadence_min_per_vehicle"])
    except Exception as e:
        logger.debug("cadence lookup error: %s", e)
    return None


# =============================================================================
# Logique métier par mode
# =============================================================================
def _build_velov_alternative(
    origin_lieu: dict,
    dest_lieu: dict,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    usual_duration: int,
) -> Alternative | None:
    """Construit une alternative Vélov si des stations sont disponibles."""
    origin_velovs = get_smart_velov_for_lieu(origin_lieu["lieu_id"], k=1)
    dest_velovs = get_smart_velov_for_lieu(dest_lieu["lieu_id"], k=1)

    if not origin_velovs or not dest_velovs:
        return None

    origin_v = origin_velovs[0]
    dest_v = dest_velovs[0]

    bikes = origin_v.get("num_bikes_available") or 0
    docks = dest_v.get("num_docks_available") or 0
    if bikes == 0 or docks == 0:
        return None

    walk_to = _walk_duration_m(origin_lat, origin_lon, origin_v["velov_lat"], origin_v["velov_lon"])
    velov_ride = _velov_duration_m(
        origin_v["velov_lat"],
        origin_v["velov_lon"],
        dest_v["velov_lat"],
        dest_v["velov_lon"],
    )
    walk_from = _walk_duration_m(dest_v["velov_lat"], dest_v["velov_lon"], dest_lat, dest_lon)
    total = walk_to + velov_ride + walk_from

    velov_score = _velov_availability_score(origin_lieu["lieu_id"])
    bikes_factor = min(1.0, bikes / 5.0)
    docks_factor = min(1.0, docks / 5.0)
    score = round(velov_score * 0.6 + bikes_factor * 0.2 + docks_factor * 0.2, 2)

    reason_parts = [
        f"{bikes} velos dispo a {origin_v['velov_name']}",
        f"{docks} places a {dest_v['velov_name']}",
    ]
    if total <= usual_duration:
        reason_parts.append(f"aussi rapide ({total} min vs {usual_duration})")
    elif total <= usual_duration * 1.3:
        reason_parts.append(f"+{total - usual_duration} min vs metro")

    return Alternative(
        mode="velov",
        mode_label="Velov'",
        mode_icon="bike",
        temps_min=total,
        score_confiance=score,
        raison=" . ".join(reason_parts),
    )


def _build_bus_alternative(
    origin_lieu: dict,
    dest_lieu: dict,
    usual_duration: int,
    current_mode: str,
) -> Alternative | None:
    """Construit une alternative bus si des lignes sont disponibles."""
    transports = get_lieux_transports(dest_lieu["lieu_id"])
    buses = [t for t in transports if t.get("line_mode") in ("bus", "tram")]
    if not buses:
        return None

    best = buses[0]
    line = best["line_ref"]
    stop = best["stop_name"]
    dist_stop = int(best.get("distance_m") or 0)

    walk_to_stop = max(1, int(round(dist_stop / 1000.0 / 4.5 * 60.0)))  # noqa: RUF046
    cadence = _get_cadence_for_lieu_line(dest_lieu["lieu_id"], line)
    wait = cadence or 6
    dist_bus = _haversine_m(
        origin_lieu["lat"],
        origin_lieu["lon"],
        dest_lieu["lat"],
        dest_lieu["lon"],
    )
    bus_dur = max(1, int(round(dist_bus / 1000.0 / 18.0 * 60.0)))  # noqa: RUF046
    total = walk_to_stop + wait + bus_dur

    congestion = _traffic_delay_factor(dest_lieu["lieu_id"])
    cadence_factor = 1.0 if (cadence or 0) <= 8 else 0.7
    score = round((1.0 - congestion) * cadence_factor * 0.8, 2)

    reason_parts = [f"{line} a {stop} ({dist_stop}m a pied)"]
    if cadence:
        reason_parts.append(f"attente ~{wait} min")
    reason_parts.append("pas de correspondances")
    if total <= usual_duration:
        reason_parts.append(f"aussi rapide ({total} min)")
    elif total <= usual_duration * 1.5:
        reason_parts.append(f"+{total - usual_duration} min vs {current_mode}")

    return Alternative(
        mode="bus",
        mode_label=f"Bus {line}",
        mode_icon="bus",
        temps_min=total,
        score_confiance=score,
        raison=" . ".join(reason_parts),
    )


def _build_walk_alternative(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    usual_duration: int,
) -> Alternative | None:
    """Construit une alternative marche directe si distance < 2km."""
    dist = _haversine_m(origin_lat, origin_lon, dest_lat, dest_lon)
    if dist > 2000:
        return None
    total = _walk_duration_m(origin_lat, origin_lon, dest_lat, dest_lon)
    dist_factor = max(0.3, 1.0 - dist / 2000.0)
    score = round(dist_factor * 0.7, 2)
    return Alternative(
        mode="walk",
        mode_label="A pied",
        mode_icon="walk",
        temps_min=total,
        score_confiance=score,
        raison=f"{int(dist)}m -- direct, bon pour la sante",
    )


def _build_vtc_alternative(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    usual_duration: int,
    dest_lieu: dict,
) -> Alternative | None:
    """Construit une alternative VTC/taxi (Uber, etc.) -- toujours disponible."""
    dist = _haversine_m(origin_lat, origin_lon, dest_lat, dest_lon)
    direct_dur = max(1, int(round(dist / 1000.0 / 30.0 * 60.0)))  # noqa: RUF046
    total = 5 + int(direct_dur * 1.2)

    congestion = _traffic_delay_factor(dest_lieu["lieu_id"])
    score = round((1.0 - congestion * 0.5) * 0.75, 2)

    reason_parts = [
        f"~{dist / 1000:.1f} km",
        "disponible 24h/24",
    ]
    if total <= usual_duration:
        reason_parts.append(f"plus rapide ({total} min)")
    else:
        reason_parts.append(f"+{total - usual_duration} min vs metro")

    return Alternative(
        mode="vtc",
        mode_label="VTC / Taxi",
        mode_icon="taxi",
        temps_min=total,
        score_confiance=score,
        raison=" . ".join(reason_parts),
    )


# =============================================================================
# API principale
# =============================================================================
def get_alternatives(favorite: dict) -> list[dict]:
    """Génère des alternatives multimodales pour un trajet favori.

    Args:
        favorite: dict avec au minimum :
            id, name, origin, destination, usual_mode, usual_duration_min
            origin_lat, origin_lon, dest_lat, dest_lon (optionnel)

    Returns:
        Liste de dicts triés par score_confiance décroissant :
        [{mode, mode_label, mode_icon, temps_min, score_confiance, raison}, ...]
    """
    if _is_demo_mode():
        return _mock_alternatives(favorite)

    if not _is_db_available():
        raise DashboardDataError(
            source="get_alternatives",
            detail="PostgreSQL indisponible -- impossible de generer les alternatives",
        )

    origin_lat = favorite.get("origin_lat")
    origin_lon = favorite.get("origin_lon")
    dest_lat = favorite.get("dest_lat")
    dest_lon = favorite.get("dest_lon")
    usual_duration = favorite.get("usual_duration_min") or 20
    current_mode = MODE_LABEL.get(favorite.get("usual_mode", ""), "transit")

    origin_lieu = _snap_to_lieu(origin_lat or 45.7600, origin_lon or 4.8500)
    dest_lieu = _snap_to_lieu(dest_lat or 45.7600, dest_lon or 4.8500)

    if not origin_lieu or not dest_lieu:
        logger.warning("Snap lieux failed for favorite %s -- using mock fallback", favorite.get("id"))
        return _mock_alternatives(favorite)

    alternatives: list[Alternative] = []

    if current_mode not in ("velov", "walk"):
        velov_alt = _build_velov_alternative(
            origin_lieu,
            dest_lieu,
            origin_lat or origin_lieu["lat"],
            origin_lon or origin_lieu["lon"],
            dest_lat or dest_lieu["lat"],
            dest_lon or dest_lieu["lon"],
            usual_duration,
        )
        if velov_alt:
            alternatives.append(velov_alt)

    if current_mode not in ("bus", "tram"):
        bus_alt = _build_bus_alternative(origin_lieu, dest_lieu, usual_duration, current_mode)
        if bus_alt:
            alternatives.append(bus_alt)

    if origin_lat and origin_lon and dest_lat and dest_lon:
        walk_alt = _build_walk_alternative(
            origin_lat,
            origin_lon,
            dest_lat,
            dest_lon,
            usual_duration,
        )
        if walk_alt:
            alternatives.append(walk_alt)

    if dest_lieu:
        vtc_alt = _build_vtc_alternative(
            origin_lat or origin_lieu["lat"],
            origin_lon or origin_lieu["lon"],
            dest_lat or dest_lieu["lat"],
            dest_lon or dest_lieu["lon"],
            usual_duration,
            dest_lieu,
        )
        if vtc_alt:
            alternatives.append(vtc_alt)

    alternatives.sort(key=lambda a: a.score_confiance, reverse=True)
    return [alt.to_dict() for alt in alternatives]


def _mock_alternatives(favorite: dict) -> list[dict]:
    """Alternatives mock réalistes pour le mode démo."""
    usual_duration = favorite.get("usual_duration_min") or 20
    current_mode = MODE_LABEL.get(favorite.get("usual_mode", ""), "transit")

    mock_alts = [
        {
            "mode": "velov",
            "mode_label": "Velov'",
            "mode_icon": "bike",
            "temps_min": max(1, usual_duration - 3),
            "score_confiance": 0.82,
            "raison": "12 velos dispo a Part-Dieu . 8 docks a Villeurbanne . a 3 min plus rapide",
        },
        {
            "mode": "bus",
            "mode_label": "Bus C13",
            "mode_icon": "bus",
            "temps_min": usual_duration + 5,
            "score_confiance": 0.68,
            "raison": "C13 a 150m . attente ~4 min . pas de correspondances . ~+5 min vs metro",
        },
        {
            "mode": "vtc",
            "mode_label": "VTC / Taxi",
            "mode_icon": "taxi",
            "temps_min": max(1, usual_duration - 8),
            "score_confiance": 0.72,
            "raison": "4.2 km . disponible 24h/24 . plus rapide (14 min)",
        },
    ]

    if current_mode != "walk":
        mock_alts.append(
            {
                "mode": "walk",
                "mode_label": "A pied",
                "mode_icon": "walk",
                "temps_min": usual_duration + 15,
                "score_confiance": 0.35,
                "raison": "2800m -- direct, bon pour la sante, pas de CO2",
            }
        )

    return mock_alts
