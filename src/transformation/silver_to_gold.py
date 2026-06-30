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
import os

from src.db import raw_connection

logger = logging.getLogger(__name__)


def transform_silver_to_gold(target: str = "all", dry_run: bool = False) -> dict[str, int]:
    """Transform Silver → Gold pour un ou tous les modèles.

    Args:
        target: 'traffic' | 'velov' | 'bus_delay' | 'tcl_realtime'
            | 'bottleneck' | 'multimodal_grid'
            | 'bus_traffic_spatial'
            | 'purge_traffic_features' (opt-in uniquement)
            | 'all'
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
    # Sprint 24+ (2026-06-29) — purge gold.traffic_features_live. Opt-in
    # uniquement (PAS dans 'all' : la purge ne doit pas tourner sur le
    # chemin critique */10 — risque de bloquer le refresh léger).
    if target == "purge_traffic_features":
        results["purge_traffic_features"] = _purge_old_traffic_features()
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
WITH latest_meteo AS (
    SELECT temperature_c, rain_mm, visibility, wind_speed_10m, weather_code
    FROM silver.meteo_hourly
    ORDER BY measurement_time DESC
    LIMIT 1
),
recent AS (
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
LEFT JOIN latest_meteo met ON TRUE
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
WITH latest_meteo AS (
    SELECT temperature_c, rain_mm
    FROM silver.meteo_hourly
    ORDER BY measurement_time DESC
    LIMIT 1
),
recent AS (
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
LEFT JOIN latest_meteo met ON TRUE
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
    # Sprint 24+ (2026-06-29) — statement_timeout contre hang silencieux.
    # JOIN global sur ~4.4M lignes peut déraper (mauvais plan, lock en attente).
    # Couper côté Postgres à 10 min — identique à _refresh_matview_safe —
    # évite de bloquer le worker Celery + tenir un lock 30 min.
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = 600000")  # 10 min
        cur.execute("DELETE FROM gold.infrastructure_bottlenecks")
        cur.execute(_BOTTLENECK_SQL)
        n = cur.rowcount
    logger.info("gold.infrastructure_bottlenecks: %d rows upserted", n)
    return n


def _refresh_multimodal_grid() -> int:
    """Refresh ``gold.mv_multimodal_grid`` (Sprint 15+, migration 017).

    Agrège sur grille 0.01° (~1 km) Lyon : trafic (vitesse, % congestion),
    TCL (retard), Vélov (dispo), météo. Refresh robuste via
    :func:`_refresh_matview_safe` (Sprint 24).
    """
    return _refresh_matview_safe(
        "mv_multimodal_grid",
        migration_hint="Appliquer scripts/sql/migration_017_multimodal_grid.sql.",
    )


def _refresh_bus_traffic_spatial() -> int:
    """Refresh ``gold.mv_bus_traffic_spatial`` (Sprint 15+, Axe 3, migration 018).

    JOIN spatial bus x trafic par zone 0.001° (~100 m). Refresh robuste via
    :func:`_refresh_matview_safe` (Sprint 24) — corrige le 0 ligne dû au
    CONCURRENTLY sur MV jamais peuplée.
    """
    return _refresh_matview_safe(
        "mv_bus_traffic_spatial",
        migration_hint="Appliquer scripts/sql/migration_018_bus_traffic_spatial.sql.",
    )


def _purge_old_traffic_features(retention_hours: int | None = None) -> int:
    """Purge gold.traffic_features_live > N heures (Sprint 24+ — 2026-06-29).

    Allège les scans gold downstream :
    * ``mv_multimodal_grid`` (migration 017, grille 1 km)
    * ``mv_bus_traffic_spatial`` (migration 036, fenêtre 48 h)
    * ``gold.infrastructure_bottlenecks`` (legacy, à supprimer)

    L'index ``idx_gold_traffic_features_live_computed_at`` (migration 037)
    rend le DELETE < 1 s même sur 1 M+ rows purgées.

    Rétention configurable via ``GOLD_TRAFFIC_FEATURES_RETENTION_HOURS``
    (défaut 48). 48 h est aligné sur la fenêtre de ``mv_bus_traffic_spatial``
    (Sprint 24) — au-delà, les MV n'ont pas besoin des données. Si un
    consumer downstream requiert plus d'historique, augmenter la valeur et
    vérifier au préalable par ``grep gold.traffic_features_live`` dans le
    code.

    Args:
        retention_hours: override explicite (test). Si None, lit l'env var.

    Returns:
        Nombre de rows purgées.
    """
    if retention_hours is None:
        retention_hours = int(os.getenv("GOLD_TRAFFIC_FEATURES_RETENTION_HOURS", "48"))
    with raw_connection() as conn, conn.cursor() as cur:
        # Garde-fou anti-hang : 5 min suffit largement pour un DELETE indexé.
        cur.execute("SET statement_timeout = 300000")
        cur.execute(
            "DELETE FROM gold.traffic_features_live WHERE computed_at < NOW() - INTERVAL %s",
            (f"{retention_hours} hours",),
        )
        n = cur.rowcount
    logger.info(
        "gold.traffic_features_live: %d rows purged (>%sh retention)",
        n,
        retention_hours,
    )
    return n


def _refresh_matview_safe(
    matview: str,
    *,
    migration_hint: str = "",
    timeout_ms: int = 600_000,  # 10 min — coupe avant le execution_timeout Airflow
) -> int:
    """Refresh idempotent et robuste d'une vue matérialisée ``gold.<matview>``.

    Stratégie :
      * MV absente            → warning + return 0 (le DAG continue).
      * MV non peuplée        → ``REFRESH`` plain (obligatoire au 1er passage).
      * MV déjà peuplée       → ``REFRESH ... CONCURRENTLY`` (pas de lock lecture),
                                 fallback plain si CONCURRENTLY échoue.
      * statement_timeout posé pour éviter tout hang silencieux.

    Args:
        matview: nom court de la MV (sans le schéma), ex. ``mv_bus_traffic_spatial``.
        migration_hint: message d'aide si la MV est absente (n° de migration).
        timeout_ms: budget temps Postgres avant abort (défaut 10 min).

    Returns:
        Nombre de lignes dans la MV après refresh (0 si MV absente).
    """
    fqmv = f"gold.{matview}"
    with raw_connection() as conn, conn.cursor() as cur:
        # Garde-fou anti-hang : abort côté Postgres, pas seulement côté Airflow.
        cur.execute("SET statement_timeout = %s", (timeout_ms,))

        # La MV existe-t-elle, et est-elle déjà peuplée ?
        cur.execute(
            """
            SELECT ispopulated
            FROM pg_matviews
            WHERE schemaname = 'gold' AND matviewname = %s
            """,
            (matview,),
        )
        row = cur.fetchone()
        if row is None:
            logger.warning(
                "%s absente — migration non appliquée. %s Le widget consommateur affichera 'vue non alimentée'.",
                fqmv,
                migration_hint,
            )
            return 0

        is_populated = bool(row[0])
        if not is_populated:
            # 1er passage OBLIGATOIRE en plain : CONCURRENTLY est interdit
            # sur une MV jamais peuplée. C'était la cause du 0 ligne.
            logger.info("%s jamais peuplée → REFRESH plain (1er passage).", fqmv)
            cur.execute(f"REFRESH MATERIALIZED VIEW {fqmv}")
        else:
            try:
                # CONCURRENTLY = le dashboard peut lire la MV pendant le refresh
                # (pas de lock exclusif). Requiert un index unique sur la MV.
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {fqmv}")
            except Exception as exc:
                # Index unique manquant, conflit, etc. → on garantit quand même
                # une MV fraîche via un refresh plain (lock court) au lieu de
                # laisser des données stale.
                conn.rollback()
                logger.warning(
                    "%s : REFRESH CONCURRENTLY a échoué (%s) → fallback REFRESH plain.",
                    fqmv,
                    exc,
                )
                cur.execute(f"REFRESH MATERIALIZED VIEW {fqmv}")

        cur.execute(f"SELECT COUNT(*) FROM {fqmv}")
        n = int(cur.fetchone()[0])
    logger.info("%s: %d lignes refreshed.", fqmv, n)
    return n
