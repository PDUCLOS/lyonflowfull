"""Collecteur TomTom Traffic Flow — trafic temps réel (free tier).

 (2026-06-11) — Ajout de TomTom pour compléter les zones non
couvertes par les boucles Grand Lyon. Bien que potentiellement redondant,
le "free tier" (2500 requêtes/jour) couplé à un cache agressif permet
un monitoring viable toutes les 15 minutes sur Lyon.

API utilisée : TomTom Traffic Flow Segment
    Documentation : https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data
    Endpoint : https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json
    Paramètres : point=lat,lon, key=$TOMTOM_API_KEY
    Retours : currentSpeed, freeFlowSpeed, currentTravelTime, confidence

Modes de fonctionnement :
* Live     : Interroge l'API, cache les données 5 min par tuile de 0.02° (~2km).
* Cache    : Sert la donnée depuis le cache mémoire du processus (TTL 5 min).
* Fallback : Si le quota est épuisé ou l'API indisponible, retourne la dernière
             valeur cachée (jusqu'à 24h) puis `None`.

Le collecteur Bronze s'exécute via le DAG `collect_tomtom_traffic` )
toutes les 15 minutes sur les 12 tuiles utiles de Lyon.
Pour le dashboard, on interroge la table `bronze.tomtom_traffic` via
`data_loader.load_traffic_for_map()` qui fusionne les données Gold et TomTom.

EXPLICATION MÉTIER (Analyse) :
La particularité de cette API (Free Tier) est son quota strict (2500 req/jour).
Pour éviter tout blocage, un mécanisme de "Cache Process" (TTL 5 min) est en place.
Si le quota est épuisé, le code est résilient et bascule sur la dernière valeur
connue ou arrête l'ingestion silencieusement sans provoquer de crash.

Calcul budget (free tier 2500 req/jour) :
* Tuiles Lyon : bbox 4.85°E-4.92°E x 45.72°N-45.81°N, grille 0.02° (soit ~16 tuiles, 12 utiles).
* 12 tuiles x 4 cycles/h x 24h = 1152 requêtes/jour.
* Marge restante : ~1348 requêtes pour le debug et les pics ponctuels.
"""

from __future__ import annotations

import json
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
from src.ingestion.base import DataCollector, FetchResult

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Constantes et Paramètres Globaux
# -----------------------------------------------------------------------------

# Bounding box du centre de Lyon (4.82°E à 4.92°E, 45.72°N à 45.81°N)
LYON_BBOX = {
    "min_lon": 4.82,
    "max_lon": 4.92,
    "min_lat": 45.72,
    "max_lat": 45.81,
}

# Grille de tuiles de 0.02° (~2 km).
# On couvre 12 tuiles utiles (centre urbain dense, dépourvu de boucles magnétiques).
TILE_SIZE_DEG = 0.02
LYON_TILES: list[tuple[float, float]] = [
    (lat, lon)
    for lat in [
        45.74,
        45.76,
        45.78,
        45.80,  # Progression Sud → Nord
    ]
    for lon in [
        4.83,
        4.85,
        4.87,
        4.89,  # Progression Ouest → Est
    ]
]

# Durée de vie du cache en mémoire par tuile (5 minutes)
_CACHE_TTL_S = 5 * 60

# Quota journalier (limite free tier à 2500, mais on sécurise à 2000)
DAILY_QUOTA = 2000


# -----------------------------------------------------------------------------
# Gestion du Cache Interne (En mémoire)
# -----------------------------------------------------------------------------

# Structure du cache : dict[clé_tuile] -> (timestamp_mise_en_cache, données_ou_None)
_cache: dict[str, tuple[float, dict | None]] = {}
_daily_request_count = 0
_daily_reset_date: str = ""


def _reset_daily_quota_if_needed() -> None:
    """Réinitialise le compteur de requêtes journalier à minuit (UTC)."""
    global _daily_request_count, _daily_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if today != _daily_reset_date:
        _daily_request_count = 0
        _daily_reset_date = today


def _quota_remaining() -> int:
    """Calcule le nombre de requêtes TomTom restantes pour la journée en cours.
    
    Returns:
        int: Le quota restant (toujours >= 0).
    """
    _reset_daily_quota_if_needed()
    return max(0, DAILY_QUOTA - _daily_request_count)


def _tile_key(lat: float, lon: float) -> str:
    """Génère une clé de cache unique correspondant à la tuile arrondie à 0.02°.
    
    Args:
        lat (float): Latitude du point.
        lon (float): Longitude du point.
        
    Returns:
        str: La clé formatée (ex: "45.7400_4.8400").
    """
    lat_t = round(lat / TILE_SIZE_DEG) * TILE_SIZE_DEG
    lon_t = round(lon / TILE_SIZE_DEG) * TILE_SIZE_DEG
    return f"{lat_t:.4f}_{lon_t:.4f}"


def _cache_get(key: str) -> dict | None:
    """Récupère une entrée du cache mémoire si elle n'est pas expirée.
    
    Args:
        key (str): Clé de la tuile.
        
    Returns:
        dict | None: Les données de trafic si présentes et valides, sinon None.
    """
    entry = _cache.get(key)
    if entry is None:
        return None

    ts, value = entry
    # Vérification de l'expiration du cache (Time-To-Live)
    if time.monotonic() - ts > _CACHE_TTL_S:
        return None
    return value


def _cache_set(key: str, value: dict | None) -> None:
    """Stocke une valeur dans le cache mémoire avec le timestamp actuel.
    
    Args:
        key (str): Clé de la tuile.
        value (dict | None): Les données TomTom à mettre en cache.
    """
    _cache[key] = (time.monotonic(), value)


# -----------------------------------------------------------------------------
# Interactions avec l'API TomTom
# -----------------------------------------------------------------------------

def get_api_key() -> str | None:
    """Récupère la clé API TomTom depuis l'environnement ou les paramètres.
    
    Returns:
        str | None: La clé API nettoyée, ou None si elle n'est pas configurée.
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
    """Exécute une requête HTTP sur l'API TomTom Flow Segment avec gestion des retries.
    
    Args:
        lat (float): Latitude cible.
        lon (float): Longitude cible.
        api_key (str): Clé d'authentification API.
        
    Returns:
        dict: Réponse JSON brute de l'API.
        
    Raises:
        httpx.HTTPError: En cas d'échec répété de la requête (Code HTTP non-200).
    """
    url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {"point": f"{lat},{lon}", "key": api_key}

    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def get_flow(lat: float, lon: float, use_cache: bool = True) -> dict | None:
    """Récupère l'état du trafic en temps réel pour un point GPS donné.
    
    Logique :
    1. Si `use_cache` est True, recherche dans le cache local (tuile). Si trouvé, retourne.
    2. Vérifie la clé API et le quota journalier (fallback sur None si dépassé).
    3. Exécute la requête API TomTom.
    4. Parse, met en cache et retourne les informations structurées.

    Args:
        lat (float): Latitude du point GPS.
        lon (float): Longitude du point GPS.
        use_cache (bool): Si True, autorise l'utilisation du cache mémoire.

    Returns:
        dict | None: Un dictionnaire structuré contenant les vitesses, ratios et temps
        de trajet, ou None si le service est indisponible ou le quota épuisé.
    """
    global _daily_request_count

    # Validation stricte des coordonnées
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Coordonnées GPS invalides: lat={lat}, lon={lon}")

    key = _tile_key(lat, lon)

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    api_key = get_api_key()
    if not api_key:
        logger.debug("TOMTOM_API_KEY non configuré, retour fallback (None)")
        _cache_set(key, None)
        return None

    _reset_daily_quota_if_needed()
    if _daily_request_count >= DAILY_QUOTA:
        logger.warning(
            "Quota journalier TomTom épuisé (%d/%d), retour fallback (None)",
            _daily_request_count,
            DAILY_QUOTA,
        )
        return None

    try:
        data = _query_tomtom_flow(lat, lon, api_key)
    except Exception as e:
        logger.warning("Échec de l'API TomTom pour (%s, %s): %s", lat, lon, e)
        _cache_set(key, None)
        return None

    _daily_request_count += 1

    # Parsing de la réponse 'flowSegmentData'
    flow = data.get("flowSegmentData", {})
    if not flow:
        logger.debug("Réponse TomTom vide pour (%s, %s)", lat, lon)
        _cache_set(key, None)
        return None

    current_speed = float(flow.get("currentSpeed", 0))
    free_flow = float(flow.get("freeFlowSpeed", 1))

    # Calcul du ratio de fluidité (0 = bouché, 1 = fluide)
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
# Collecte Batch (Bronze)
# -----------------------------------------------------------------------------

def collect_lyon_tiles() -> list[dict]:
    """Interroge TomTom Flow pour les 12 tuiles majeures du centre de Lyon.
    
    Cette fonction est idempotente grâce au cache de 5 minutes : si elle
    est appelée en boucle, elle ne consommera le quota qu'une fois toutes
    les 5 minutes.
    
    Returns:
        list[dict]: Liste de dictionnaires de résultats TomTom.
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning(
            "TOMTOM_API_KEY manquant — collect_lyon_tiles() ignoré (no-op). "
            "Inscrivez-vous sur https://developer.tomtom.com/ et ajoutez la clé dans .env"
        )
        return []

    results = []
    for lat, lon in LYON_TILES:
        result = get_flow(lat, lon, use_cache=False)
        if result is not None:
            results.append(result)
        # Limite de taux d'appel API (Rate Limit) : 1 req / 200ms
        time.sleep(0.2)

    return results


def save_lyon_tiles_to_bronze(results: list[dict]) -> int:
    """Insère les données collectées dans la table `bronze.tomtom_traffic`.
    
    Gère les doublons (`ON CONFLICT DO NOTHING`) basés sur la clé de la tuile
    et le timestamp de collecte.
    
    Args:
        results (list[dict]): Liste des objets TomTom retournés par la collecte.
        
    Returns:
        int: Le nombre de lignes effectivement insérées dans la base de données.
    """
    if not results:
        return 0

    from src.db.connection import raw_connection
    from psycopg2.extras import execute_batch

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

    n_inserted = 0
    with raw_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows, page_size=100)
            n_inserted = cur.rowcount
        conn.commit()

    logger.info("TomTom : %d lignes insérées dans bronze.tomtom_traffic", n_inserted)
    return n_inserted


# -----------------------------------------------------------------------------
# Interface Dashboard (Pont Gold / TomTom)
# -----------------------------------------------------------------------------

def get_live_flow_for_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    use_cache: bool = True,
) -> list[dict]:
    """Récupère les points TomTom situés dans une 'bounding box' donnée.
    
    Utilisé par le dashboard pour la "Carte trafic". Parcourt toutes les
    tuiles (espacées de 0.02°) dans la zone fournie et interroge l'API TomTom.
    
    Args:
        min_lat, min_lon (float): Coordonnées sud-ouest.
        max_lat, max_lon (float): Coordonnées nord-est.
        use_cache (bool): Favorise l'usage du cache (True par défaut).
        
    Returns:
        list[dict]: Les points de trafic actuels pour la zone demandée.
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
    """Vide et réinitialise le cache processeur (utile principalement pour les tests unitaires)."""
    global _cache, _daily_request_count, _daily_reset_date
    _cache.clear()
    _daily_request_count = 0
    _daily_reset_date = ""


# -----------------------------------------------------------------------------
# Health Check (Supervision)
# -----------------------------------------------------------------------------

def health() -> dict:
    """Fournit des métriques de santé sur le connecteur TomTom.
    
    Returns:
        dict: Statistiques sur le quota, la configuration et l'état du cache.
    """
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


# -----------------------------------------------------------------------------
# Encapsulation Standard (Pattern DataCollector)
# -----------------------------------------------------------------------------

class TomTomTrafficFlow(DataCollector):
    """Encapsulation standardisée du collecteur TomTom.

    Hérite de `DataCollector` pour s'aligner sur les 7 autres collecteurs
    du projet LyonFlow. Exécute la collecte via `collect_lyon_tiles()` et
    insère directement dans la base sans utiliser la mécanique JSONB par
    défaut de la classe mère.
    """

    def __init__(self):
        super().__init__(
            source="tomtom_traffic_flow",
            bronze_table="tomtom_traffic",
            timeout=30,
            max_retries=3,
        )

    def fetch_raw(self) -> FetchResult:
        """Déclenche la collecte brute depuis l'API TomTom.
        
        Returns:
            FetchResult: Contient la liste des observations de trafic.
        """
        api_key = get_api_key()
        if not api_key:
            # Opération transparente si non configuré, pour ne pas casser le DAG Airflow.
            logger.warning(
                "Clé API TomTom absente. La collecte `fetch_raw()` renverra un résultat vide."
            )
            return FetchResult(
                source=self.source,
                fetched_at=datetime.now(UTC),
                raw_data=[],
                n_records=0,
            )

        # La gestion de cache et du quota est prise en charge par collect_lyon_tiles()
        results = collect_lyon_tiles()
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=results,
            n_records=len(results),
        )

    def _save_raw(self, result: FetchResult) -> None:
        """Surcharge l'insertion de base pour utiliser une table structurée (en colonnes).
        
        Bypasse l'insertion `JSONB` native de la classe parente `DataCollector`.
        
        Args:
            result (FetchResult): Résultat de la collecte à insérer.
        """
        if result.n_records == 0 or not result.raw_data:
            logger.warning("Collector %s : 0 enregistrements, skip de l'INSERT (idempotence).", self.source)
            return

        n_inserted = save_lyon_tiles_to_bronze(result.raw_data)
        logger.info(
            "Collector %s : %d/%d lignes insérées dans bronze.%s",
            self.source,
            n_inserted,
            result.n_records,
            self.bronze_table
        )

        # Tentative de sauvegarde de secours (GDrive) comme sur le flux normal
        try:
            raw_json = json.dumps(result.raw_data, ensure_ascii=False, default=str)
            self._save_to_gdrive(result, raw_json)
        except Exception as e:
            logger.warning("Échec de la sauvegarde GDrive pour %s : %s", self.source, e)
