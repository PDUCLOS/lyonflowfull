"""Transforms Silver → Gold (features ML-ready).

Set-based SQL (zéro N+1) :
- traffic_features_live : window LAG/AVG + LATERAL meteo + JOIN spatial mapping
- velov_features : window LAG + LATERAL meteo + label encoding via DENSE_RANK
- bus_delay_segments : aggregation par tronçon/ligne/heure

Enrichissement vacances/fériés depuis bronze.calendrier_scolaire /
bronze.jours_feries via fonctions PL/pgSQL `_is_vacances(date)` /
`_is_ferie(date)`. Les fonctions sont créées à chaque run (CREATE OR
REPLACE idempotent) — pas de migration Alembic.
"""

from __future__ import annotations

import logging

from src.db import raw_connection

logger = logging.getLogger(__name__)


def transform_silver_to_gold(target: str = "all", dry_run: bool = False) -> dict[str, int]:
    """Transform Silver → Gold pour un ou tous les modèles.

    Args:
        target: 'traffic' | 'velov' | 'bus_delay' | 'tcl_realtime'
            | 'bottleneck' | 'multimodal_grid'
            | 'bus_traffic_spatial' | 'all'
        dry_run: log uniquement.

    Returns:
        {target: n_rows_upserted_or_refreshed}
    """
    if dry_run:
        logger.info("[DRY-RUN] Silver → Gold %s skipped", target)
        return {}

    results: dict[str, int] = {}
    if target in ("traffic", "all"):
        results["traffic"] = _build_traffic_features()
    if target in ("velov", "all"):
        results["velov"] = _build_velov_features()
    if target in ("bus_delay", "all"):
        results["bus_delay"] = _build_bus_delay_segments()
    if target in ("tcl_realtime", "all"):
        results["tcl_realtime"] = _build_tcl_realtime()
    if target in ("bottleneck", "all"):
        results["bottleneck"] = _build_infrastructure_bottlenecks()
    if target in ("multimodal_grid", "all"):
        results["multimodal_grid"] = _refresh_multimodal_grid()
    if target in ("bus_traffic_spatial", "all"):
        results["bus_traffic_spatial"] = _refresh_bus_traffic_spatial()
    return results


# -----------------------------------------------------------------------------
# Helpers PL/pgSQL — calendaire (CREATE OR REPLACE idempotent)
# -----------------------------------------------------------------------------
_HELPER_FN_SQL = """
-- Jour férié : true si la date (raw_data.date ou colonne date_ferie) matche.
-- raw_data format par ligne : {"date": "2024-01-01", "nom": "1er janvier"}
CREATE OR REPLACE FUNCTION _is_ferie(d date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM bronze.jours_feries jf
        WHERE jf.date_ferie = d
           OR (jf.raw_data IS NOT NULL
               AND (jf.raw_data->>'date')::date = d)
    );
$$;

-- Vacances scolaires : true si la date est dans une période [start_date, end_date]
-- pour la Zone A. Schéma direct (colonnes) : start_date, end_date, zone.
-- raw_data fallback (si schéma partiel) : {"records": [{"fields": {...}}]}
CREATE OR REPLACE FUNCTION _is_vacances(d date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM bronze.calendrier_scolaire cs
        WHERE cs.start_date <= d
          AND cs.end_date   >= d
          AND cs.zone ILIKE 'A'
    )
    OR EXISTS (
        SELECT 1
        FROM bronze.calendrier_scolaire cs,
             LATERAL jsonb_array_elements(
                 CASE WHEN jsonb_typeof(cs.raw_data->'records') = 'array'
                      THEN cs.raw_data->'records'
                      ELSE '[]'::jsonb END
             ) AS rec
        WHERE cs.start_date IS NULL
          AND (rec->'fields'->>'start_date')::date <= d
          AND (rec->'fields'->>'end_date')::date   >= d
          AND COALESCE(rec->'fields'->>'zones', '') ILIKE '%zone a%'
    );
$$;
"""


def _ensure_helpers(cur) -> None:
    """Crée/refresh fonctions `_is_ferie` et `_is_vacances` (idempotent).

    Sprint 23 (2026-06-26) - protection contre 'tuple concurrently updated'.
    Le CREATE OR REPLACE FUNCTION concurrent de plusieurs tasks Airflow
    (LocalExecutor) générait une InternalError_ pg_catalog. pg_advisory_xact_lock
    sérialise les créations : un seul task à la fois crée les helpers, les
    autres attendent. Lock relâché en fin de transaction (ROLLBACK/COMMIT).
    """
    cur.execute("SELECT pg_advisory_xact_lock(7890001)")
    cur.execute(_HELPER_FN_SQL)


# -----------------------------------------------------------------------------
# SQL set-based — un INSERT par domaine
# -----------------------------------------------------------------------------

_TRAFFIC_SQL = """
WITH recent AS (
    SELECT
        s.measurement_time,
        s.channel_id,
        s.vitesse_kmh,
        s.vitesse_limite_kmh
    FROM silver.trafic_boucles_clean s
    WHERE s.measurement_time > NOW() - INTERVAL '2 hours'
      AND s.vitesse_kmh IS NOT NULL
),
windowed AS (
    SELECT
        r.measurement_time,
        r.channel_id,
        r.vitesse_kmh,
        r.vitesse_limite_kmh,
        LAG(r.vitesse_kmh, 1) OVER w AS lag_1,
        LAG(r.vitesse_kmh, 2) OVER w AS lag_2,
        LAG(r.vitesse_kmh, 3) OVER w AS lag_3,
        AVG(r.vitesse_kmh) OVER (
            PARTITION BY r.channel_id
            ORDER BY r.measurement_time
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ) AS rolling_mean_3
    FROM recent r
    WINDOW w AS (PARTITION BY r.channel_id ORDER BY r.measurement_time)
),
fresh AS (
    SELECT * FROM windowed
    WHERE measurement_time > NOW() - INTERVAL '15 minutes'
)
INSERT INTO gold.traffic_features_live (
    channel_id, fetched_at, computed_at,
    speed_kmh, vitesse_limite_kmh,
    lag_1, lag_2, lag_3, delta_current, delta_1, rolling_mean_3,
    hour_of_day, day_of_week, is_weekend,
    sin_hour, cos_hour, sin_dow, cos_dow, channel_hash,
    temperature_2m, precipitation, rain, is_raining,
    visibility, wind_speed_10m, weather_code,
    lat, lon, importance_code, x_2154, y_2154,
    is_vacances, is_ferie
)
SELECT
    f.channel_id,
    f.measurement_time                      AS fetched_at,
    NOW()                                   AS computed_at,
    f.vitesse_kmh,
    f.vitesse_limite_kmh,
    f.lag_1,
    f.lag_2,
    f.lag_3,
    f.vitesse_kmh - f.lag_1                 AS delta_current,
    f.vitesse_kmh - COALESCE(f.lag_1, f.vitesse_kmh) AS delta_1,
    f.rolling_mean_3,
    EXTRACT(HOUR FROM f.measurement_time)::smallint AS hour_of_day,
    EXTRACT(DOW  FROM f.measurement_time)::smallint AS day_of_week,
    CASE WHEN EXTRACT(DOW FROM f.measurement_time) IN (0, 6)
         THEN 1 ELSE 0 END                 AS is_weekend,
    SIN(2 * PI() * EXTRACT(HOUR FROM f.measurement_time) / 24.0) AS sin_hour,
    COS(2 * PI() * EXTRACT(HOUR FROM f.measurement_time) / 24.0) AS cos_hour,
    SIN(2 * PI() * EXTRACT(DOW  FROM f.measurement_time) /  7.0) AS sin_dow,
    COS(2 * PI() * EXTRACT(DOW  FROM f.measurement_time) /  7.0) AS cos_dow,
    -- channel_hash : hash stable du channel_id → permet de linker aux node_idx
    -- sans JOIN sur dim_spatial_grid_mapping (qui n'est pas peuplée par channel_id)
    ('x' || substr(md5(f.channel_id), 1, 8))::bit(32)::int::double precision
        / 2147483647.0                      AS channel_hash,
    met.temperature_c                        AS temperature_2m,
    met.rain_mm                              AS precipitation,
    met.rain_mm                              AS rain,
    CASE WHEN met.rain_mm > 0
         THEN 1 ELSE 0 END                 AS is_raining,
    met.visibility,
    met.wind_speed_10m,
    met.weather_code::smallint              AS weather_code,
    m.lat,
    m.lon,
    0::smallint                             AS importance_code,
    NULL::double precision                  AS x_2154,
    NULL::double precision                  AS y_2154,
    _is_vacances(f.measurement_time::date)  AS is_vacances,
    _is_ferie(f.measurement_time::date)     AS is_ferie
FROM fresh f
LEFT JOIN gold.dim_spatial_grid_mapping m
       ON m.properties_twgid = f.channel_id
LEFT JOIN LATERAL (
    SELECT temperature_c, rain_mm, visibility, wind_speed_10m, weather_code
    FROM silver.meteo_hourly
    WHERE measurement_time <= f.measurement_time
    ORDER BY measurement_time DESC
    LIMIT 1
) met ON TRUE
ON CONFLICT (channel_id, fetched_at) DO UPDATE SET
    speed_kmh         = EXCLUDED.speed_kmh,
    lag_1             = EXCLUDED.lag_1,
    delta_current     = EXCLUDED.delta_current,
    delta_1           = EXCLUDED.delta_1,
    rolling_mean_3    = EXCLUDED.rolling_mean_3,
    temperature_2m    = EXCLUDED.temperature_2m,
    precipitation     = EXCLUDED.precipitation,
    rain              = EXCLUDED.rain,
    is_raining        = EXCLUDED.is_raining,
    is_vacances       = EXCLUDED.is_vacances,
    is_ferie          = EXCLUDED.is_ferie,
    lat               = EXCLUDED.lat,
    lon               = EXCLUDED.lon,
    computed_at       = NOW()
"""


_VELOV_SQL = """
WITH recent AS (
    SELECT fetched_at, station_id, num_bikes_available
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '2 hours'
      AND num_bikes_available IS NOT NULL
),
encoded AS (
    SELECT
        r.*,
        DENSE_RANK() OVER (ORDER BY r.station_id) - 1 AS station_id_encoded
    FROM recent r
),
windowed AS (
    SELECT
        e.*,
        LAG(num_bikes_available, 1) OVER w AS bikes_lag_1,
        LAG(num_bikes_available, 2) OVER w AS bikes_lag_2,
        LAG(num_bikes_available, 3) OVER w AS bikes_lag_3,
        AVG(num_bikes_available) OVER (
            PARTITION BY e.station_id
            ORDER BY e.fetched_at
            ROWS BETWEEN 36 PRECEDING AND 1 PRECEDING
        ) AS rolling_mean_3h
    FROM encoded e
    WINDOW w AS (PARTITION BY e.station_id ORDER BY e.fetched_at)
),
fresh AS (
    SELECT * FROM windowed
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
)
INSERT INTO gold.velov_features (
    measurement_time, station_id_encoded, station_id, bikes_available,
    bikes_lag_1, bikes_lag_2, bikes_lag_3, rolling_mean_3h,
    hour_sin, hour_cos, temperature_c, rain_mm, is_vacances, is_ferie
)
SELECT
    f.fetched_at,
    f.station_id_encoded,
    f.station_id,
    f.num_bikes_available,
    f.bikes_lag_1, f.bikes_lag_2, f.bikes_lag_3,
    f.rolling_mean_3h,
    SIN(2 * PI() * EXTRACT(HOUR FROM f.fetched_at) / 24.0) AS hour_sin,
    COS(2 * PI() * EXTRACT(HOUR FROM f.fetched_at) / 24.0) AS hour_cos,
    met.temperature_c,
    met.rain_mm,
    _is_vacances(f.fetched_at::date) AS is_vacances,
    _is_ferie(f.fetched_at::date)    AS is_ferie
FROM fresh f
LEFT JOIN LATERAL (
    SELECT temperature_c, rain_mm
    FROM silver.meteo_hourly
    WHERE measurement_time <= f.fetched_at
    ORDER BY measurement_time DESC
    LIMIT 1
) met ON TRUE
ON CONFLICT (station_id_encoded, measurement_time) DO UPDATE SET
    bikes_available = EXCLUDED.bikes_available,
    bikes_lag_1     = EXCLUDED.bikes_lag_1,
    rolling_mean_3h = EXCLUDED.rolling_mean_3h,
    temperature_c   = EXCLUDED.temperature_c,
    rain_mm         = EXCLUDED.rain_mm,
    is_vacances     = EXCLUDED.is_vacances,
    is_ferie        = EXCLUDED.is_ferie
"""


_BUS_DELAY_SQL = """
INSERT INTO gold.bus_delay_segments (
    date, hour, line_ref, segment_id,
    avg_delay_seconds, n_observations,
    is_vacances, is_ferie, weather_code
)
SELECT
    d                                          AS date,
    h::smallint                                AS hour,
    line_ref,
    'all'                                      AS segment_id,
    AVG(delay_seconds)::numeric(8,2)           AS avg_delay_seconds,
    COUNT(*)::int                              AS n_observations,
    _is_vacances(d)                            AS is_vacances,
    _is_ferie(d)                               AS is_ferie,
    NULL::int                                  AS weather_code
FROM (
    SELECT
        DATE(measurement_time)                        AS d,
        EXTRACT(HOUR FROM measurement_time)::int      AS h,
        line_ref,
        delay_seconds
    FROM silver.tcl_vehicles_clean
    WHERE measurement_time > NOW() - INTERVAL '7 days'
      AND line_ref IS NOT NULL
) src
GROUP BY line_ref, h, d
ON CONFLICT (date, hour, line_ref, segment_id) DO UPDATE SET
    avg_delay_seconds = EXCLUDED.avg_delay_seconds,
    n_observations    = EXCLUDED.n_observations,
    is_vacances       = EXCLUDED.is_vacances,
    is_ferie          = EXCLUDED.is_ferie
"""


_TCL_REALTIME_SQL = """
-- Alimente gold.tcl_vehicle_realtime à partir de silver.tcl_vehicles_clean
-- (1 ligne par véhicule distinct, avec sa dernière position observée).
-- Sert au Pro_4_Simulateur pour la carte TCL temps réel.
INSERT INTO gold.tcl_vehicle_realtime (
    vehicle_ref, line_ref, latitude, longitude,
    delay_seconds, is_delayed, recorded_at
)
SELECT DISTINCT ON (journey_ref)
    journey_ref                                 AS vehicle_ref,
    line_ref,
    lat                                         AS latitude,
    lon                                         AS longitude,
    delay_seconds,
    delay_seconds > 60                          AS is_delayed,
    measurement_time                            AS recorded_at
FROM silver.tcl_vehicles_clean
WHERE measurement_time > NOW() - INTERVAL '15 minutes'
  AND journey_ref IS NOT NULL
ORDER BY journey_ref, measurement_time DESC
ON CONFLICT (vehicle_ref, recorded_at) DO UPDATE SET
    latitude      = EXCLUDED.latitude,
    longitude     = EXCLUDED.longitude,
    delay_seconds = EXCLUDED.delay_seconds,
    is_delayed    = EXCLUDED.is_delayed
"""


def _build_traffic_features() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        _ensure_helpers(cur)
        cur.execute(_TRAFFIC_SQL)
        n = cur.rowcount
    logger.info("gold.traffic_features_live: %d rows upserted", n)
    return n


def _build_velov_features() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        _ensure_helpers(cur)
        cur.execute(_VELOV_SQL)
        n = cur.rowcount
    logger.info("gold.velov_features: %d rows upserted", n)
    return n


def _build_bus_delay_segments() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        _ensure_helpers(cur)
        cur.execute(_BUS_DELAY_SQL)
        n = cur.rowcount
    logger.info("gold.bus_delay_segments: %d rows upserted", n)
    return n


def _build_tcl_realtime() -> int:
    """Alimente gold.tcl_vehicle_realtime depuis silver.tcl_vehicles_clean.

    Le Pro_4_Simulateur (Sprint VPS-5) lit cette table ; sans ce feed elle
    est stale depuis 2 semaines (juin 2026), alors que silver.tcl_vehicles_clean
    reçoit bien les positions temps réel.
    """
    with raw_connection() as conn, conn.cursor() as cur:
        # Cleanup : on garde 1h d'historique. Le Pro_4 n'a besoin que de la
        # dernière position par véhicule, mais un peu d'historique est utile
        # pour les graphes "trajet des 5 dernières minutes".
        cur.execute("DELETE FROM gold.tcl_vehicle_realtime WHERE recorded_at < NOW() - INTERVAL '1 hour'")
        cur.execute(_TCL_REALTIME_SQL)
        n = cur.rowcount
    logger.info("gold.tcl_vehicle_realtime: %d rows upserted", n)
    return n


_BOTTLENECK_SQL = """
WITH bus_hourly AS (
    SELECT
        line_ref,
        hour,
        AVG(avg_delay_seconds)::numeric(8,2) AS avg_delay,
        SUM(n_observations)::int             AS total_obs
    FROM gold.bus_delay_segments
    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY line_ref, hour
),
traffic_hourly AS (
    SELECT
        EXTRACT(HOUR FROM fetched_at)::int AS hour_of_day,
        AVG(speed_kmh)::numeric(8,2)        AS avg_speed
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
    GROUP BY EXTRACT(HOUR FROM fetched_at)::int
)
INSERT INTO gold.infrastructure_bottlenecks (
    segment_id, line_ref, diagnosis, computed_at,
    bus_delay_seconds, traffic_speed_kmh, traffic_congestion,
    lat, lon, n_observations
)
SELECT
    bh.line_ref || '_h' || bh.hour,
    bh.line_ref,
    CASE
        WHEN bh.avg_delay > 120 AND COALESCE(th.avg_speed, 50) < 25 THEN 'infra'
        WHEN bh.avg_delay > 120 THEN 'operations'
        WHEN COALESCE(th.avg_speed, 50) < 25 THEN 'bus_lane_ok'
        ELSE 'ok'
    END,
    NOW()                                              AS computed_at,
    bh.avg_delay,
    COALESCE(th.avg_speed, 0),
    CASE WHEN th.avg_speed IS NOT NULL
         THEN (1.0 - LEAST(th.avg_speed / 50.0, 1.0))::numeric(4,3)
         ELSE 0
    END,
    45.76 + (HASHTEXT(bh.line_ref) % 100) * 0.0002,
    4.84  + (HASHTEXT(bh.line_ref) % 70)  * 0.0003,
    bh.total_obs
FROM bus_hourly bh
LEFT JOIN traffic_hourly th ON th.hour_of_day = bh.hour
"""


def _build_infrastructure_bottlenecks() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM gold.infrastructure_bottlenecks")
        cur.execute(_BOTTLENECK_SQL)
        n = cur.rowcount
    logger.info("gold.infrastructure_bottlenecks: %d rows upserted", n)
    return n


def _refresh_multimodal_grid() -> int:
    """Refresh la vue matérialisée ``gold.mv_multimodal_grid`` (Sprint 15+).

    Agrège sur grille 0.01° (~1 km) Lyon :
    * gold.traffic_features_live (vitesse, % congestion)
    * gold.tcl_vehicle_realtime (retard, % véhicules en retard)
    * silver.velov_clean (vélos/docks dispo)
    * silver.meteo_hourly (température, précipitations — CROSS JOIN)

    REFRESH CONCURRENTLY (pas de lock exclusif sur la MV côté dashboard).
    Requiert l'index unique ``idx_mv_multimodal_grid_latlon`` créé dans
    la migration 017. Si la MV n'existe pas (migration pas appliquée),
    on log un warning et on retourne 0 sans planter — le DAG continue.

    Returns:
        Nombre de cellules dans la MV après refresh (0 si MV absente).
    """
    with raw_connection() as conn, conn.cursor() as cur:
        # Vérifie que la MV existe avant de tenter le refresh
        cur.execute(
            """
            SELECT 1 FROM pg_matviews
            WHERE schemaname = 'gold' AND matviewname = 'mv_multimodal_grid'
            """
        )
        if cur.fetchone() is None:
            logger.warning(
                "gold.mv_multimodal_grid absente — migration 017 non appliquée. "
                "Le widget multimodal_heatmap affichera 'vue non alimentée'. "
                "Appliquer scripts/sql/migration_017_multimodal_grid.sql puis "
                "redémarrer ce DAG."
            )
            return 0
        # CONCURRENTLY = refresh sans lock exclusif (dashboard peut lire
        # la MV en parallèle). Requiert l'index unique idx_mv_multimodal_grid_latlon.
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_multimodal_grid")
        cur.execute("SELECT COUNT(*) FROM gold.mv_multimodal_grid")
        n = int(cur.fetchone()[0])
    logger.info("gold.mv_multimodal_grid: %d cellules refreshed", n)
    return n


def _refresh_bus_traffic_spatial() -> int:
    """Refresh ``gold.mv_bus_traffic_spatial`` (Sprint 15+, Axe 3).

    JOIN spatial bus x trafic par zone 0.001 deg (~100 m). Requiert
    l'index unique ``idx_mv_bus_traffic_spatial_pk`` de migration 018.
    """
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM pg_matviews
            WHERE schemaname = 'gold' AND matviewname = 'mv_bus_traffic_spatial'
            """
        )
        if cur.fetchone() is None:
            logger.warning("gold.mv_bus_traffic_spatial absente — migration 018 non appliquée.")
            return 0
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_bus_traffic_spatial")
        cur.execute("SELECT COUNT(*) FROM gold.mv_bus_traffic_spatial")
        n = int(cur.fetchone()[0])
    logger.info("gold.mv_bus_traffic_spatial: %d zones refreshed", n)
    return n
