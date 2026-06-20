"""Couche d'accès aux données Gold/Silver pour les widgets dashboard.

Ce module encapsule les requêtes SQL paramétrées vers les tables Gold/Silver
de l'architecture Medallion, et fournit une API typée simple pour les widgets
Streamlit. Toutes les fonctions:

* Utilisent du SQL paramétré (psycopg2 %s, JAMAIS de f-string)
* Retournent des `pandas.DataFrame` (pratique pour Streamlit/Plotly)
* Levent ``DashboardDataError`` si la DB est down (politique zero mock Sprint 8)
* Sont testables hors ligne (les tests monkeypatchent ``_is_db_available``)

Pattern d'utilisation dans un widget::

    from src.data.db_query import get_latest_traffic

    df = get_latest_traffic(limit=50)  # DataFrame ou DashboardDataError
    st.dataframe(df)

Pour les widgets, voir le pattern dans ``dashboard/components/widgets/usager/traffic_widget.py``.
"""

from __future__ import annotations

import logging
import re
from typing import cast

import pandas as pd

from src.data.exceptions import DashboardDataError
from src.db.connection import execute_query, execute_scalar, test_connection

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers libellés (Sprint 11+ — nettoyage des identifiants TCL bruts)
# =============================================================================
# Les sources SIRI Lite Grand Lyon exposent des ``line_ref`` au format brut
# ``ActIV:Line::66:SYTRAL`` (parfois suffixés ``_h20`` pour le bucket horaire).
# C'est illisible côté UI. Ce helper standardise l'affichage avec ``;``
# comme séparateur (convention validée par Patrice 2026-06-17).
#
# Exemples :
#   "ActIV:Line::66:SYTRAL"       → "L66"
#   "ActIV:Line::4252:SYTRAL_h16" → "L4252 ; 16h"
#   "ActIV:Line::M_A:SYTRAL"      → "LM_A"
#   "T1" / "M_A" / "C3"          → inchangé (déjà lisibles)
#   None / ""                     → "—"


_LINE_REF_ACTIV_PATTERN = re.compile(r"^ActIV:Line::([^:]+):SYTRAL(?:_h(\d+))?$")


def clean_line_label(line_ref: str | None) -> str:
    """Nettoie un identifiant TCL brut en libellé lisible (Sprint 11+).

    Args:
        line_ref: identifiant TCL brut (ex. ``"ActIV:Line::66:SYTRAL_h20"``)
            ou déjà lisible (ex. ``"T1"``). ``None`` et ``""`` renvoient ``"—"``.

    Returns:
        Libellé formaté. Exemples : ``"L66"``, ``"T1"``, ``"—"``.
        Le suffixe horaire ``_hNN`` est supprimé (bucket interne, pas pertinent
        pour l'affichage utilisateur).
    """
    if not line_ref or not isinstance(line_ref, str):
        return "—"
    ref = line_ref.strip()
    if not ref:
        return "—"

    m = _LINE_REF_ACTIV_PATTERN.match(ref)
    if m:
        return f"L{m.group(1)}"

    return ref


# -----------------------------------------------------------------------------
# Disponibilité DB (cache de healthcheck pour éviter des pings à chaque render)
# -----------------------------------------------------------------------------

_db_available_cache: bool | None = None


def _is_db_available() -> bool:
    """Teste la connexion DB. Cache le résultat pendant la durée du process.

    Returns:
        True si la DB répond, False sinon.
    """
    global _db_available_cache
    if _db_available_cache is None:
        _db_available_cache = test_connection()
        if not _db_available_cache:
            logger.warning(
                "DB non disponible — les widgets afficheront une erreur. "
                "Vérifiez POSTGRES_HOST/POSTGRES_PORT/POSTGRES_PASSWORD dans .env"
            )
    return _db_available_cache


def reset_db_cache() -> None:
    """Reset le cache (utile pour les tests)."""
    global _db_available_cache
    _db_available_cache = None


# -----------------------------------------------------------------------------
# Helpers internes
# -----------------------------------------------------------------------------


def _df_from_query(query: str, params: tuple = ()) -> pd.DataFrame:
    """Exécute une requête et retourne un DataFrame. Vide si erreur/disponible."""
    try:
        rows = execute_query(query, params)
        return pd.DataFrame(rows)
    except Exception as e:  # pragma: no cover — fallback path
        logger.warning("DB query failed, returning empty DataFrame: %s", e)
        return pd.DataFrame()


def _with_fallback(df: pd.DataFrame, fallback_df: pd.DataFrame) -> pd.DataFrame:
    """Si df est vide ET la DB n'est pas dispo, retourne fallback_df (mock)."""
    if df.empty and not _is_db_available():
        return fallback_df
    return df


# =============================================================================
# Traffic (Gold)
# =============================================================================


def get_latest_traffic(limit: int = 100) -> pd.DataFrame:
    """Récupère les N dernières mesures de vitesse depuis Gold.

    Args:
        limit: Nombre de lignes à retourner (défaut 100).

    Returns:
        DataFrame avec colonnes: measurement_time, node_idx, channel_id,
        speed_kmh, importance_code. Vide si DB down (mock fallback).

    EXPLICATION MÉTIER (Analyse) :
    Cette méthode est au cœur de l'affichage temps réel.
    Note sur la politique Zéro Mock (Sprint 8) : auparavant, si la base de données
    PostgreSQL tombait en panne, un "mock" simulait des données aléatoires.
    Ceci a été strictement banni pour la production sur le VPS. Si la base est injoignable,
    la fonction lève une exception (`DashboardDataError`) qui est interceptée par
    Streamlit pour afficher une erreur explicite à l'usager, garantissant ainsi
    la fiabilité de l'information (Fail-Loud).
    """
    # Schema réel : gold.traffic_features_live = computed_at, channel_id, speed_kmh
    # (pas de node_idx ni importance_code dans la table effective)
    query = """
        SELECT computed_at AS measurement_time, channel_id, speed_kmh,
               vitesse_limite_kmh, lag_1, lag_2, lag_3,
               hour_of_day, day_of_week
        FROM gold.traffic_features_live
        WHERE computed_at >= NOW() - INTERVAL '2 hours'
        ORDER BY computed_at DESC
        LIMIT %s
    """
    df = _df_from_query(query, (limit,))
    return df


def get_traffic_timeseries_for_node(node_idx: int, hours: int = 24) -> pd.DataFrame:
    """Sprint 8 — viré le mock fallback. Stub : à implémenter Sprint 9."""
    return pd.DataFrame()


def get_traffic_for_node(node_idx: int, hours: int = 24) -> pd.DataFrame:
    """Série temporelle de vitesse pour un nœud donné.

    Args:
        node_idx: Index du nœud dans gold.dim_spatial_grid_mapping.
        hours: Fenêtre temporelle en heures (défaut 24).

    Returns:
        DataFrame avec colonnes: measurement_time, speed_kmh, speed_lag_1,
        rolling_mean_5min, hour_sin, hour_cos.
    """
    query = """
        SELECT measurement_time, speed_kmh, speed_lag_1, speed_lag_2,
               speed_delta_1, rolling_mean_5min, hour_sin, hour_cos,
               temperature_c, rain_mm, is_vacances
        FROM gold.traffic_features_live
        WHERE node_idx = %s
          AND measurement_time >= NOW() - make_interval(hours => %s)
        ORDER BY measurement_time ASC
    """
    return _df_from_query(query, (node_idx, hours))


def get_traffic_predictions(horizon_minutes: int = 60, limit: int = 200) -> pd.DataFrame:
    """Prédictions de trafic Gold (XGBoost + GNN si dispo).

    Args:
        horizon_minutes: Horizon de prédiction en minutes (5/15/30/60/180/360).
            Mappé vers horizon_h en DB : 5min→0, 30min→0, 60min→1, 180min→3, 360min→6.
        limit: Nombre max de lignes.

    Returns:
        DataFrame avec colonnes nouveau schéma (v0.3.1) ::
            axis_key, horizon_h, calculated_at, speed_pred, etat_pred,
            color, vitesse_limite_kmh, label, model_version, lat, lon.
        Pour rétro-compat, expose aussi ``predicted_speed`` (= speed_pred)
        et ``prediction_timestamp`` (= calculated_at).

    EXPLICATION MÉTIER (Analyse) :
    Le schéma de la table `gold.trafic_predictions` a évolué au Sprint 5 (v0.3.1).
    Plutôt que d'utiliser des minutes, la table partitionne les données en "heures"
    d'horizon (0, 1, 3, 6).
    C'est pourquoi une conversion `horizon_minutes -> horizon_h` est effectuée ici.
    Cette fonction est sollicitée massivement par le Pathfinding (Voiture) pour
    calculer les itinéraires prospectifs.
    """
    # Mapping horizon_minutes -> horizon_h
    # Le schéma gold stocke en heures : 0=H+5min, 1=H+1h, 3=H+3h, 6=H+6h
    horizon_h = _minutes_to_hours(horizon_minutes)
    if horizon_h is None:
        logger.warning("horizon_minutes=%s non mappable vers horizon_h", horizon_minutes)
        return pd.DataFrame()

    query = """
        SELECT axis_key, horizon_h, calculated_at, speed_pred, etat_pred,
               color, vitesse_limite_kmh, label, model_version, lat, lon
        FROM gold.trafic_predictions
        WHERE horizon_h = %s
          AND calculated_at >= NOW() - INTERVAL '2 hours'
        ORDER BY calculated_at DESC
        LIMIT %s
    """
    df = _df_from_query(query, (horizon_h, limit))
    if df.empty:
        return df
    # Colonnes rétro-compat pour les anciens callers
    df["prediction_timestamp"] = df["calculated_at"]
    df["predicted_speed"] = df["speed_pred"]
    return df


def _minutes_to_hours(horizon_minutes: int) -> int | None:
    """Convertit un horizon en minutes vers l'unité heures du schéma gold.

    Mapping convention (cf init-db.sql ligne 1244) ::
        5min  -> 0  (H+5min)
        30min -> 0  (H+30min — vu dans la même fenêtre que H+5min pour 1h-granularité)
        60min -> 1
        180min -> 3
        360min -> 6
    """
    mapping = {5: 0, 15: 0, 30: 0, 60: 1, 180: 3, 360: 6}
    return mapping.get(horizon_minutes)


def get_traffic_bottlenecks(top: int = 20) -> pd.DataFrame:
    """Top N axes avec la vitesse médiane la plus basse sur 1h.

    Sprint VPS-5 — v0.3.1 schema : ``gold.traffic_features_live`` n'a plus
    ``node_idx`` ni ``measurement_time``. La clé d'agrégation est ``channel_id``
    et la colonne temps est ``computed_at``.

    Returns:
        DataFrame: channel_id, avg_speed, min_speed, observations.
    """
    query = """
        SELECT channel_id,
               AVG(speed_kmh) AS avg_speed,
               MIN(speed_kmh) AS min_speed,
               COUNT(*) AS observations
        FROM gold.traffic_features_live
        WHERE computed_at >= NOW() - INTERVAL '1 hour'
          AND speed_kmh IS NOT NULL
        GROUP BY channel_id
        ORDER BY avg_speed ASC
        LIMIT %s
    """
    df = _df_from_query(query, (top,))
    return df


def get_predictions_vs_actuals(limit: int = 1000) -> pd.DataFrame:
    """Backtesting — comparaisons prédictions vs réalité.

    Returns:
        DataFrame: horizon_minutes, model_name, predicted_speed, actual_speed,
        error_kmh, error_pct.
    """
    query = """
        SELECT horizon_minutes, model_name, predicted_speed, actual_speed,
               error_kmh, error_pct
        FROM gold.predictions_vs_actuals
        ORDER BY prediction_id DESC
        LIMIT %s
    """
    df = _df_from_query(query, (limit,))
    return df


# =============================================================================
# Vélov (Gold)
# =============================================================================


def get_velov_stations_geo() -> pd.DataFrame:
    """Stations Vélov avec leur géolocalisation (Silver).

    Returns:
        DataFrame: station_id, station_name, bikes_available, docks_available,
        lat, lng, is_operational.
    """
    # Schema réel silver.velov_clean : num_bikes_available, num_docks_available, lat, lon, is_active
    query = """
        SELECT DISTINCT ON (station_id)
               station_id, station_name,
               num_bikes_available AS bikes_available,
               num_docks_available AS docks_available,
               lat, lon AS lng,
               is_active AS is_operational
        FROM silver.velov_clean
        WHERE measurement_time >= NOW() - INTERVAL '30 minutes'
        ORDER BY station_id, measurement_time DESC
    """
    df = _df_from_query(query)
    return df


def get_nearest_velov_stations(
    lat: float,
    lon: float,
    k: int = 3,
    require_bikes: int = 0,
    require_docks: int = 0,
) -> list[dict]:
    """Top-k stations Vélov les plus proches d'un point GPS.

    Sprint 9+ (2026-06-17) — extrait de l'inline SQL d'Usager_1_Mon_Trajet.py
    (page widget qui contournait la couche data). Wrapper autour de la
    fonction SQL ``referentiel.nearest_velov_stations(lat, lon, k,
    require_bikes, require_docks)``.

    Args:
        lat: latitude WGS84 du point de référence.
        lon: longitude WGS84 du point de référence.
        k: nombre de stations à retourner.
        require_bikes: nb vélos min dispo (0 = peu importe).
        require_docks: nb docks min dispo (0 = peu importe).

    Returns:
        Liste de dicts ``[{station_id, station_name, lat, lon,
        bikes_available, stands_available, distance_m, is_active}, ...]``
        triés par ``distance_m`` croissant. Liste vide si aucune station.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    if not _is_db_available():
        raise DashboardDataError(
            source="referentiel.nearest_velov_stations",
            detail="PostgreSQL indisponible",
        )
    rows = execute_query(
        """
        SELECT station_id, station_name, lat, lon,
               num_bikes_available AS bikes_available,
               num_docks_available AS stands_available,
               distance_m, is_active
        FROM referentiel.nearest_velov_stations(
            %s::double precision, %s::double precision,
            %s, %s, %s
        )
        """,
        (lat, lon, k, require_bikes, require_docks),
    )
    return [
        {
            "station_id": str(r["station_id"]),
            "name": r["station_name"],
            "lat": r["lat"],
            "lon": r["lon"],
            "bikes_available": r["bikes_available"],
            "stands_available": r["stands_available"],
            "distance_m": int(r["distance_m"]),
            "is_active": r["is_active"],
        }
        for r in rows
    ]


def get_velov_predictions(horizon_minutes: int = 30, limit: int = 500) -> pd.DataFrame:
    """Prédictions de disponibilité Vélov.

    Args:
        horizon_minutes: Horizon (30 ou 60).
        limit: Nombre max de lignes.

    Returns:
        DataFrame: prediction_timestamp, target_timestamp, station_id,
        station_id_encoded, predicted_bikes, confidence_low, confidence_high.
    """
    # Schema réel gold.velov_predictions : pas de station_id_encoded ni confidence_low/high.
    # Colonnes : prediction_timestamp, target_timestamp, horizon_minutes, station_id,
    # predicted_bikes, actual_bikes, model_name, model_version
    query = """
        SELECT prediction_timestamp, target_timestamp, horizon_minutes,
               station_id, predicted_bikes, actual_bikes,
               model_name, model_version
        FROM gold.velov_predictions
        WHERE horizon_minutes = %s
        ORDER BY prediction_timestamp DESC
        LIMIT %s
    """
    df = _df_from_query(query, (horizon_minutes, limit))
    # Sprint 8 — viré le fallback mock. Si DB répond vide, retourne df vide.
    return df


def get_velov_features_for_station(station_id_encoded: int, hours: int = 24) -> pd.DataFrame:
    """Features d'une station Vélov (pour debug / audit widget)."""
    query = """
        SELECT measurement_time, station_id, bikes_available,
               bikes_lag_1, bikes_lag_2, bikes_lag_3, rolling_mean_3h,
               hour_sin, hour_cos, temperature_c, rain_mm,
               is_vacances, is_ferie
        FROM gold.velov_features
        WHERE station_id_encoded = %s
          AND measurement_time >= NOW() - make_interval(hours => %s)
        ORDER BY measurement_time ASC
    """
    return _df_from_query(query, (station_id_encoded, hours))


# =============================================================================
# Bus (Gold)
# =============================================================================


def get_bus_delay_segments(line_ref: str | None = None, days: int = 7) -> pd.DataFrame:
    """Retard moyen bus par tronçon/ligne/jour/heure.

    Args:
        line_ref: Filtrer sur une ligne (None = toutes).
        days: Fenêtre en jours (défaut 7).

    Returns:
        DataFrame: date, hour, line_ref, segment_id, avg_delay_seconds,
        n_observations.
    """
    if line_ref:
        query = """
            SELECT date, hour, line_ref, segment_id, avg_delay_seconds, n_observations
            FROM gold.bus_delay_segments
            WHERE line_ref = %s
              AND date >= CURRENT_DATE - %s
            ORDER BY date DESC, hour DESC
        """
        return _df_from_query(query, (line_ref, days))
    query = """
        SELECT date, hour, line_ref, segment_id, avg_delay_seconds, n_observations
        FROM gold.bus_delay_segments
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date DESC, hour DESC
    """
    df = _df_from_query(query, (days,))
    return df


def get_infrastructure_bottlenecks(top: int = 30) -> pd.DataFrame:
    """Bottlenecks infrastructure (croisement bus × trafic).

    Returns:
        DataFrame: segment_id, line_ref, diagnosis, bus_delay_seconds,
        traffic_speed_kmh, traffic_congestion, lat, lng, n_observations.
    """
    query = """
        SELECT id, segment_id, line_ref, diagnosis,
               bus_delay_seconds, traffic_speed_kmh, traffic_congestion,
               lat, lon AS lng, n_observations, computed_at
        FROM gold.infrastructure_bottlenecks
        ORDER BY bus_delay_seconds DESC NULLS LAST
        LIMIT %s
    """
    df = _df_from_query(query, (top,))
    return df


def get_bottlenecks_summary(top: int = 50) -> pd.DataFrame:
    """Résumé des bottlenecks infrastructure pour les pages Élu (rank + zone + voyageurs).

    Sprint 9+ (2026-06-17) — Fonction manquante qui crashait
    ``load_bottlenecks_summary`` / ``load_bottlenecks_top``. Lit la table réelle
    ``gold.infrastructure_bottlenecks`` (v0.3.1) et expose un alias
    rétro-compatible pour ``load_bottlenecks_top`` (qui consomme
    ``bottleneck_id``, ``road_name``, ``voyageurs_jour``).

    Mapping schéma v0.3.1 → contrat widget Élu ::
        * ``id``               → ``bottleneck_id``
        * ``segment_id``       → ``road_name`` (identifiant segment routier)
        * ``line_ref``         → ``line_ref`` (ligne TCL impactée)
        * ``bus_delay_seconds``→ ``avg_bus_delay_s`` (s)
        * ``traffic_speed_kmh``→ ``avg_traffic_speed_kmh`` (km/h)
        * ``n_observations``   → ``voyageurs_jour`` proxy (n_obs agrégées,
                                 utilisé comme dénominateur d'impact par Élu)
        * ``lat``, ``lon``     → géoloc
        * ``diagnosis``        → étiquette diagnostic

    Args:
        top: nombre max de lignes retournées (défaut 50).

    Returns:
        DataFrame: bottleneck_id, road_name, line_ref, diagnosis,
        avg_bus_delay_s, avg_traffic_speed_kmh, n_observations,
        voyageurs_jour, lat, lng, computed_at.
        Vide si DB indisponible (la couche data_loader remonte alors
        ``DashboardDataError`` via ``_require_db_or_raise``).
    """
    query = """
        SELECT id            AS bottleneck_id,
               segment_id    AS road_name,
               line_ref,
               diagnosis,
               bus_delay_seconds AS avg_bus_delay_s,
               traffic_speed_kmh AS avg_traffic_speed_kmh,
               traffic_congestion,
               n_observations,
               n_observations AS voyageurs_jour,
               lat, lon AS lng,
               computed_at
        FROM gold.infrastructure_bottlenecks
        ORDER BY bus_delay_seconds DESC NULLS LAST
        LIMIT %s
    """
    df = _df_from_query(query, (top,))
    if not df.empty and "line_ref" in df.columns:
        # Sprint 11+ — colonne line_label pour affichage lisible
        # ("L66 ; 20h" au lieu de "ActIV:Line::66:SYTRAL_h20").
        df["line_label"] = df["line_ref"].apply(clean_line_label)
        # Le road_name (segment_id brut) peut aussi être nettoyé quand c'est
        # un identifiant ActIV:Line:: (cas des bottlenecks routiers).
        if "road_name" in df.columns:
            df["road_label"] = df["road_name"].apply(clean_line_label)
    return df


# =============================================================================
# Spatial (Gold)
# =============================================================================


def get_spatial_mapping() -> pd.DataFrame:
    """Mapping nœuds GNN ↔ channel_id (capteurs).

    Returns:
        DataFrame: node_idx, channel_id, matrix_i, matrix_j, h3_id, lat, lng.
    """
    query = """
        SELECT node_idx, properties_twgid AS channel_id, matrix_i, matrix_j, h3_id,
               lat, lon AS lng
        FROM gold.dim_spatial_grid_mapping
        ORDER BY node_idx
    """
    df = _df_from_query(query)
    return df


def get_gnn_adjacency() -> pd.DataFrame:
    """Arêtes du graphe GNN (K=2 grid_disk, bidirectionnel)."""
    query = """
        SELECT node_u, node_v, is_connected, distance_m
        FROM gold.dim_gnn_adjacency
        WHERE is_connected = TRUE
    """
    df = _df_from_query(query)
    return df


# =============================================================================
# RGPD
# =============================================================================


def get_rgpd_audit_log(limit: int = 100) -> pd.DataFrame:
    """Logs d'audit RGPD (registre Article 30).

    Returns:
        DataFrame: event_time, actor, action, resource_type, resource_id,
        ip_address, user_agent.
    """
    query = """
        SELECT event_time, actor, action, resource_type, resource_id,
               ip_address::text AS ip_address, user_agent
        FROM rgpd.audit_log
        ORDER BY event_time DESC
        LIMIT %s
    """
    df = _df_from_query(query, (limit,))
    return df


def get_rgpd_consents_summary() -> pd.DataFrame:
    """Résumé des consents par type (analytics, tracking, marketing, all)."""
    query = """
        SELECT consent_type,
               SUM(CASE WHEN granted THEN 1 ELSE 0 END) AS granted_count,
               SUM(CASE WHEN NOT granted THEN 1 ELSE 0 END) AS denied_count,
               COUNT(*) AS total
        FROM rgpd.user_consents
        WHERE granted_at >= NOW() - INTERVAL '90 days'
        GROUP BY consent_type
        ORDER BY consent_type
    """
    df = _df_from_query(query)
    return df


def get_rgpd_data_subject_requests(limit: int = 50) -> pd.DataFrame:
    """DSR (Demandes Subjects Request) — Article 15/17/20."""
    query = """
        SELECT request_id, user_identifier, request_type, status,
               requested_at, completed_at, notes
        FROM rgpd.data_subject_requests
        ORDER BY requested_at DESC
        LIMIT %s
    """
    df = _df_from_query(query, (limit,))
    return df


def get_rgpd_purge_history(limit: int = 50) -> pd.DataFrame:
    """Historique des purges RGPD."""
    query = """
        SELECT schema_name, table_name, rows_purged, retention_days, purged_at
        FROM rgpd.purge_log
        ORDER BY purged_at DESC
        LIMIT %s
    """
    df = _df_from_query(query, (limit,))
    return df


# =============================================================================
# Monitoring / Health
# =============================================================================


def get_data_freshness(schema: str = "bronze", table: str = "trafic_boucles") -> pd.Timestamp | None:
    """Retourne le timestamp de la dernière ligne d'une table.

    Args:
        schema: 'bronze' | 'silver' | 'gold'.
        table: Nom de la table (sans préfixe schéma).

    Returns:
        Timestamp de la dernière mesure, ou None si DB down / table vide.
    """
    # Whitelist pour éviter SQL injection sur schema/table (psycopg2 %s ne protège pas les identifiants)
    allowed = {
        ("bronze", "trafic_boucles"),
        ("bronze", "velov"),
        ("bronze", "tcl_vehicles"),
        ("bronze", "meteo"),
        ("bronze", "air_quality"),
        ("bronze", "chantiers"),
        ("silver", "trafic_boucles_clean"),
        ("silver", "velov_clean"),
        ("silver", "tcl_vehicles_clean"),
        ("silver", "meteo_hourly"),
        ("silver", "chantiers_actifs"),
        ("gold", "traffic_features_live"),
        ("gold", "velov_features"),
        ("gold", "velov_predictions"),
        ("gold", "trafic_predictions"),
    }
    if (schema, table) not in allowed:
        logger.warning("Schema/table (%s.%s) not whitelisted in db_query", schema, table)
        return None

    query = f"SELECT MAX(fetched_at) FROM {schema}.{table}"  # nosec B608 (safe: identifiants whitelistés)
    try:
        result = execute_scalar(query)
        return pd.Timestamp(result) if result else None
    except Exception as e:  # pragma: no cover
        logger.warning("Freshness check failed for %s.%s: %s", schema, table, e)
        return None


def get_bronze_source_counts(hours: int = 1) -> pd.DataFrame:
    """Compte de lignes ingérées par source Bronze sur les N dernières heures.

    Returns:
        DataFrame: source, n_rows, last_fetch.
    """
    sources = [
        ("trafic_boucles", "Grand Lyon boucles (pvotrafic)"),
        ("velov", "Vélo'v GBFS"),
        ("tcl_vehicles", "TCL SIRI Lite"),
        ("meteo", "Open-Meteo weather"),
        ("air_quality", "Open-Meteo air quality"),
        ("chantiers", "Grand Lyon chantiers"),
    ]
    # Sprint 8 — viré le fallback mock. Si DB indispo, le caller doit catch.
    if not _is_db_available():
        from src.data.exceptions import DashboardDataError

        raise DashboardDataError(source="bronze_source_counts", detail="PostgreSQL indisponible")

    rows = []
    for table, label in sources:
        # Une requête par table (pas de UNION sur des tables hétérogènes)
        try:
            count = execute_scalar(
                f"SELECT COUNT(*) FROM bronze.{table} WHERE fetched_at >= NOW() - make_interval(hours => %s)",  # nosec B608
                (hours,),
            )
            last = execute_scalar(f"SELECT MAX(fetched_at) FROM bronze.{table}")  # nosec B608
            rows.append(
                {
                    "source": label,
                    "table": f"bronze.{table}",
                    "n_rows": cast(int, count or 0),
                    "last_fetch": pd.Timestamp(last) if last else None,
                }
            )
        except Exception as e:  # pragma: no cover
            logger.warning("Bronze count failed for %s: %s", table, e)
            rows.append({"source": label, "table": f"bronze.{table}", "n_rows": 0, "last_fetch": None})
    return pd.DataFrame(rows)


# =============================================================================
# Utilitaires de rendu
# =============================================================================


def safe_dataframe(df: pd.DataFrame, empty_message: str = "Aucune donnée disponible.") -> pd.DataFrame:
    """Helper UI — retourne le DataFrame, ou un DataFrame placeholder si vide.

    Usage dans un widget Streamlit::

        df = get_latest_traffic(limit=50)
        df = safe_dataframe(df, "Aucune mesure trafic récente — vérifiez le pipeline.")
        st.dataframe(df)
    """
    if df.empty:
        return pd.DataFrame({"info": [empty_message]})
    return df


# =============================================================================
# Météo, alertes, segments, buses, kpis, amenagements
# Sprint 8 — Sprint 6 widget migration complète
# =============================================================================


def get_weather_hourly(hours: int = 24) -> pd.DataFrame:
    """Météo horaire (open-meteo Silver) — pour le widget météo."""
    query = """
        SELECT
            measurement_time,
            temperature_c,
            rain_mm,
            wind_speed_10m AS wind_kmh,
            humidity AS humidity_pct,
            weather_code::text AS condition_label
        FROM silver.meteo_hourly
        WHERE measurement_time >= NOW() - make_interval(hours => %s)
          AND measurement_time <= NOW() + INTERVAL '1 hour'
        ORDER BY measurement_time DESC
    """
    return _df_from_query(query, (hours,))


def get_recent_alerts(hours: int = 24, limit: int = 50) -> pd.DataFrame:
    """Alertes récentes (predictions + events).

    Source: agrégat de plusieurs tables (gold.trafic_predictions, chantiers,
    etc.). Pour l'instant mock — sera remplacé par une vue matérialisée
    ``gold.v_recent_alerts`` quand le pipeline tournera.
    """
    query = """
        SELECT
            chantier_id AS alert_id,
            COALESCE(date_debut::timestamp with time zone, fetched_at) AS alert_time,
            'Warning' AS severity,
            'Toutes' AS line_ref,
            titre AS title,
            description,
            'Déviation potentielle' AS action
        FROM silver.chantiers_actifs
        WHERE is_active = true
        ORDER BY alert_time DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_segments(limit: int = 200) -> pd.DataFrame:
    """Liste des segments routiers (top 200 par importance)."""
    query = """
        SELECT
            segment_id,
            channel_id,
            importance_code,
            longueur_m,
            ST_Y(ST_StartPoint(geom_wgs84)) AS lat_start,
            ST_X(ST_StartPoint(geom_wgs84)) AS lng_start,
            ST_Y(ST_EndPoint(geom_wgs84)) AS lat_end,
            ST_X(ST_EndPoint(geom_wgs84)) AS lng_end
        FROM silver.trafic_segments_clean
        ORDER BY importance_code DESC, segment_id
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_correlation_matrix(limit: int = 50) -> pd.DataFrame:
    """Matrice de corrélation entre features Gold (pour heatmap)."""
    query = """
        SELECT feature_x, feature_y, correlation, p_value, n_samples
        FROM gold.fact_correlation_matrix
        ORDER BY abs(correlation) DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_buses_positions(limit: int = 200) -> pd.DataFrame:
    """Positions temps réel des bus TCL.

    Fenêtre 30 min (6 cycles SIRI @5min) pour tolérer les gaps d'ingestion.
    DISTINCT ON (journey_ref) garde la position la plus récente par véhicule.
    """
    query = """
        SELECT DISTINCT ON (journey_ref)
            journey_ref AS vehicle_ref,
            line_ref,
            lat,
            lon AS lng,
            0 AS bearing,
            delay_seconds,
            measurement_time AS recorded_at
        FROM silver.tcl_vehicles_clean
        WHERE measurement_time >= NOW() - INTERVAL '30 minutes'
          AND lat IS NOT NULL
          AND lon IS NOT NULL
        ORDER BY journey_ref, measurement_time DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_kpis_12_months() -> pd.DataFrame:
    """KPIs ville sur 12 mois (vue matérialisée pour le persona Élu)."""
    query = """
        SELECT
            kpi_key,
            month,
            value,
            delta_pct,
            target_value
        FROM gold.mv_kpis_12_months
        ORDER BY kpi_key, month
    """
    return _df_from_query(query)


def get_amenagements_passes(limit: int = 50) -> pd.DataFrame:
    """Aménagements passés (historique pour le persona Élu)."""
    query = """
        SELECT
            amenagement_id,
            name,
            zone,
            type,
            cout_eur,
            date_debut,
            date_fin,
            impact_part_modale_tc,
            impact_congestion_pct,
            impact_co2_tonnes_an,
            description
        FROM gold.amenagements_history
        ORDER BY date_fin DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


# =============================================================================
# Grille multimodale (Sprint 15+, 2026-06-19) — Axe 1 du SPEC_OPTIMISATION_INTERDEPENDANCES
# =============================================================================
# Vue matérialisée gold.mv_multimodal_grid (migration 17) :
#   Fusionne gold.traffic_features_live + gold.tcl_vehicle_realtime +
#   silver.velov_clean + silver.meteo_hourly sur une grille spatiale 0.01°.
#   Refresh toutes les 10 min par le DAG transform_silver_to_gold.
# =============================================================================


def get_multimodal_grid(limit: int = 5000) -> pd.DataFrame:
    """Grille multimodale temps réel (Sprint 15+, 2026-06-19).

    Vue matérialisée ``gold.mv_multimodal_grid`` (migration 17). Chaque
    ligne = 1 cellule 0.01° (~1 km) Lyon avec un agrégat trafic + TCL +
    Vélov + météo, un score 0-10 (haut = saturé) et un diagnostic dominant.

    Args:
        limit: nb max de cellules retournées (défaut 5000 — couvre tout
            Lyon intra-muros + banlieue proche).

    Returns:
        DataFrame avec colonnes : ``lat, lon, avg_speed_kmh, pct_congestion,
        n_sensors, avg_delay_sec, pct_delayed, n_vehicles, bikes_available,
        docks_available, n_stations, temperature_c, rain_mm,
        score_multimodal, diagnosis, computed_at``. ``diagnosis`` ∈
        {ok, road_congested, transit_delayed, saturated, velov_scarce}.

        Retourne un DataFrame vide si DB indispo (pattern cohérent avec
        ``_df_from_query``). Le fail loud via ``DashboardDataError`` est
        porté par ``data_loader.load_multimodal_grid``.
    """
    query = """
        SELECT lat, lon,
               avg_speed_kmh, pct_congestion, n_sensors,
               avg_delay_sec, pct_delayed, n_vehicles,
               bikes_available, docks_available, n_stations,
               temperature_c, rain_mm,
               score_multimodal, diagnosis, computed_at
        FROM gold.mv_multimodal_grid
        ORDER BY score_multimodal DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_multimodal_grid_diagnosis_counts() -> pd.DataFrame:
    """Distribution des diagnostics dominants (Sprint 15+, 2026-06-19).

    Pour le bandeau KPI du widget ``multimodal_heatmap`` : compte les
    cellules par diagnostic.

    Returns:
        DataFrame ``{diagnosis, n_cells, avg_score, pct_cells}`` trié par
        ``n_cells`` DESC. Vide si DB indispo (fail loud via data_loader).
    """
    query = """
        SELECT diagnosis,
               COUNT(*)::int                   AS n_cells,
               ROUND(AVG(score_multimodal)::numeric, 2) AS avg_score,
               ROUND((100.0 * COUNT(*) / SUM(COUNT(*)) OVER ())::numeric, 1)
                                                AS pct_cells
        FROM gold.mv_multimodal_grid
        GROUP BY diagnosis
        ORDER BY n_cells DESC
    """
    return _df_from_query(query)


# =============================================================================
# Bus × trafic spatialisé (Sprint 15+, Axe 3 — migration 18)
# =============================================================================


def get_bus_traffic_spatial(
    line_ref: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Corrélation bus × trafic spatialisée (Sprint 15+, 2026-06-19).

    Vue matérialisée ``gold.mv_bus_traffic_spatial`` (migration 18). Chaque
    ligne = 1 triplet (line_ref, heure, zone 0.001°) avec le retard bus ET
    la vitesse trafic dans la MÊME zone géographique (~100 m).

    Args:
        line_ref: filtre optionnel sur une ligne TCL.
        limit: nb max de lignes retournées.

    Returns:
        DataFrame avec colonnes : ``line_ref, hour, lat, lon,
        bus_delay_sec, bus_observations, bus_delayed_count,
        traffic_speed_kmh, traffic_sensors, diagnosis,
        traffic_congestion, computed_at``.
    """
    if line_ref:
        query = """
            SELECT line_ref, hour, lat, lon,
                   bus_delay_sec, bus_observations, bus_delayed_count,
                   traffic_speed_kmh, traffic_sensors,
                   diagnosis, traffic_congestion, computed_at
            FROM gold.mv_bus_traffic_spatial
            WHERE line_ref = %s
            ORDER BY bus_delay_sec DESC
            LIMIT %s
        """
        return _df_from_query(query, (line_ref, limit))
    query = """
        SELECT line_ref, hour, lat, lon,
               bus_delay_sec, bus_observations, bus_delayed_count,
               traffic_speed_kmh, traffic_sensors,
               diagnosis, traffic_congestion, computed_at
        FROM gold.mv_bus_traffic_spatial
        ORDER BY bus_delay_sec DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_bus_traffic_spatial_diagnosis_counts(
    line_ref: str | None = None,
) -> pd.DataFrame:
    """Distribution des diagnostics spatialisés (Sprint 15+, 2026-06-19).

    Pour le bandeau KPI du widget ``bus_traffic_spatial`` : compte les
    zones par diagnostic.

    Returns:
        DataFrame ``{diagnosis, n_zones, avg_delay, avg_speed, pct_zones}``.
    """
    if line_ref:
        query = """
            SELECT diagnosis,
                   COUNT(*)::int AS n_zones,
                   ROUND(AVG(bus_delay_sec)::numeric, 1) AS avg_delay,
                   ROUND(AVG(traffic_speed_kmh)::numeric, 1) AS avg_speed,
                   ROUND((100.0 * COUNT(*) / SUM(COUNT(*)) OVER ())::numeric, 1)
                       AS pct_zones
            FROM gold.mv_bus_traffic_spatial
            WHERE line_ref = %s
            GROUP BY diagnosis
            ORDER BY n_zones DESC
        """
        return _df_from_query(query, (line_ref,))
    query = """
        SELECT diagnosis,
               COUNT(*)::int AS n_zones,
               ROUND(AVG(bus_delay_sec)::numeric, 1) AS avg_delay,
               ROUND(AVG(traffic_speed_kmh)::numeric, 1) AS avg_speed,
               ROUND((100.0 * COUNT(*) / SUM(COUNT(*)) OVER ())::numeric, 1)
                   AS pct_zones
        FROM gold.mv_bus_traffic_spatial
        GROUP BY diagnosis
        ORDER BY n_zones DESC
    """
    return _df_from_query(query)


# =============================================================================
# Score santé réseau (Sprint 15+, Axe 5 — migration 019)
# =============================================================================


def get_network_health_score() -> pd.DataFrame:
    """Score de santé réseau 0-100 temps réel (Sprint 15+, Axe 5).

    Appelle ``gold.fn_network_health_score()`` qui agrège trafic + TCL +
    Vélov + météo avec redistribution des poids si source indisponible.

    Returns:
        DataFrame 1 ligne : ``score, pct_congestion, pct_tcl_delayed,
        pct_velov_empty, meteo_penalty, traffic_available, tcl_available,
        velov_available, meteo_available, diagnosis, computed_at``.
    """
    query = "SELECT * FROM gold.fn_network_health_score()"
    return _df_from_query(query)


# =============================================================================
# Référentiel lieux × transports × calendrier (Sprint VPS-6, 2026-06-11)
# =============================================================================
# Ces 3 tables sont créées par :
#   scripts/sql/create_referentiel_lieux.sql
#   scripts/sql/create_referentiel_transports.sql
#   scripts/sql/create_lieux_calendrier.sql
# Le seed des cadences est fait par scripts/seed_lieux_calendrier.py.
# =============================================================================


def get_lieux_lyon_names(active_only: bool = True) -> list[str]:
    """Liste des noms de lieux Lyon (pour autocomplete).

    Returns:
        Liste de strings ``['Part-Dieu, Lyon', 'Perrache, Lyon', ...]``.
    """
    query = (
        "SELECT name FROM referentiel.lieux_lyon WHERE is_active = TRUE ORDER BY name"
        if active_only
        else "SELECT name FROM referentiel.lieux_lyon ORDER BY name"
    )
    rows = execute_query(query)
    return [r["name"] for r in rows]


def get_lieux_lyon_with_coords(active_only: bool = True) -> list[dict]:
    """Lieux Lyon avec coordonnées GPS complètes.

    Format identique à l'ancien mock ``LYON_ADDRESSES`` : ``{name, lon, lat, type}``.

    Returns:
        Liste de dicts ``[{name, lon, lat, type}, ...]``.
    """
    query = (
        "SELECT name, lon, lat, type FROM referentiel.lieux_lyon WHERE is_active = TRUE ORDER BY name"
        if active_only
        else "SELECT name, lon, lat, type FROM referentiel.lieux_lyon ORDER BY name"
    )
    rows = execute_query(query)
    return [dict(r) for r in rows]


def get_lieux_transports(lieu_id: int | None = None) -> list[dict]:
    """Dessertes TCL par lieu (référentiel N-N lieu ↔ ligne).

    Args:
        lieu_id: si fourni, filtre sur ce lieu. Sinon, tous les lieux actifs.

    Returns:
        Liste de dicts ``{lieu_id, lieu_name, line_ref, line_mode, stop_name,
        distance_m, rank}`` triés par ``(lieu_name, rank)``.
    """
    if lieu_id is not None:
        query = """
            SELECT lt.lieu_id, ll.name AS lieu_name, lt.line_ref, lt.line_mode,
                   lt.stop_name, lt.distance_m, lt.rank
            FROM referentiel.lieux_transports lt
            JOIN referentiel.lieux_lyon ll ON ll.lieu_id = lt.lieu_id
            WHERE lt.is_active = TRUE AND lt.lieu_id = %s
            ORDER BY ll.name, lt.rank
        """
        params: tuple = (lieu_id,)
    else:
        query = """
            SELECT lt.lieu_id, ll.name AS lieu_name, lt.line_ref, lt.line_mode,
                   lt.stop_name, lt.distance_m, lt.rank
            FROM referentiel.lieux_transports lt
            JOIN referentiel.lieux_lyon ll ON ll.lieu_id = lt.lieu_id
            WHERE lt.is_active = TRUE
            ORDER BY ll.name, lt.rank
        """
        params = ()
    rows = execute_query(query, params)
    return [dict(r) for r in rows]


def get_cadence_for_line(
    line_ref: str,
    day_type: str | None = None,
    time_bucket: str | None = None,
) -> list[dict]:
    """Cadence observée pour une ligne TCL (référentiel lieux_calendrier).

    Args:
        line_ref: identifiant TCL (ex. ``'M_A'``). NOT NULL.
        day_type: filtre optionnel sur le type de jour.
        time_bucket: filtre optionnel sur la tranche horaire (ex. ``'08:00'``).

    Returns:
        Liste de dicts ``{line_ref, day_type, time_bucket,
        cadence_min_per_vehicle, n_observations, confidence}``.

    Raises:
        ValueError: si ``line_ref`` est vide.
    """
    if not line_ref:
        raise ValueError("line_ref is required")

    clauses = ["line_ref = %s"]
    params: list = [line_ref]
    if day_type is not None:
        clauses.append("day_type = %s")
        params.append(day_type)
    if time_bucket is not None:
        clauses.append("time_bucket = %s")
        params.append(time_bucket)

    where_clause = " AND ".join(clauses)
    query = (
        "SELECT line_ref, day_type, time_bucket, cadence_min_per_vehicle, "
        "n_observations, confidence, computed_at "
        "FROM referentiel.lieux_calendrier "
        "WHERE " + where_clause + " "  # nosec B608
        "ORDER BY CASE day_type "
        "WHEN 'weekday' THEN 1 "
        "WHEN 'saturday' THEN 2 "
        "WHEN 'sunday_holiday' THEN 3 "
        "WHEN 'vacation' THEN 4 "
        "ELSE 5 END, time_bucket"
    )
    rows = execute_query(query, tuple(params))
    return [dict(r) for r in rows]


def get_transit_options(origin_lieu_id: int, dest_lieu_id: int) -> list[dict]:
    """Lignes TC desservant simultanément origin ET destination (intersection N-N).

    Sprint 14 (2026-06-19) — jointure référentiel.lieux_transports sur lui-même
    par ``line_ref``. Si une ligne dessert les 2 lieux, on a un trajet direct
    possible. Tri par somme des ranks (rank 1 = arrêt le plus proche du lieu)
    pour prioriser les lignes les plus accessibles à pied.

    Args:
        origin_lieu_id: PK de ``referentiel.lieux_lyon`` (origine).
        dest_lieu_id: PK de ``referentiel.lieux_lyon`` (destination).

    Returns:
        Liste de dicts ``{line_ref, line_mode, stop_origin, distance_origin_m,
        rank_origin, stop_dest, distance_dest_m, rank_dest}``. Vide si aucune
        ligne commune (→ fallback correspondance via hub par
        ``plan_transit_trip``).
    """
    query = """
        SELECT lt_o.line_ref, lt_o.line_mode,
               lt_o.stop_name AS stop_origin,
               lt_o.distance_m AS distance_origin_m,
               lt_o.rank AS rank_origin,
               lt_d.stop_name AS stop_dest,
               lt_d.distance_m AS distance_dest_m,
               lt_d.rank AS rank_dest
        FROM referentiel.lieux_transports lt_o
        JOIN referentiel.lieux_transports lt_d
          ON lt_o.line_ref = lt_d.line_ref
         AND lt_o.is_active = TRUE
         AND lt_d.is_active = TRUE
        WHERE lt_o.lieu_id = %s
          AND lt_d.lieu_id = %s
        ORDER BY (lt_o.rank + lt_d.rank), lt_o.line_ref
    """
    rows = execute_query(query, (origin_lieu_id, dest_lieu_id))
    return [dict(r) for r in rows]


# =============================================================================
# TomTom + vue unifiée trafic (Sprint VPS-6, 2026-06-11)
# =============================================================================
# Table bronze.tomtom_traffic : snapshots TomTom Flow (cf. scripts/sql/create_tomtom_traffic.sql)
# Vue gold.v_tomtom_traffic_live : dernier snapshot par tuile (24h)
# Vue gold.v_traffic_combined : fusion Gold live > Gold pred > TomTom
# =============================================================================


def get_traffic_combined(limit: int = 5000) -> pd.DataFrame:
    """Vue unifiée trafic temps réel (Gold live + Gold pred + TomTom).

    Sprint VPS-6 — permet au dashboard carte d'afficher du trafic
    partout à Lyon, y compris hors couverture des boucles Grand Lyon.

    Args:
        limit: nb max de lignes retournées (défaut 5000).

    Returns:
        DataFrame avec colonnes ``channel_id, lat, lon, speed_kmh,
        computed_at, source, confidence``. ``source`` ∈ {gold_live,
        gold_pred, tomtom}.
    """
    query = """
        SELECT channel_id, lat, lon, speed_kmh, computed_at, source, confidence
        FROM gold.v_traffic_combined
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_tomtom_latest(limit: int = 100) -> pd.DataFrame:
    """Dernier snapshot TomTom par tuile (vue ``gold.v_tomtom_traffic_live``).

    Returns:
        DataFrame avec colonnes ``tile_key, lat, lon, current_speed_kmh,
        free_flow_speed_kmh, ratio, confidence, etat, color, fetched_at``.
    """
    query = """
        SELECT tile_key, lat, lon, current_speed_kmh, free_flow_speed_kmh,
               ratio, confidence, current_travel_time_s, free_flow_travel_time_s,
               etat, color, fetched_at
        FROM gold.v_tomtom_traffic_live
        ORDER BY tile_key
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_tomtom_coherence(limit: int = 500) -> pd.DataFrame:
    """Cohérence TomTom ↔ capteurs Grand Lyon (Sprint 13+, 2026-06-18).

    Vue ``gold.v_coherence_tomtom_vs_grandlyon`` : pour chaque tuile
    TomTom récente, trouve les capteurs Grand Lyon à moins de 200 m
    et calcule le delta de vitesse.

    Args:
        limit: nb max de paires (tile_key, channel_id) retournées.

    Returns:
        DataFrame avec colonnes ``tile_key, channel_id, site_name,
        distance_m, tomtom_speed_kmh, gl_speed_kmh, delta_kmh,
        ratio_diff, tomtom_confidence, fetched_at, status``
        (``status`` ∈ {ok, minor_drift, drift, no_data}).
    """
    query = """
        SELECT tile_key, channel_id, site_name, distance_m,
               tomtom_speed_kmh, gl_speed_kmh, delta_kmh, ratio_diff,
               tomtom_confidence, fetched_at, status
        FROM gold.v_coherence_tomtom_vs_grandlyon
        ORDER BY ABS(delta_kmh) DESC NULLS LAST
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


def get_tomtom_gl_drift(limit: int = 200) -> pd.DataFrame:
    """Capteurs Grand Lyon suspectés HS (Sprint 13+, 2026-06-18).

    Vue ``gold.v_tomtom_gl_drift`` : capteurs dont >= 60% des paires
    TomTom proches sont en drift (delta > 20 km/h) sur 24h. Utile
    pour le détecteur de capteurs HS du widget Pro_TCL.

    Args:
        limit: nb max de capteurs retournés (triés par n_drift DESC).

    Returns:
        DataFrame avec colonnes ``channel_id, site_name, n_pairs,
        n_ok, n_minor_drift, n_drift, drift_ratio, avg_abs_delta_kmh,
        max_abs_delta_kmh, sensor_health``
        (``sensor_health`` ∈ {healthy, watch, suspect, no_data}).
    """
    query = """
        SELECT channel_id, site_name, n_pairs, n_ok, n_minor_drift,
               n_drift, drift_ratio, avg_abs_delta_kmh,
               max_abs_delta_kmh, sensor_health
        FROM gold.v_tomtom_gl_drift
        ORDER BY n_drift DESC, n_pairs DESC
        LIMIT %s
    """
    return _df_from_query(query, (limit,))


# =============================================================================
# Lieux × Vélov proches (Sprint VPS-6, 2026-06-11)
# =============================================================================
# Vue referentiel.v_lieux_velov_proches : 1 lieu × top 3 bornes Vélov
# Vue referentiel.v_lieux_velov_plus_proche : 1 lieu × 1 borne la + proche
# Vue materialisée créée par scripts/sql/create_lieux_velov_proches.sql
# =============================================================================


def get_lieux_with_velov(k: int = 3, only_operational: bool = True) -> list[dict]:
    """Renvoie la liste des lieux du référentiel avec leurs K bornes Vélov
    les plus proches (par distance haversine).

    Args:
        k: nombre de bornes Vélov par lieu (défaut 3, max 10).
        only_operational: si True, filtre les bornes Vélov inactives.

    Returns:
        Liste de dicts par lieu :
        ``{lieu_id, lieu_name, lieu_lon, lieu_lat, lieu_type,
        bornes: [{station_id, velov_name, velov_lon, velov_lat,
                  num_bikes_available, num_docks_available, distance_m}]}``
    """
    query = """
        SELECT
            lieu_id, lieu_name, lieu_lon, lieu_lat, lieu_type,
            station_id, velov_name, velov_lon, velov_lat,
            num_bikes_available, num_docks_available, distance_m
        FROM referentiel.v_lieux_velov_proches
        WHERE rank <= %s
    """
    if only_operational:
        query += " AND num_bikes_available >= 0"
    query += " ORDER BY lieu_id, distance_m"
    rows = execute_query(query, (k,))
    # Regroupement par lieu
    out: dict[int, dict] = {}
    for r in rows:
        lid = r["lieu_id"]
        if lid not in out:
            out[lid] = {
                "lieu_id": lid,
                "lieu_name": r["lieu_name"],
                "lieu_lon": r["lieu_lon"],
                "lieu_lat": r["lieu_lat"],
                "lieu_type": r["lieu_type"],
                "bornes": [],
            }
        out[lid]["bornes"].append(
            {
                "station_id": r["station_id"],
                "velov_name": r["velov_name"],
                "velov_lon": r["velov_lon"],
                "velov_lat": r["velov_lat"],
                "num_bikes_available": r["num_bikes_available"],
                "num_docks_available": r["num_docks_available"],
                "distance_m": float(r["distance_m"]),
            }
        )
    return list(out.values())


def get_velov_proche_for_lieu(lieu_id: int) -> dict | None:
    """Renvoie la borne Vélov la plus proche d'un lieu (top 1).

    Args:
        lieu_id: identifiant du lieu (referentiel.lieux_lyon.lieu_id).

    Returns:
        Dict {station_id, velov_name, velov_lon, velov_lat,
        num_bikes_available, num_docks_available, distance_m} ou None.
    """
    query = """
        SELECT station_id, velov_name, velov_lon, velov_lat,
               num_bikes_available, num_docks_available, distance_m
        FROM referentiel.v_lieux_velov_plus_proche
        WHERE lieu_id = %s
    """
    rows = execute_query(query, (lieu_id,))
    return dict(rows[0]) if rows else None


# =============================================================================
# Vélov smart routing + maillage (Sprint VPS-6, 2026-06-11)
# =============================================================================
# Vues referentiel.v_lieux_velov_smart et v_velov_neighbors
# Cf. scripts/sql/create_velov_maillage.sql
# =============================================================================


def get_smart_velov_for_lieu(lieu_id: int, k: int = 3) -> list[dict]:
    """Top K bornes Vélov scorées pour un lieu, avec statut dispo.

    Args:
        lieu_id: identifiant du lieu (referentiel.lieux_lyon.lieu_id).
        k: nombre de bornes à retourner (max 3 dans la vue, défaut 3).

    Returns:
        Liste de dicts triées par rank (1 = meilleur choix) :
        ``{station_id, velov_name, velov_lon, velov_lat,
        num_bikes_available, num_docks_available, distance_m,
        score, status, rank}`` où status ∈ {VIDE, PLEINE, FAIBLE, OK}.
    """
    query = """
        SELECT station_id, velov_name, velov_lon, velov_lat,
               num_bikes_available, num_docks_available,
               distance_m, score, status, rank
        FROM referentiel.v_lieux_velov_smart
        WHERE lieu_id = %s AND rank <= %s
        ORDER BY rank
    """
    rows = execute_query(query, (lieu_id, k))
    return [dict(r) for r in rows]


def get_smart_velov_for_lieux(lieu_ids: list[int], k: int = 3) -> dict[int, list[dict]]:
    """Top K bornes Vélov scorées pour plusieurs lieux (1 query).

    Args:
        lieu_ids: liste de lieu_id.
        k: nb bornes par lieu (max 3).

    Returns:
        Dict {lieu_id: [bornes...]} avec bornes triées par rank.
    """
    if not lieu_ids:
        return {}
    query = """
        SELECT lieu_id, station_id, velov_name, velov_lon, velov_lat,
               num_bikes_available, num_docks_available,
               distance_m, score, status, rank
        FROM referentiel.v_lieux_velov_smart
        WHERE lieu_id = ANY(%s) AND rank <= %s
        ORDER BY lieu_id, rank
    """
    rows = execute_query(query, (lieu_ids, k))
    out: dict[int, list[dict]] = {lid: [] for lid in lieu_ids}
    for r in rows:
        out[r["lieu_id"]].append(dict(r))
    return out


def get_velov_neighbors(station_id: str, k: int = 5) -> list[dict]:
    """Top K voisines d'une borne Vélov (distance < 200m).

    Args:
        station_id: identifiant de la borne (silver.velov_clean.station_id).
        k: nb de voisines à retourner (défaut 5).

    Returns:
        Liste de dicts triées par distance ASC :
        ``{station_id_b, name_b, bikes_b, docks_b, lon_b, lat_b, distance_m}``.
    """
    query = """
        SELECT station_id_b, name_b, bikes_b, docks_b, lon_b, lat_b, distance_m
        FROM referentiel.v_velov_neighbors
        WHERE station_id_a = %s
        ORDER BY distance_m
        LIMIT %s
    """
    rows = execute_query(query, (station_id, k))
    return [dict(r) for r in rows]


def get_velov_neighbors_batch(station_ids: list[str], k: int = 3) -> dict[str, list[dict]]:
    """Voisines de plusieurs bornes (1 query).

    Args:
        station_ids: liste de station_id.
        k: nb voisines par borne.

    Returns:
        Dict {station_id: [voisines...]} avec voisines triées par distance.
    """
    if not station_ids:
        return {}
    query = """
        SELECT station_id_a, station_id_b, name_b, bikes_b, docks_b,
               lon_b, lat_b, distance_m
        FROM referentiel.v_velov_neighbors
        WHERE station_id_a = ANY(%s)
        ORDER BY station_id_a, distance_m
    """
    rows = execute_query(query, (station_ids,))
    out: dict[str, list[dict]] = {sid: [] for sid in station_ids}
    for r in rows:
        d = dict(r)
        if len(out[r["station_id_a"]]) < k:
            out[r["station_id_a"]].append(d)
    return out


# =============================================================================
# Sprint 7 (post-VPS-6) — Vues matérialisées KPIs TCL + Heatmap OTP
# =============================================================================
# Vues gold.mv_line_kpis_live + gold.mv_otp_heatmap
# Cf. scripts/sql/create_mv_line_kpis_otp.sql
# Débloque Pro_2_Heatmap_OTP.py et Pro_4_Simulateur.py
# =============================================================================


def get_line_kpis(line_ids: list[str] | None = None) -> dict:
    """KPIs par ligne TCL depuis la vue matérialisée mv_line_kpis_live.

    Sprint P2-quater (2026-06-15) — Format de retour aligné sur le
    contrat des widgets (cf. ``widgets/pro_tcl/line_kpis.py`` et
    ``widgets/pro_tcl/line_comparison.py``)::

        {
            "<line_id>": {
                "otp_pct": float,
                "avg_delay_min": float,        # retard en minutes
                "frequency_min": float,         # intervalle entre véhicules (min)
                "load_pct": float,             # taux d'occupation (0..100)
                "trend": str,                  # "up" | "down" | "stable"
                "trend_delta": float,
            },
            ...
        }

    Notes :
    * La vue ``gold.mv_line_kpis_live`` n'est pas encore matérialisée
      en prod. Si elle n'existe pas, on retourne ``{}`` (les widgets
      afficheront "Aucun KPI ligne disponible" plutôt que de crasher).
    * Conversion legacy schema prod :
      - ``retard_moyen_s`` (DB, secondes) → ``avg_delay_min`` (min) : ÷ 60
      - ``freq_vehicules_par_h`` (DB, veh/h) → ``frequency_min`` (min/veh) :
        60 / fvh, arrondi à 1 décimale
      - ``charge_pct`` (DB) → ``load_pct`` (widget) : simple rename
      - Colonnes legacy conservées en plus (rétro-compatibilité mock).
    """
    if not _is_db_available():
        return {}
    params: tuple = ()
    if line_ids:
        query = """
            SELECT line_ref, otp_pct, retard_moyen_s, freq_vehicules_par_h,
                   charge_pct, mode, otp_status, n_obs_total, n_days
            FROM gold.mv_line_kpis_live
            WHERE line_ref = ANY(%s)
            ORDER BY line_ref
        """
        params = (line_ids,)
    else:
        query = """
            SELECT line_ref, otp_pct, retard_moyen_s, freq_vehicules_par_h,
                   charge_pct, mode, otp_status, n_obs_total, n_days
            FROM gold.mv_line_kpis_live
            ORDER BY line_ref
        """
    try:
        rows = execute_query(query, params)
    except Exception as e:
        # Vue absente ou query invalide — fail-soft
        logger.warning(
            "get_line_kpis: query gold.mv_line_kpis_live a échoué (%s) — "
            "fallback dict vide. Vue à matérialiser Sprint 10+.",
            e,
        )
        return {}
    if not rows:
        return {}

    out: dict = {}
    for r in rows:
        retard_s = float(r["retard_moyen_s"]) if r["retard_moyen_s"] is not None else 0.0
        fvh = float(r["freq_vehicules_par_h"]) if r["freq_vehicules_par_h"] is not None else 0.0
        charge = float(r["charge_pct"]) if r["charge_pct"] is not None else 0.0
        line_ref_raw = r["line_ref"]
        out[line_ref_raw] = {
            "line_label": clean_line_label(line_ref_raw),  # Sprint 11+ affichage lisible
            "otp_pct": float(r["otp_pct"]) if r["otp_pct"] is not None else 0.0,
            "avg_delay_min": round(retard_s / 60, 1),
            "frequency_min": round(60 / fvh, 1) if fvh > 0 else 0.0,
            "load_pct": charge,
            "trend": "stable",  # Pas dans la MV — déduit côté front si besoin
            "trend_delta": 0.0,
            # Legacy fields (rétro-compatibilité mock / autres callers)
            "retard_moyen_s": retard_s,
            "freq_vehicules_par_h": fvh,
            "charge_pct": charge,
            "mode": r.get("mode"),
            "otp_status": r.get("otp_status"),
            "n_obs_total": int(r["n_obs_total"]) if r.get("n_obs_total") is not None else 0,
            "n_days": int(r["n_days"]) if r.get("n_days") is not None else 0,
        }
    return out


def get_otp_heatmap(days: int = 7) -> pd.DataFrame:
    """Heatmap OTP (ligne × date × heure) sur les N derniers jours.

    Args:
        days: fenêtre temporelle en jours (défaut 7).

    Returns:
        DataFrame avec colonnes ``line_id, line_label, date, hour,
        otp_pct, avg_delay_s, n_obs`` (rétro-compatible avec le mock aplati
        ``OTP_GRID`` → ``[line_id, date, hour, otp_pct]``). ``line_label``
        est ajoutée par Sprint 11+ pour affichage lisible (``"L66"`` au
        lieu de ``"ActIV:Line::66:SYTRAL"``).
    """
    query = """
        SELECT line_id, date, hour, otp_pct, avg_delay_s, n_obs
        FROM gold.mv_otp_heatmap
        WHERE date >= CURRENT_DATE - %s
        ORDER BY line_id, date, hour
    """
    df = _df_from_query(query, (days,))
    if not df.empty and "line_id" in df.columns:
        df["line_label"] = df["line_id"].apply(clean_line_label)
    return df


def get_latest_drift_report() -> dict | None:
    """Retourne le dernier rapport de drift persisté par build_xgb_training_set.

    Sprint 10+ (2026-06-12) — Lecture live de gold.model_drift_reports
    (schéma v0.3.1). Remplace le mock ``drift_status`` du widget
    Pro_7_Model_Monitoring.

    Returns:
        Dict avec ``dataset_drift``, ``drift_share``, ``n_ref``,
        ``n_current``, ``ref_from``, ``ref_to``, ``current_from``,
        ``current_to``, ``report`` (JSONB), ``computed_at``. None si
        la table est vide.
    """
    rows = execute_query("""
        SELECT
            computed_at,
            dataset_drift,
            drift_share,
            n_ref,
            n_current,
            ref_from,
            ref_to,
            current_from,
            current_to,
            report
        FROM gold.model_drift_reports
        ORDER BY computed_at DESC
        LIMIT 1
    """)
    if not rows:
        return None
    r = rows[0]
    # Conversion des timestamps en string ISO (Streamlit-friendly)
    for k in ("computed_at", "ref_from", "ref_to", "current_from", "current_to"):
        if r.get(k) is not None and not isinstance(r[k], str):
            r[k] = str(r[k])
    return r


# =============================================================================
# Sprint 16 Axe A — TomTom Niveau 2 : Backtest Engine
# =============================================================================
# Validation XGBoost vs oracle externe (TomTom Traffic Flow = GPS flottes).
# Vue matérialisée gold.mv_xgb_vs_tomtom (migration 020) + vue simple
# gold.v_xgb_accuracy_summary. Refresh */30 min par le DAG
# refresh_xgb_vs_tomtom. Voir docs/SPEC_SPRINT_16.md §A.1-A.3.


def get_xgb_vs_tomtom(hours: int = 24, limit: int = 500) -> pd.DataFrame:
    """Paires (prédiction XGBoost H+1h, observation TomTom) des dernières N heures.

    Sert au widget Pro_7_Model_Monitoring::backtest_dashboard pour le scatter
    Plotly XGBoost vs TomTom + table top 10 pires prédictions.

    Args:
        hours: fenêtre temporelle en heures (défaut 24h).
        limit: nombre max de paires retournées (défaut 500, tri par date desc).

    Returns:
        DataFrame avec colonnes : axis_key, calculated_at, xgb_speed_kmh,
        tomtom_speed_kmh, error_abs_kmh, error_pct, accuracy_band,
        tomtom_confidence, model_version, etat_pred.
    """
    query = """
        SELECT axis_key, calculated_at, xgb_speed_kmh, tomtom_speed_kmh,
               error_abs_kmh, error_pct, accuracy_band,
               tomtom_confidence, model_version, etat_pred
        FROM gold.mv_xgb_vs_tomtom
        WHERE calculated_at > NOW() - (INTERVAL '1 hour' * %s)
        ORDER BY calculated_at DESC
        LIMIT %s
    """
    return _df_from_query(query, (hours, limit))


def get_xgb_accuracy_summary(hours: int = 168) -> pd.DataFrame:
    """KPIs agrégés par heure (MAE, MAPE, P90, distribution accuracy).

    Sert au widget backtest_dashboard pour la courbe MAE temporelle et le
    pie distribution accuracy_band. 168h = 7 jours par défaut.

    Args:
        hours: fenêtre temporelle en heures (défaut 168 = 7 jours).

    Returns:
        DataFrame avec colonnes : hour_bucket, n_pairs, mae_kmh,
        median_error_kmh, p90_error_kmh, mape_pct, n_accurate, n_acceptable,
        n_poor, avg_tomtom_confidence.
    """
    query = """
        SELECT hour_bucket, n_pairs, mae_kmh, median_error_kmh,
               p90_error_kmh, mape_pct, n_accurate, n_acceptable, n_poor,
               avg_tomtom_confidence
        FROM gold.v_xgb_accuracy_summary
        WHERE hour_bucket > NOW() - (INTERVAL '1 hour' * %s)
        ORDER BY hour_bucket DESC
    """
    return _df_from_query(query, (hours,))


# =============================================================================
# Sprint 16 Axe B — Data Quality : Monitoring multi-source
# =============================================================================
# Vues gold.v_source_health (migration 021) + gold.v_data_completeness.
# Remplacent les 6 checks mono-table par 2 vues agrégées + check_all_sources().
# Voir docs/SPEC_SPRINT_16.md §B.1-B.3.


def get_source_health() -> pd.DataFrame:
    """Santé par source (fraîcheur + score 0-100 + statut).

    Sert au widget Pro_6_Pipeline_Mgmt::source_health_monitor (jauge + grille)
    et au badge Elu_1_Synthese::data_quality_badge.

    Returns:
        DataFrame avec colonnes : source, last_update, age_minutes,
        records_1h, expected_interval_min, health_score, status.
        Trié par health_score ASC (les plus malades en premier).
    """
    query = """
        SELECT source, last_update, age_minutes, records_1h,
               expected_interval_min, health_score, status
        FROM gold.v_source_health
        ORDER BY health_score ASC
    """
    return _df_from_query(query, ())


def get_data_completeness() -> pd.DataFrame:
    """Complétude colonnes critiques par table Silver (24h glissantes).

    Returns:
        DataFrame avec colonnes : source, total_rows, speed_pct, geo_pct, id_pct.
    """
    query = """
        SELECT source, total_rows, speed_pct, geo_pct, id_pct
        FROM gold.v_data_completeness
    """
    return _df_from_query(query, ())


# Sprint 17 Axe 7 — Météo comme variable d'interaction (migration 022)
# Vue matérialisée gold.mv_meteo_impact : impact de la météo (5 bandes) sur
# 3 modes (trafic, TCL, Vélov), avec delta vs baseline "beau temps".
# Voir docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §8.


def get_meteo_impact() -> pd.DataFrame:
    """Impact météo par bande × mode (Sprint 17 Axe 7, migration 022).

    Vue matérialisée ``gold.mv_meteo_impact`` qui agrège 30 jours
    d'historique pour comparer l'effet de 5 conditions météo (fair,
    light_rain, heavy_rain, frost, heatwave) sur 3 modes de transport.

    Sert au widget ``meteo_impact`` (Pro_3_Correlation → section
    Interdépendances multimodales) pour le tableau comparatif.

    Returns:
        DataFrame avec colonnes : meteo_band, avg_speed_kmh, std_speed_kmh,
        traffic_n_obs, traffic_delta_kmh_vs_fair, avg_delay_seconds,
        tcl_n_obs, tcl_delay_delta_sec_vs_fair, avg_bikes_available,
        velov_n_obs, velov_delta_bikes_vs_fair, computed_at.

        Trié par meteo_band (ordre logique : fair → light_rain → heavy_rain
        → frost → heatwave).

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou si la vue
            matérialisée n'existe pas (migration 022 non appliquée).
    """
    query = """
        SELECT meteo_band,
               avg_speed_kmh,
               std_speed_kmh,
               traffic_n_obs,
               traffic_delta_kmh_vs_fair,
               avg_delay_seconds,
               tcl_n_obs,
               tcl_delay_delta_sec_vs_fair,
               avg_bikes_available,
               velov_n_obs,
               velov_delta_bikes_vs_fair,
               computed_at
        FROM gold.mv_meteo_impact
        ORDER BY
            CASE meteo_band
                WHEN 'fair'        THEN 1
                WHEN 'light_rain'  THEN 2
                WHEN 'heavy_rain'  THEN 3
                WHEN 'frost'       THEN 4
                WHEN 'heatwave'    THEN 5
            END
    """
    return _df_from_query(query, ())


# Sprint 17 Axe 4 — Vélov ↔ TC report modal (migration 023)
# Vue matérialisée gold.mv_velov_transit_coupling : z-score vélos dispos
# par station Vélov < 300m d'une zone TC. anomaly_detected = TRUE si
# z_score < -2 (vidange anormale → report modal probable).
# Voir docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §5.


def get_velov_transit_coupling(anomalies_only: bool = False) -> pd.DataFrame:
    """Couplage Vélov ↔ TC (Sprint 17 Axe 4, migration 023).

    Vue matérialisée ``gold.mv_velov_transit_coupling`` : pour chaque
    station Vélov située à < 300m d'une zone où circule une ligne TC,
    calcule le z-score (= combien d'écarts-types en dessous de la
    moyenne horaire 7j) du nombre de vélos disponibles.

    Sert au widget ``modal_shift_alert`` (Pro_3_Correlation → section
    Interdépendances multimodales) pour détecter les incidents TC qui
    font basculer les usagers vers le Vélov.

    Args:
        anomalies_only: si True, filtre ``anomaly_detected = TRUE``
            (z_score < -2). Utilisé pour le KPI counter + le tableau
            "stations anormalement vides".

    Returns:
        DataFrame avec colonnes : station_id, station_name, transit_line,
        transit_n_vehicles, station_lat, station_lon, distance_to_line_m,
        bikes_now, baseline_avg_bikes, baseline_std_bikes, baseline_n_obs,
        hour_of_day, z_score, anomaly_detected, computed_at.

        Trié par anomaly_detected DESC puis z_score ASC (les anomalies
        les plus extrêmes en premier).

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou si la vue
            matérialisée n'existe pas (migration 023 non appliquée).
    """
    base_query = """
        SELECT station_id,
               station_name,
               transit_line,
               transit_n_vehicles,
               station_lat,
               station_lon,
               distance_to_line_m,
               bikes_now,
               baseline_avg_bikes,
               baseline_std_bikes,
               baseline_n_obs,
               hour_of_day,
               z_score,
               anomaly_detected,
               computed_at
        FROM gold.mv_velov_transit_coupling
    """
    if anomalies_only:
        query = base_query + " WHERE anomaly_detected = TRUE" + " ORDER BY z_score ASC NULLS LAST"
    else:
        query = base_query + " ORDER BY anomaly_detected DESC, z_score ASC NULLS LAST"
    return _df_from_query(query, ())


def get_velov_transit_coupling_summary() -> pd.DataFrame:
    """Résumé par ligne TC : nombre de stations en alerte par ligne.

    Si plusieurs stations Vélov proches d'une même ligne TC sont en
    alarme simultanée → probable incident sur cette ligne (panne métro,
    tram interrompu, etc.) qui fait basculer les usagers vers le Vélov.

    Sert au widget ``modal_shift_alert`` pour le bandeau KPI "lignes TC
    en alerte" + le tri par "score de report modal".

    Returns:
        DataFrame avec colonnes : transit_line, n_stations_total,
        n_stations_anomaly, n_vehicles, alert_level (critical si ≥ 3
        stations en alarme, warning si ≥ 1, ok sinon).

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    query = """
        SELECT
            transit_line,
            COUNT(*)::int                                AS n_stations_total,
            SUM(CASE WHEN anomaly_detected THEN 1 ELSE 0 END)::int
                                                        AS n_stations_anomaly,
            MAX(transit_n_vehicles)::int                 AS n_vehicles,
            CASE
                WHEN SUM(CASE WHEN anomaly_detected THEN 1 ELSE 0 END) >= 3
                    THEN 'critical'
                WHEN SUM(CASE WHEN anomaly_detected THEN 1 ELSE 0 END) >= 1
                    THEN 'warning'
                ELSE 'ok'
            END                                          AS alert_level,
            MIN(z_score)::numeric(6,2)                   AS min_z_score
        FROM gold.mv_velov_transit_coupling
        GROUP BY transit_line
        ORDER BY n_stations_anomaly DESC, min_z_score ASC NULLS LAST
    """
    return _df_from_query(query, ())
