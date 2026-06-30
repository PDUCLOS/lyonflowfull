-- Migration 035 — MV pour dernière position connue par channel
--
-- Bug : le DAG `build_spatial_mapping` exécutait à chaque run un
--       SELECT DISTINCT ON (channel_id) ORDER BY channel_id, measurement_time DESC
--       sur silver.trafic_boucles_clean (~1.55M rows × ~600 channels + geom).
--       Sans index composite, le planner faisait un sort complet en RAM qui
--       swappait, bloquait le disque sdb à 100% util et restait actif 24h+.
--
-- Fix : pré-calculer la dernière position dans une vue matérialisée UNIQUE
--       (channel_id) refreshée par le DAG (REFRESH CONCURRENTLY = secondes).
--       Index composite (channel_id, measurement_time DESC) WHERE geom IS NOT NULL
--       pour accélérer le refresh.
--
-- Idempotent : DROP IF EXISTS / CREATE.

BEGIN;

-- 1) Index composite — accélère le SELECT DISTINCT ON de la MV
--    (channel_id en tête, measurement_time DESC pour le tri, partiel sur geom NOT NULL)
CREATE INDEX IF NOT EXISTS idx_silver_trafic_chn_time_geom
    ON silver.trafic_boucles_clean (channel_id, measurement_time DESC)
    WHERE geom IS NOT NULL;

-- 2) Vue matérialisée — UNIQUE sur channel_id permet REFRESH CONCURRENTLY
DROP MATERIALIZED VIEW IF EXISTS gold.mv_latest_sensor_position CASCADE;

CREATE MATERIALIZED VIEW gold.mv_latest_sensor_position AS
SELECT DISTINCT ON (channel_id)
    channel_id,
    ST_Y(geom)::double precision AS lat,
    ST_X(geom)::double precision AS lon,
    geom,
    measurement_time AS last_seen_at
FROM silver.trafic_boucles_clean
WHERE geom IS NOT NULL
ORDER BY channel_id, measurement_time DESC;

-- Index UNIQUE obligatoire pour REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_sensor_position_chn
    ON gold.mv_latest_sensor_position (channel_id);

-- Grant à l'utilisateur lyonflow
GRANT SELECT ON gold.mv_latest_sensor_position TO lyonflow;

-- Stats fraîches
ANALYZE gold.mv_latest_sensor_position;

-- 3) Tracking
INSERT INTO public.schema_migrations (version) VALUES (35)
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- === VERIFY (hors transaction) ===
SELECT
    to_regclass('gold.mv_latest_sensor_position')::text AS mv_exists,
    (SELECT COUNT(*) FROM gold.mv_latest_sensor_position) AS channel_count,
    version AS tracked
FROM public.schema_migrations
WHERE version = 35;