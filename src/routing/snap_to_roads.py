"""Snap-to-roads via Overpass API (OpenStreetMap).

Sprint 10+ UX (2026-06-12) — Les nœuds H3 du graphe routier
(gold.dim_spatial_grid_mapping) ne sont pas exactement sur les rues :
ils sont au centre de cellules hexagonales (rayon ~10m en res 13), ce
qui peut tomber dans le Rhône, sur un toit ou perpendiculairement à la
rue.

**Stratégie** : pour chaque (lat, lon), query Overpass pour trouver
les ways (rues) dans un rayon de ~30m, puis projeter le point sur le
way le plus proche.

**Performance** :
- Overpass API publique : ~200-500ms par requête (rate-limited 10 req/s)
- Cache 1h en mémoire (Lyon intra-muros a 1543 nœuds → ~5min pour
  tout snapper en cold start, ~instantané en warm)
- Fallback gracieux si Overpass down (retourne le point original)

**API publique** :
- ``snap_to_road(lat, lon, radius_m=30) -> (snapped_lat, snapped_lon)``
- ``snap_path_to_roads(points: list[tuple[float, float]]) -> list[tuple]``
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CACHE_TTL_SECONDS = 3600  # 1h
CACHE_GRID_SIZE_DEG = 0.001  # ~100m grid for cache bucketing

# Module-level cache: {(grid_lat_idx, grid_lon_idx): (snapped_lat, snapped_lon, ts)}
_cache: dict[tuple[int, int], tuple[float, float, float]] = {}


def _grid_key(lat: float, lon: float) -> tuple[int, int]:
    """Bucket (lat, lon) en grille ~100m pour le cache."""
    return (int(lat / CACHE_GRID_SIZE_DEG), int(lon / CACHE_GRID_SIZE_DEG))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _project_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float]:
    """Projette un point P sur le segment AB. Retourne (proj_x, proj_y, dist_m).

    Algorithme : clamp du paramètre t entre 0 et 1 sur le segment.
    Conversion degrés → mètres via approximation locale cos(lat).
    """
    # Convert to local meters (WGS84) using equirectangular projection
    lat0 = (ay + by) / 2
    cos_lat = math.cos(math.radians(lat0))
    ax_m = (ax) * cos_lat * 111_320
    ay_m = ay * 110_540
    bx_m = (bx) * cos_lat * 111_320
    by_m = by * 110_540
    px_m = (px) * cos_lat * 111_320
    py_m = py * 110_540

    dx, dy = bx_m - ax_m, by_m - ay_m
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        # Segment dégénéré
        d = _haversine_m(py, px, ay, ax)
        return ax, ay, d
    t = ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    proj_x = ax + t * (bx - ax)
    proj_y = ay + t * (by - ay)
    d = _haversine_m(py, px, proj_y, proj_x)
    return proj_x, proj_y, d


def _query_overpass(lat: float, lon: float, radius_m: float) -> list[tuple[float, float, float, float]]:
    """Query Overpass pour les ways dans un rayon donné. Retourne liste de segments [(lat1,lon1,lat2,lon2)]."""
    # Rayon en degrés (approx)
    radius_deg = radius_m / 111_320
    query = f"""
    [out:json][timeout:8];
    way(
      around:{radius_m},{lat},{lon}
    )["highway"];
    out geom;
    """
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning("Overpass query failed for (%s, %s): %s", lat, lon, e)
        return []

    segments: list[tuple[float, float, float, float]] = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry", [])
        for i in range(len(geom) - 1):
            a, b = geom[i], geom[i + 1]
            segments.append((a["lat"], a["lon"], b["lat"], b["lon"]))
    return segments


def snap_to_road(
    lat: float,
    lon: float,
    radius_m: float = 30.0,
    use_cache: bool = True,
) -> tuple[float, float]:
    """Projeette un point (lat, lon) sur la rue OSM la plus proche.

    Args:
        lat, lon: coordonnées GPS du point.
        radius_m: rayon de recherche Overpass (défaut 30m).
        use_cache: utiliser le cache 1h (défaut True).

    Returns:
        Tuple (snapped_lat, snapped_lon). Si Overpass échoue ou ne
        trouve aucune rue dans le rayon, retourne le point original.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return lat, lon

    # Cache hit
    if use_cache:
        key = _grid_key(lat, lon)
        cached = _cache.get(key)
        if cached and (time.time() - cached[2]) < CACHE_TTL_SECONDS:
            return cached[0], cached[1]

    # Overpass query
    segments = _query_overpass(lat, lon, radius_m)
    if not segments:
        # Pas de rue dans le rayon → fallback point original
        return lat, lon

    # Trouve le segment le plus proche et projette
    best: tuple[float, float, float] | None = None  # (proj_lat, proj_lon, dist_m)
    for a_lat, a_lon, b_lat, b_lon in segments:
        proj_lon, proj_lat, d = _project_on_segment(lon, lat, a_lon, a_lat, b_lon, b_lat)
        if best is None or d < best[2]:
            best = (proj_lat, proj_lon, d)

    if best is None:
        return lat, lon

    snapped_lat, snapped_lon, dist_m = best
    if use_cache:
        _cache[key] = (snapped_lat, snapped_lon, time.time())
    return snapped_lat, snapped_lon


def snap_path_to_roads(
    points: Iterable[tuple[float, float]],
    radius_m: float = 30.0,
) -> list[tuple[float, float]]:
    """Snap une polyligne complète. Utilise le cache."""
    return [snap_to_road(lat, lon, radius_m=radius_m) for lat, lon in points]


def reset_cache() -> None:
    """Reset le cache module-level (utile pour les tests)."""
    _cache.clear()
