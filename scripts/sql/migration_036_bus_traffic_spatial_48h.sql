-- =============================================================================
-- LyonFlowFull — Migration 36 (Sprint 24, 2026-06-29)
-- =============================================================================
-- Optimisation : gold.mv_bus_traffic_spatial — fenêtre 7 jours → 48 heures.
--
-- CONTEXTE (incident 2026-06-29) :
--   La MV agrégeait INTERVAL '7 days' de gold.traffic_features_live (~3M+ lignes
--   sur 7j) mais le DAG la rafraîchit toutes les 10-15 min. On recomputait
--   donc 7 jours de données à chaque cycle pour un delta réel de ~0,15 %.
--   Couplé au bug CONCURRENTLY-sur-MV-vide (corrigé côté Python), la MV restait
--   à 0 ligne et le refresh saturait le worker, rendant la chaîne gold stale.
--
-- DÉCISION :
--   * traffic_features_live est une table "LIVE" (court terme), pas un
--     entrepôt historique. 48 h suffisent largement pour la corrélation
--     bus × trafic par tranche horaire (24 heures distinctes couvertes 2×).
--   * Scan ÷3 sur la source la plus lourde du JOIN → refresh qui tient dans
--     le statement_timeout (10 min) même sur le VPS 12 Go RAM.
--   * La logique métier (diagnostic infra/operations/bus_lane_ok/ok, zones
--     0.001° ≈ 100 m, ROI downstream) est STRICTEMENT INCHANGÉE.
--
-- IDEMPOTENT : DROP + CREATE. Le 1er REFRESH après cette migration DOIT être
--   non-concurrent (la MV WITH NO DATA n'est pas peuplée) — c'est géré
--   automatiquement par _refresh_matview_safe() (src/transformation/silver_to_gold.py).
--
-- DÉPENDANCES : gold.tcl_vehicle_realtime, gold.traffic_features_live
-- =============================================================================

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
    WHERE recorded_at > NOW() - INTERVAL '48 hours'   -- Sprint 24 : 7d → 48h
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
    WHERE fetched_at > NOW() - INTERVAL '48 hours'    -- Sprint 24 : 7d → 48h
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

-- Index unique OBLIGATOIRE pour autoriser REFRESH ... CONCURRENTLY ensuite.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_pk
    ON gold.mv_bus_traffic_spatial (line_ref, hour, lat, lon);

CREATE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_diagnosis
    ON gold.mv_bus_traffic_spatial (diagnosis);

CREATE INDEX IF NOT EXISTS idx_mv_bus_traffic_spatial_line
    ON gold.mv_bus_traffic_spatial (line_ref);

-- Peuplement initial (la MV est créée WITH DATA par défaut ci-dessus, mais on
-- garde ce commentaire comme rappel : si créée WITH NO DATA, exécuter
-- `REFRESH MATERIALIZED VIEW gold.mv_bus_traffic_spatial;` en NON-concurrent.)
