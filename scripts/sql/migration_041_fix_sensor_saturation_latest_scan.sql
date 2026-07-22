-- Migration 041 — Fix scan complet sur gold.mv_sensor_saturation (2026-07-02)
--
-- Pourquoi cette migration existe :
-- REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_sensor_saturation
-- (migration 034) échouait en boucle (`statement_timeout` 240s) depuis
-- le */15min DAG refresh_sensor_saturation. Root cause : la CTE `latest`
-- (DISTINCT ON channel_id, dernière mesure) n'a AUCUNE borne temporelle
-- → scan complet de gold.traffic_features_live (3.3 Go / 5M lignes,
-- cost ~700k) à chaque refresh, alors que les CTE 7j/24h coûtent
-- seulement ~99k chacune grâce à leur filtre sur computed_at.
--
-- Fix : `latest` réutilise la fenêtre `measurements_24h` (déjà bornée
-- par un index sur computed_at) au lieu de rescanner toute la table.
-- Les capteurs sont alimentés */5min (bronze.trafic_boucles) donc la
-- mesure la plus récente est toujours dans les dernières 24h — aucune
-- perte de données côté fonctionnel.

DROP MATERIALIZED VIEW IF EXISTS gold.mv_sensor_saturation CASCADE;

CREATE MATERIALIZED VIEW gold.mv_sensor_saturation AS
WITH
    measurements_7d AS (
        SELECT
            channel_id,
            speed_kmh,
            computed_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL
          AND speed_kmh > 0
          AND computed_at >= NOW() - INTERVAL '7 days'
    ),
    measurements_24h AS (
        SELECT
            channel_id,
            speed_kmh,
            computed_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL
          AND speed_kmh > 0
          AND computed_at >= NOW() - INTERVAL '24 hours'
    ),
    agg_7d AS (
        SELECT
            channel_id,
            COUNT(*)                                      AS n_obs_7d,
            PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY speed_kmh)
                AS v85_7j,
            MAX(computed_at)                              AS last_7d_at
        FROM measurements_7d
        GROUP BY channel_id
    ),
    agg_24h AS (
        SELECT
            channel_id,
            COUNT(*)        AS n_obs_24h,
            MIN(speed_kmh)  AS vmin_24h,
            MAX(speed_kmh)  AS vmax_24h,
            STDDEV(speed_kmh) AS std_24h,
            AVG(speed_kmh)  AS avg_24h,
            MAX(computed_at) AS last_at
        FROM measurements_24h
        GROUP BY channel_id
    ),
    -- Mesure la plus récente — bornée à measurements_24h (fix migration 041 :
    -- l'ancienne version scannait toute la table sans limite temporelle).
    latest AS (
        SELECT DISTINCT ON (channel_id)
            channel_id,
            speed_kmh AS current_speed,
            computed_at AS current_at
        FROM measurements_24h
        ORDER BY channel_id, computed_at DESC
    )
SELECT
    a7.channel_id,
    a7.n_obs_7d,
    ROUND(a7.v85_7j::numeric, 1)                         AS v85_7j,
    a7.last_7d_at,
    a24.n_obs_24h,
    a24.vmin_24h,
    a24.vmax_24h,
    ROUND(a24.std_24h::numeric, 2)                       AS std_24h,
    ROUND(a24.avg_24h::numeric, 1)                       AS avg_24h,
    a24.last_at                                          AS last_24h_at,
    ROUND(
        ((l.current_speed / NULLIF(a7.v85_7j, 0)) * 100)::numeric,
        1
    )                                                       AS sat_now_pct,
    l.current_speed                                        AS current_speed_kmh,
    ROUND(
        (((a24.vmax_24h - a24.vmin_24h) / NULLIF(a7.v85_7j, 0)) * 100)::numeric,
        1
    )                                                       AS amp_pct,
    CASE
        WHEN a7.n_obs_7d IS NULL OR a7.n_obs_7d = 0
            THEN 'no_data'
        WHEN a24.last_at < NOW() - INTERVAL '15 minutes'
            THEN 'stale'
        WHEN a24.std_24h < 1.0
         AND ((a24.vmax_24h - a24.vmin_24h) / NULLIF(a7.v85_7j, 0)) * 100 < 2.0
            THEN 'stuck'
        ELSE 'ok'
    END                                                     AS status
FROM agg_7d a7
LEFT JOIN agg_24h a24 ON a7.channel_id = a24.channel_id
LEFT JOIN latest l   ON a7.channel_id = l.channel_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sensor_saturation_channel
    ON gold.mv_sensor_saturation (channel_id);

CREATE INDEX IF NOT EXISTS idx_mv_sensor_saturation_status
    ON gold.mv_sensor_saturation (status);

COMMENT ON MATERIALIZED VIEW gold.mv_sensor_saturation IS
    'Sprint 22+ (migration 034) : saturation %v85 + amplitude %v85 + status
     par capteur. Refresh : REFRESH MATERIALIZED VIEW CONCURRENTLY via
     dags/maintenance/refresh_sensor_saturation.py (toutes les 15 min).
     Migration 041 (2026-07-02) : CTE `latest` bornée à measurements_24h
     (fix statement_timeout récurrent — l''ancienne version scannait
     toute la table gold.traffic_features_live sans limite temporelle).';
