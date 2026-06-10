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
        target: 'traffic' | 'velov' | 'bus_delay' | 'all'
        dry_run: log uniquement.

    Returns:
        {target: n_rows_upserted}
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
    if target in ("bottleneck", "all"):
        results["bottleneck"] = _build_infrastructure_bottlenecks()
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
    """Crée/refresh fonctions `_is_ferie` et `_is_vacances` (idempotent)."""
    cur.execute(_HELPER_FN_SQL)


# -----------------------------------------------------------------------------
# SQL set-based — un INSERT par domaine
# -----------------------------------------------------------------------------

_TRAFFIC_SQL = """
WITH recent AS (
    SELECT measurement_time, channel_id, vitesse_kmh
    FROM silver.trafic_boucles_clean
    WHERE measurement_time > NOW() - INTERVAL '2 hours'
),
windowed AS (
    SELECT
        r.measurement_time,
        r.channel_id,
        r.vitesse_kmh,
        LAG(r.vitesse_kmh, 1) OVER w AS speed_lag_1,
        LAG(r.vitesse_kmh, 2) OVER w AS speed_lag_2,
        LAG(r.vitesse_kmh, 3) OVER w AS speed_lag_3,
        AVG(r.vitesse_kmh) OVER (
            PARTITION BY r.channel_id
            ORDER BY r.measurement_time
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS rolling_mean_5min
    FROM recent r
    WINDOW w AS (PARTITION BY r.channel_id ORDER BY r.measurement_time)
),
fresh AS (
    SELECT * FROM windowed
    WHERE measurement_time > NOW() - INTERVAL '15 minutes'
)
INSERT INTO gold.traffic_features_live (
    measurement_time, node_idx, channel_id, speed_kmh,
    speed_lag_1, speed_lag_2, speed_lag_3, speed_delta_1,
    rolling_mean_5min, hour_sin, hour_cos, day_sin, day_cos,
    temperature_c, rain_mm, is_vacances, is_ferie, importance_code
)
SELECT
    f.measurement_time,
    m.node_idx,
    f.channel_id,
    f.vitesse_kmh,
    f.speed_lag_1,
    f.speed_lag_2,
    f.speed_lag_3,
    f.vitesse_kmh - f.speed_lag_1                              AS speed_delta_1,
    f.rolling_mean_5min,
    SIN(2 * PI() * EXTRACT(HOUR FROM f.measurement_time) / 24.0) AS hour_sin,
    COS(2 * PI() * EXTRACT(HOUR FROM f.measurement_time) / 24.0) AS hour_cos,
    SIN(2 * PI() * EXTRACT(DOW  FROM f.measurement_time) / 7.0)  AS day_sin,
    COS(2 * PI() * EXTRACT(DOW  FROM f.measurement_time) / 7.0)  AS day_cos,
    met.temperature_c,
    met.rain_mm,
    _is_vacances(f.measurement_time::date)                     AS is_vacances,
    _is_ferie(f.measurement_time::date)                        AS is_ferie,
    '0'                                                         AS importance_code
FROM fresh f
JOIN gold.dim_spatial_grid_mapping m ON m.channel_id = f.channel_id
LEFT JOIN LATERAL (
    SELECT temperature_c, rain_mm
    FROM silver.meteo_hourly
    WHERE measurement_time <= f.measurement_time
    ORDER BY measurement_time DESC
    LIMIT 1
) met ON TRUE
ON CONFLICT (node_idx, measurement_time) DO UPDATE SET
    speed_kmh         = EXCLUDED.speed_kmh,
    speed_lag_1       = EXCLUDED.speed_lag_1,
    speed_delta_1     = EXCLUDED.speed_delta_1,
    rolling_mean_5min = EXCLUDED.rolling_mean_5min,
    temperature_c     = EXCLUDED.temperature_c,
    rain_mm           = EXCLUDED.rain_mm,
    is_vacances       = EXCLUDED.is_vacances,
    is_ferie          = EXCLUDED.is_ferie
"""


_VELOV_SQL = """
WITH recent AS (
    SELECT fetched_at, station_id, bikes_available
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '2 hours'
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
        LAG(bikes_available, 1) OVER w AS bikes_lag_1,
        LAG(bikes_available, 2) OVER w AS bikes_lag_2,
        LAG(bikes_available, 3) OVER w AS bikes_lag_3,
        AVG(bikes_available) OVER (
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
    f.bikes_available,
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
    line_ref, segment_id, hour_of_day, day_of_week,
    avg_delay_seconds, n_observations,
    is_vacances, is_ferie, weather_code
)
SELECT
    line_ref,
    'all'                                     AS segment_id,
    h::smallint                               AS hour_of_day,
    dow::smallint                             AS day_of_week,
    AVG(delay_seconds)::real                  AS avg_delay_seconds,
    COUNT(*)::int                             AS n_observations,
    _is_vacances(d)                           AS is_vacances,
    _is_ferie(d)                              AS is_ferie,
    NULL::int                                 AS weather_code
FROM (
    SELECT
        DATE(measurement_time)                        AS d,
        EXTRACT(HOUR FROM measurement_time)::int      AS h,
        EXTRACT(DOW FROM measurement_time)::int       AS dow,
        line_ref,
        delay_seconds
    FROM silver.tcl_vehicles_clean
    WHERE measurement_time > NOW() - INTERVAL '7 days'
      AND line_ref IS NOT NULL
) src
GROUP BY line_ref, h, dow, d
ON CONFLICT (line_ref, segment_id, hour_of_day, day_of_week) DO UPDATE SET
    avg_delay_seconds = EXCLUDED.avg_delay_seconds,
    n_observations    = EXCLUDED.n_observations,
    is_vacances       = EXCLUDED.is_vacances,
    is_ferie          = EXCLUDED.is_ferie
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


_BOTTLENECK_SQL = """
WITH bus_hourly AS (
    SELECT
        line_ref,
        hour_of_day,
        AVG(avg_delay_seconds)::numeric(8,2) AS avg_delay,
        SUM(n_observations)::int             AS total_obs
    FROM gold.bus_delay_segments
    WHERE computed_at > NOW() - INTERVAL '7 days'
    GROUP BY line_ref, hour_of_day
),
traffic_hourly AS (
    SELECT
        EXTRACT(HOUR FROM measurement_time)::int AS hour_of_day,
        AVG(speed_kmh)::numeric(8,2)             AS avg_speed
    FROM gold.traffic_features_live
    WHERE measurement_time > NOW() - INTERVAL '7 days'
    GROUP BY EXTRACT(HOUR FROM measurement_time)::int
)
INSERT INTO gold.infrastructure_bottlenecks (
    segment_id, line_ref, diagnosis,
    bus_delay_seconds, traffic_speed_kmh, traffic_congestion,
    lat, lon, n_observations
)
SELECT
    bh.line_ref || '_h' || bh.hour_of_day,
    bh.line_ref,
    CASE
        WHEN bh.avg_delay > 120 AND COALESCE(th.avg_speed, 50) < 25 THEN 'infra'
        WHEN bh.avg_delay > 120 THEN 'operations'
        WHEN COALESCE(th.avg_speed, 50) < 25 THEN 'bus_lane_ok'
        ELSE 'ok'
    END,
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
LEFT JOIN traffic_hourly th ON th.hour_of_day = bh.hour_of_day
"""


def _build_infrastructure_bottlenecks() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM gold.infrastructure_bottlenecks")
        cur.execute(_BOTTLENECK_SQL)
        n = cur.rowcount
    logger.info("gold.infrastructure_bottlenecks: %d rows upserted", n)
    return n
