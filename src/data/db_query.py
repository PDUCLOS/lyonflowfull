"""Couche d'accès aux données Gold/Silver pour les widgets dashboard.

Ce module encapsule les requêtes SQL paramétrées vers les tables Gold/Silver
de l'architecture Medallion, et fournit une API typée simple pour les widgets
Streamlit. Toutes les fonctions:

* Utilisent du SQL paramétré (psycopg2 %s, JAMAIS de f-string)
* Retournent des `pandas.DataFrame` (pratique pour Streamlit/Plotly)
* Ont un fallback gracieux vers `src.data.mock` si la DB est down
* Sont testables hors ligne (les tests monkeypatchent ``_is_db_available``)

Pattern d'utilisation dans un widget::

    from src.data.db_query import get_latest_traffic, get_traffic_aggregates

    df = get_latest_traffic(limit=50)  # DataFrame ou mock fallback
    st.dataframe(df)

Pour les widgets, voir le pattern dans ``dashboard/components/widgets/usager/traffic_widget.py``.
"""

from __future__ import annotations

import logging
import time

import pandas as pd

from src.db.connection import execute_query, execute_scalar, test_connection

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Disponibilité DB (cache de healthcheck pour éviter des pings à chaque render)
# -----------------------------------------------------------------------------

_db_available_cache: bool | None = None
_db_available_cache_ts: float = 0.0
_DB_CACHE_TTL_SECONDS = 60.0  # H2 (Sprint 11+) — évite un cache "False" éternel


def _is_db_available() -> bool:
    """Teste la connexion DB. Cache le résultat pendant la durée du process
    avec un TTL court (60s) — H2 (Sprint 11+) : si la DB revient dans la même
    vie de process, on la redécouvre sans avoir à redémarrer.

    Returns:
        True si la DB répond, False sinon.
    """
    global _db_available_cache, _db_available_cache_ts
    now = time.monotonic()
    if _db_available_cache is None or (now - _db_available_cache_ts) > _DB_CACHE_TTL_SECONDS:
        _db_available_cache = test_connection()
        _db_available_cache_ts = now
        if not _db_available_cache:
            logger.warning(
                "DB non disponible — les widgets soulèveront DashboardDataError. "
                "Vérifiez POSTGRES_HOST/POSTGRES_PORT/POSTGRES_PASSWORD dans .env"
            )
    return _db_available_cache


def reset_db_cache() -> None:
    """Reset le cache (utile pour les tests)."""
    global _db_available_cache, _db_available_cache_ts
    _db_available_cache = None
    _db_available_cache_ts = 0.0


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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_TRAFFIC_FEATURES

        return pd.DataFrame(MOCK_TRAFFIC_FEATURES[:limit])
    return df


def get_traffic_timeseries_for_node(node_idx: int, hours: int = 24) -> pd.DataFrame:
    """Time series trafic pour un nœud (mock fallback)."""
    # Pas de query SQL ici — c'est un alias utilisé par les widgets démo.
    from src.data.mock.usager import MOCK_TRAFFIC_TIMESERIES

    return pd.DataFrame(MOCK_TRAFFIC_TIMESERIES)


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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_TRAFFIC_BOTTLENECKS

        return pd.DataFrame(MOCK_TRAFFIC_BOTTLENECKS[:top])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_PREDICTIONS_VS_ACTUALS

        return pd.DataFrame(MOCK_PREDICTIONS_VS_ACTUALS[:limit])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_VELOV_STATIONS_GEO

        return pd.DataFrame(MOCK_VELOV_STATIONS_GEO)
    return df


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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_TRAFIC_PREDICTIONS

        return pd.DataFrame([p for p in MOCK_TRAFIC_PREDICTIONS if p["horizon_minutes"] == horizon_minutes][:limit])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_BUS_DELAYS

        return pd.DataFrame(MOCK_BUS_DELAYS)
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_INFRA_BOTTLENECKS

        return pd.DataFrame(MOCK_INFRA_BOTTLENECKS[:top])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_SPATIAL_MAPPING

        return pd.DataFrame(MOCK_SPATIAL_MAPPING)
    return df


def get_gnn_adjacency() -> pd.DataFrame:
    """Arêtes du graphe GNN (K=2 grid_disk, bidirectionnel)."""
    query = """
        SELECT node_u, node_v, is_connected, distance_m
        FROM gold.dim_gnn_adjacency
        WHERE is_connected = TRUE
    """
    df = _df_from_query(query)
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_GNN_ADJACENCY

        return pd.DataFrame(MOCK_GNN_ADJACENCY)
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_RGPD_AUDIT

        return pd.DataFrame(MOCK_RGPD_AUDIT[:limit])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_RGPD_CONSENTS_SUMMARY

        return pd.DataFrame(MOCK_RGPD_CONSENTS_SUMMARY)
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_RGPD_DSR

        return pd.DataFrame(MOCK_RGPD_DSR[:limit])
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
    if df.empty and not _is_db_available():
        from src.data.mock.usager import MOCK_RGPD_PURGE

        return pd.DataFrame(MOCK_RGPD_PURGE[:limit])
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

    # C2 (Sprint 11+) — psycopg2.sql.Identifier quote proprement les identifiants
    # même après whitelist. Defense in depth (ne jamais faire confiance à
    # f-string même si input est validée).
    from psycopg2 import sql as pg_sql
    query = pg_sql.SQL("SELECT MAX(fetched_at) FROM {}.{}").format(
        pg_sql.Identifier(schema),
        pg_sql.Identifier(table),
    )
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
    if not _is_db_available():
        from src.data.mock.usager import MOCK_BRONZE_COUNTS

        return pd.DataFrame(MOCK_BRONZE_COUNTS)

    rows = []
    from psycopg2 import sql as pg_sql
    for table, label in sources:
        # Une requête par table (pas de UNION sur des tables hétérogènes)
        try:
            count = execute_scalar(
                pg_sql.SQL("SELECT COUNT(*) FROM bronze.{} WHERE fetched_at >= NOW() - make_interval(hours => %s)").format(
                    pg_sql.Identifier(table)
                ),
                (hours,),
            )
            last = execute_scalar(
                pg_sql.SQL("SELECT MAX(fetched_at) FROM bronze.{}").format(
                    pg_sql.Identifier(table)
                )
            )
            rows.append(
                {
                    "source": label,
                    "table": f"bronze.{table}",
                    "n_rows": int(count or 0),
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
    return _df_from_query(query, (hours, limit))


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
    """Positions temps réel des bus TCL."""
    query = """
        SELECT
            journey_ref AS vehicle_ref,
            line_ref,
            lat,
            lon AS lng,
            0 AS bearing,
            delay_seconds,
            measurement_time AS recorded_at
        FROM silver.tcl_vehicles_clean
        WHERE measurement_time >= NOW() - INTERVAL '5 minutes'
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


# -----------------------------------------------------------------------------
# Sprint 10+ — fonctions manquantes (stubs pour CI / compatibilité)
# TODO (Sprint 10+): remplacer par vrai SQL + MV gold.mv_line_kpis_live
# -----------------------------------------------------------------------------


def get_line_kpis(line_ids: list[str] | None = None) -> dict:
    """KPIs par ligne TCL (OTP, retards, fréquence).

    En l'absence de DB, retourne un stub vide pour ne pas bloquer les tests.
    TODO Sprint 10+: câbler sur gold.mv_line_kpis_live.
    """
    if not _is_db_available():
        return {"lines": [], "timestamp": None}
    query = """
        SELECT line_id, line_name, otp_pct, avg_delay_min,
               frequency_pph, occupancy_pct, date
        FROM gold.mv_line_kpis_live
        WHERE (%s IS NULL OR line_id = ANY(%s))
        ORDER BY line_id
        LIMIT 100
    """
    params = (line_ids, line_ids)
    try:
        df = _df_from_query(query, params)
    except Exception:
        return {"lines": [], "timestamp": None}
    if df.empty:
        return {"lines": [], "timestamp": None}
    return {
        "lines": df.to_dict("records"),
        "timestamp": df["date"].max().isoformat() if "date" in df.columns else None,
    }


def get_otp_heatmap() -> pd.DataFrame:
    """Heatmap OTP (ligne × heure).

    TODO Sprint 10+: câbler sur gold.mv_otp_heatmap.
    """
    if not _is_db_available():
        return pd.DataFrame(columns=["line_id", "date", "hour", "otp_pct"])
    query = """
        SELECT line_id, date, hour, otp_pct
        FROM gold.mv_otp_heatmap
        LIMIT 5000
    """
    try:
        return _df_from_query(query)
    except Exception:
        return pd.DataFrame(columns=["line_id", "date", "hour", "otp_pct"])


def get_bottlenecks_summary() -> pd.DataFrame:
    """Résumé agrégé des bottlenecks d'infrastructure.

    TODO Sprint 10+: câbler sur gold.infrastructure_bottlenecks.
    """
    if not _is_db_available():
        return pd.DataFrame(
            columns=[
                "zone",
                "line_id",
                "voyageurs_jour",
                "gain_min",
                "cout_M_euros",
                "roi_mois",
                "priorite",
            ]
        )
    query = """
        SELECT zone, line_id, voyageurs_jour, gain_min,
               cout_M_euros, roi_mois, priorite
        FROM gold.infrastructure_bottlenecks
        ORDER BY priorite DESC, gain_min DESC
        LIMIT 50
    """
    try:
        return _df_from_query(query)
    except Exception:
        return pd.DataFrame(
            columns=[
                "zone",
                "line_id",
                "voyageurs_jour",
                "gain_min",
                "cout_M_euros",
                "roi_mois",
                "priorite",
            ]
        )


def get_lieux_transports(lieu_id: int | None = None) -> list[dict]:
    """Référentiel lieux × transports (TCL, Vélov, parking).

    TODO Sprint 10+: câbler sur gold.referentiel_lieux.
    """
    if not _is_db_available():
        return []
    query = """
        SELECT lieu_id, nom, lat, lon, type_lieu,
               lines_tcl, has_velov, has_parking, distance_gare
        FROM gold.referentiel_lieux
        WHERE (%s IS NULL OR lieu_id = %s)
        LIMIT 100
    """
    try:
        df = _df_from_query(query, (lieu_id, lieu_id))
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []


def get_smart_velov_for_lieu(lieu_id: int, k: int = 3) -> list[dict]:
    """Vélov stations proches d'un lieu (pour routing multimodal).

    TODO Sprint 10+: câbler sur gold.velov_stations_near_lieu.
    """
    if not _is_db_available():
        return []
    query = """
        SELECT station_id, station_name,
               ST_Distance(geom::geography, ST_MakePoint(%s, %s)::geography) AS distance_m,
               num_bikes_available AS bikes_available
        FROM silver.velov_clean
        WHERE measurement_time >= NOW() - INTERVAL '30 minutes'
        ORDER BY distance_m ASC
        LIMIT %s
    """
    try:
        df = _df_from_query(query, (lieu_id, lieu_id, k))
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []
