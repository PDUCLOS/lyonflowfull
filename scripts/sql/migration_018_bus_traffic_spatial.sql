-- =============================================================================
-- LyonFlowFull — Migration 18 (Sprint 15+, 2026-06-19)
-- =============================================================================
-- Vue matérialisée : gold.mv_bus_traffic_spatial
--
-- Corrige la lacune du bottleneck actuel (_BOTTLENECK_SQL dans
-- silver_to_gold.py) qui fait un JOIN bus × trafic par HEURE GLOBALE :
-- le retard du bus L12 à 8h était corrélé au trafic moyen de TOUT Lyon
-- à 8h, pas au trafic de la zone Part-Dieu ↔ Gerland.
--
-- Cette MV fait un JOIN SPATIAL : les positions GPS des véhicules TCL
-- (gold.tcl_vehicle_realtime.latitude/longitude) sont corrélées au trafic
-- routier (gold.traffic_features_live.lat/lon) de la MÊME zone
-- (résolution 0.001° ≈ 100m).
--
-- Option B (non-breaking) : cette MV coexiste avec
-- gold.infrastructure_bottlenecks. Le widget bus_traffic_spatial.py
-- lit cette MV ; correlation_matrix.py continue de lire l'ancien.
-- Bascule vers Option A (remplacement) quand la MV aura fait ses
-- preuves sur ≥ 7 jours de données.
--
-- Refresh : */15 min dans le DAG transform_silver_to_gold.
-- Dépendances : gold.tcl_vehicle_realtime, gold.traffic_features_live
-- =============================================================================

-- Suppression si existe (idempotent)
DROP MATERIALIZED VIEW IF EXISTS gold.mv_bus_traffic_spatial;

CREATE MATERIALIZED VIEW gold.mv_bus_traffic_spatial AS
WITH
bus_positions AS (
    SELECT
        line_ref,
        EXTRACT(HOUR FROM recorded_at)::int AS hour,
        ROUND(latitude::numeric, 3) AS lat3,
        ROUND(longitude::numeric, 3) AS lon3,
        AVG(delay_seconds)::numeric(8,2) AS avg_delay_sec,
        COUNT(*) AS n_obs,
        SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END)::int AS n_delayed
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '7 days'
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
    GROUP BY line_ref,
             EXTRACT(HOUR FROM recorded_at)::int,
             ROUND(latitude::numeric, 3),
             ROUND(longitude::numeric, 3)
),
traffic_zones AS (
    SELECT
        ROUND(lat::numeric, 3) AS lat3,
        ROUND(lon::numeric, 3) AS lon3,
        EXTRACT(HOUR FROM fetched_at)::int AS hour,
        AVG(speed_kmh)::numeric(6,2) AS avg_speed,
        COUNT(*) AS n_sensors
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
      AND lat IS NOT NULL
      AND lon IS NOT NULL
    GROUP BY ROUND(lat::numeric, 3),
             ROUND(lon::numeric, 3),
             EXTRACT(HOUR FROM fetched_at)::int
)
SELECT
    bp.line_ref,
    bp.hour,
    bp.lat3 AS lat,
    bp.lon3 AS lon,
    bp.avg_delay_sec AS bus_delay_sec,
    bp.n_obs AS bus_observations,
    bp.n_delayed AS bus_delayed_count,
    COALESCE(tz.avg_speed, 0)::numeric(6,2) AS traffic_speed_kmh,
    COALESCE(tz.n_sensors, 0)::int AS traffic_sensors,
    CASE
        WHEN bp.avg_delay_sec > 120 AND COALESCE(tz.avg_speed, 50) < 25
            THEN 'infra'
        WHEN bp.avg_delay_sec > 120 AND (tz.avg_speed >= 25 OR tz.avg_speed IS NULL)
            THEN 'operations'
        WHEN bp.avg_delay_sec <= 120 AND COALESCE(tz.avg_speed, 50) < 25
            THEN 'bus_lane_ok'
        ELSE 'ok'
    END AS diagnosis,
    CASE WHEN tz.avg_speed IS NOT NULL
         THEN (1.0 - LEAST(tz.avg_speed / 50.0, 1.0))::numeric(4,3)
         ELSE 0
    END AS traffic_congestion,
    NOW() AS computed_at
FROM bus_positions bp
LEFT JOIN traffic_zones tz
    ON bp.lat3 = tz.lat3
   AND bp.lon3 = tz.lon3
   AND bp.hour = tz.hour;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_pk
    ON gold.mv_bus_traffic_spatial (line_ref, hour, lat, lon);

CREATE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_diagnosis
    ON gold.mv_bus_traffic_spatial (diagnosis);

CREATE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_line
    ON gold.mv_bus_traffic_spatial (line_ref);
