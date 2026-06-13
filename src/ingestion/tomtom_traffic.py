"""Collecteur TomTom Traffic Flow — trafic temps réel (free tier).

Sprint VPS-6 (2026-06-11) — Ajout de TomTom pour compléter les zones non
couvertes par les boucles Grand Lyon. Sprint précédent l'avait listé
"Supprimé : TomTom API | Payant, redondant avec boucles" — mais avec
le free tier (2500 req/jour) et un cache agressif, c'est viable pour
un monitoring à 15 min de cycle sur Lyon.

API utilisée : TomTom Traffic Flow Segment
  https://api.tomtom.com/traffic/services/4/flowSegmentData/{style}/10/json
  Params : point=lat,lon, style=absolute, key=$TOMTOM_API_KEY
  Retourne : currentSpeed, freeFlowSpeed, currentTravelTime, confidence

Modes :
* Live  : query API, cache 5 min par tuile 0.02° (~2km)
* Cache : servi depuis cache mémoire process (TTL)
* Fallback: si quota épuisé ou API indispo, retourne la dernière
  valeur cachée (jusqu'à 24h) puis None.

Le collecteur Bronze s'exécute via DAG ``collect_tomtom_traffic``
(Sprint 7+) toutes les 15 min sur 12 tuiles utiles de Lyon.
Pour le dashboard, on lit la table ``bronze.tomtom_traffic`` via
``data_loader.load_traffic_for_map()`` qui fusionne Gold + TomTom.

Calcul budget (free tier 2500 req/jour) :
* Tuiles Lyon bbox 4.85°E-4.92°E x 45.72°N-45.81°N, grille 0.02° :
  (0.07/0.02) x (0.09/0.02) = 3.5 x 4.5 = ~16 tuiles, on en suit 12
  utiles (centre urbain).
* 12 tuiles x 4 cycles/h x 24h = 1152 req/jour.
* Marge : 1348 req pour debug, ad-hoc, pics.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_settings

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------

# Bounding box Lyon centre (4.82°E à 4.92°E, 45.72°N à 45.81°N)
LYON_BBOX = {
    "min_lon": 4.82,
    "max_lon": 4.92,
    "min_lat": 45.72,
    "max_lat": 45.81,
}

# Grille de tuiles 0.02° (~2 km). On couvre 12 tuiles utiles
# (centre urbain dense, là où il y a le plus de zones sans boucle).
TILE_SIZE_DEG = 0.02
LYON_TILES: list[tuple[float, float]] = [
    (lat, lon)
    for lat in [
        45.74,
        45.76,
        45.78,
        45.80,  # sud → nord
    ]
    for lon in [
        4.83,
        4.85,
        4.87,
        4.89,  # ouest → est
    ]
]

# Cache process 5 min par tuile
_CACHE_TTL_S = 5 * 60

# Quota journalier (free tier 2500 req/jour, marge sécurité à 2000)
DAILY_QUOTA = 2000


# -----------------------------------------------------------------------------
# Cache process
# -----------------------------------------------------------------------------

_cache: dict[str, tuple[float, dict | None]] = {}
_daily_request_count = 0
_daily_reset_date: str = ""


def _reset_daily_quota_if_needed() -> None:
    """Reset compteur journalier à minuit UTC."""
    global _daily_request_count, _daily_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if today != _daily_reset_date:
        _daily_request_count = 0
        _daily_reset_date = today


def _quota_remaining() -> int:
    """Renvoie le nombre de requêtes restantes aujourd'hui (>=0)."""
    _reset_daily_quota_if_needed()
    return max(0, DAILY_QUOTA - _daily_request_count)


def _tile_key(lat: float, lon: float) -> str:
    """Clé de cache = tuile arrondie à 0.02°."""
    lat_t = round(lat / TILE_SIZE_DEG) * TILE_SIZE_DEG
    lon_t = round(lon / TILE_SIZE_DEG) * TILE_SIZE_DEG
    return f"{lat_t:.4f}_{lon_t:.4f}"


def _cache_get(key: str) -> dict | None:
    """Lookup cache process. Renvoie None si expiré ou absent."""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_S:
        return None
    return value


def _cache_set(key: str, value: dict | None) -> None:
    _cache[key] = (time.monotonic(), value)


# -----------------------------------------------------------------------------
# API TomTom
# -----------------------------------------------------------------------------


def get_api_key() -> str | None:
    """Lit TOMTOM_API_KEY depuis env / settings.

    Returns None si non configuré → caller fallback cache/None.
    """
    s = get_settings()
    key = os.getenv("TOMTOM_API_KEY") or getattr(s, "tomtom_api_key", None)
    if not key:
        return None
    return key.strip()


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _query_tomtom_flow(lat: float, lon: float, api_key: str) -> dict:
    """Appel API TomTom Flow Segment. Lève HTTPError si non-200.

    Documentation TomTom :
    https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data
    """
    url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {"point": f"{lat},{lon}", "key": api_key}
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def get_flow(lat: float, lon: float, use_cache: bool = True) -> dict | None:
    """Récupère le trafic temps réel pour 1 point GPS.

    Args:
        lat, lon: coordonnées GPS (WGS84).
        use_cache: si True (défaut), sert depuis cache process si <5 min.

    Returns:
        Dict ``{current_speed_kmh, free_flow_speed_kmh, ratio, confidence,
        current_travel_time_s, free_flow_travel_time_s, fetched_at,
        tile_key}`` ou None si indispo (quota épuisé, API down, no key).

    Logique :
    1. Si use_cache, lookup cache par tuile. Hit → return.
    2. Si quota journalier épuisé, log warning et return None.
    3. Sinon query TomTom, parse, cache, incrémente quota, return.
    """
    global _daily_request_count

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Coordonnées GPS invalides: lat={lat}, lon={lon}")

    key = _tile_key(lat, lon)

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    api_key = get_api_key()
    if not api_key:
        logger.debug("TOMTOM_API_KEY non configuré, fallback None")
        _cache_set(key, None)
        return None

    _reset_daily_quota_if_needed()
    if _daily_request_count >= DAILY_QUOTA:
        logger.warning(
            "TomTom quota journalier épuisé (%d/%d), fallback None",
            _daily_request_count,
            DAILY_QUOTA,
        )
        return None

    try:
        data = _query_tomtom_flow(lat, lon, api_key)
    except Exception as e:
        logger.warning("TomTom API a échoué pour (%s, %s): %s", lat, lon, e)
        _cache_set(key, None)
        return None

    _daily_request_count += 1

    # Parse réponse TomTom Flow Segment
    # Format : {"flowSegmentData": {"currentSpeed": int, "freeFlowSpeed": int,
    #   "currentTravelTime": int, "freeFlowTravelTime": int, "confidence": float}}
    flow = data.get("flowSegmentData", {})
    if not flow:
        logger.debug("TomTom réponse vide pour (%s, %s)", lat, lon)
        _cache_set(key, None)
        return None

    current_speed = float(flow.get("currentSpeed", 0))
    free_flow = float(flow.get("freeFlowSpeed", 1))
    ratio = current_speed / free_flow if free_flow > 0 else 0.0

    result = {
        "current_speed_kmh": current_speed,
        "free_flow_speed_kmh": free_flow,
        "ratio": round(ratio, 3),
        "confidence": float(flow.get("confidence", 0)),
        "current_travel_time_s": int(flow.get("currentTravelTime", 0)),
        "free_flow_travel_time_s": int(flow.get("freeFlowTravelTime", 0)),
        "fetched_at": datetime.now(UTC).isoformat(),
        "tile_key": key,
        "lat": lat,
        "lon": lon,
    }
    _cache_set(key, result)
    return result


# -----------------------------------------------------------------------------
# Collecte Bronze (bulk pour les 12 tuiles Lyon)
# -----------------------------------------------------------------------------


def collect_lyon_tiles() -> list[dict]:
    """Collecte TomTom Flow pour les 12 tuiles utiles de Lyon.

    À appeler depuis le DAG ``collect_tomtom_traffic`` (Sprint 7+).
    Idempotent : utilise cache 5min, donc ne consume pas le quota
    si appelé plus souvent que toutes les 5 min.
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning(
            "TOMTOM_API_KEY non configuré — collect_lyon_tiles() no-op. "
            "Inscrivez-vous sur https://developer.tomtom.com/ (free tier "
            "2500 req/jour) et ajoutez TOMTOM_API_KEY=... dans .env"
        )
        return []

    results = []
    for lat, lon in LYON_TILES:
        result = get_flow(lat, lon, use_cache=False)
        if result is not None:
            results.append(result)
        # Rate limit : 1 req / 200ms pour rester poli
        time.sleep(0.2)
    return results


def save_lyon_tiles_to_bronze(results: list[dict]) -> int:
    """Persiste les résultats TomTom en table ``bronze.tomtom_traffic``.

    Returns:
        Nombre de lignes insérées.
    """
    if not results:
        return 0

    from src.db.connection import get_connection

    rows = [
        (
            r["lat"],
            r["lon"],
            r["current_speed_kmh"],
            r["free_flow_speed_kmh"],
            r["ratio"],
            r["confidence"],
            r["current_travel_time_s"],
            r["free_flow_travel_time_s"],
            r["tile_key"],
            r["fetched_at"],
        )
        for r in results
    ]

    sql = """
        INSERT INTO bronze.tomtom_traffic
            (lat, lon, current_speed_kmh, free_flow_speed_kmh, ratio,
             confidence, current_travel_time_s, free_flow_travel_time_s,
             tile_key, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tile_key, fetched_at) DO NOTHING
    """
    from psycopg2.extras import execute_batch

    n = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows, page_size=100)
            n = cur.rowcount
        conn.commit()
    logger.info("TomTom: %d lignes insérées dans bronze.tomtom_traffic", n)
    return n


# -----------------------------------------------------------------------------
# Bridge Gold ↔ TomTom (utilisé par data_loader)
# -----------------------------------------------------------------------------


def get_live_flow_for_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    use_cache: bool = True,
) -> list[dict]:
    """Renvoie les points TomTom Flow dans une bounding box.

    Sert le dashboard "Carte trafic H+30min" : pour chaque tuile
    intersectant la bbox, on récupère la vitesse temps réel TomTom.
    Si TomTom indispo, on retombe sur bronze.tomtom_traffic (dernier
    snapshot DB).
    """
    tiles = []
    lat = min_lat
    while lat <= max_lat:
        lon = min_lon
        while lon <= max_lon:
            tiles.append((lat, lon))
            lon += TILE_SIZE_DEG
        lat += TILE_SIZE_DEG

    out = []
    for lat, lon in tiles:
        result = get_flow(lat, lon, use_cache=use_cache)
        if result is not None:
            out.append(result)
    return out


def reset_cache() -> None:
    """Reset cache process (utile pour les tests)."""
    global _cache, _daily_request_count, _daily_reset_date
    _cache.clear()
    _daily_request_count = 0
    _daily_reset_date = ""


# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------


def health() -> dict:
    """Renvoie l'état du connecteur TomTom (pour les healthchecks)."""
    api_key = get_api_key()
    return {
        "api_key_configured": bool(api_key),
        "cache_size": len(_cache),
        "daily_requests": _daily_request_count,
        "daily_quota": DAILY_QUOTA,
        "quota_remaining": _quota_remaining(),
        "daily_reset_date": _daily_reset_date,
        "tiles_configured": len(LYON_TILES),
    }
