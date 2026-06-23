-- Migration 034 — Sprint 22+ audit saturation v2 (matérialisation)
--
-- Pourquoi cette migration existe :
-- La migration 033 créait une VIEW (non matérialisée) qui scannait
-- ~889k rows de `gold.traffic_features_live` × 2 fenêtres temporelles
-- (7j + 24h) × PERCENTILE_CONT + STDDEV + 3 LEFT JOINs → > 60s en prod
-- (timeout sur le widget Streamlit).
--
-- Solution : MATERIALIZED VIEW + UNIQUE INDEX (requis pour
-- REFRESH CONCURRENTLY) + un DAG Airflow `*/15 min` qui fait
-- `REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_sensor_saturation`.
--
-- Trade-off accepté :
--   * Avant (vue) : 0 lag, 60+ s/query
--   * Après (matérialisée) : 0-15 min lag, < 100 ms/query
--   * Le widget a un cache Streamlit 60s de toute façon → le lag de
--     15 min ne change rien à l'UX.

DROP VIEW IF EXISTS gold.v_sensor_saturation CASCADE;

CREATE OR REPLACE MATERIALIZED VIEW gold.mv_sensor_saturation AS
WITH
    -- Mesures des 7 derniers jours (fenêtre large pour v85)
    measurements_7d AS (
        SELECT
            channel_id,
            speed_kmh,
            computed_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL
          AND speed_kmh > 0  -- cohérent avec _parse_grandlyon_vitesse fix (e05f501)
          AND computed_at >= NOW() - INTERVAL '7 days'
    ),
    -- Mesures des dernières 24h (pour amplitude + std)
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
    -- Agrégat 7j par capteur (v85 = vitesse libre typique)
    agg_7d AS (
        SELECT
            channel_id,
            COUNT(*)                                      AS n_obs_7d,
            -- PERCENTILE_CONT doit s'appliquer à un type ordonnable.
            -- numeric est plus stable que double pour les percentiles
            -- (Sprint 22+ : corrigé suite erreur déploiement VPS).
            PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY speed_kmh)
                AS v85_7j,
            MAX(computed_at)                              AS last_7d_at
        FROM measurements_7d
        GROUP BY channel_id
    ),
    -- Aggrégats 24h par capteur
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
    -- Mesure la plus récente (pour sat_now_pct)
    latest AS (
        SELECT DISTINCT ON (channel_id)
            channel_id,
            speed_kmh AS current_speed,
            computed_at AS current_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL AND speed_kmh > 0
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
    -- Saturation = vitesse actuelle / v85 * 100
    --   > 100% = congestion (trafic plus lent que la vitesse libre)
    --   < 50%  = fluide
    --   ~ 100% = vitesse libre typique
    -- Cast ``::numeric`` requis avant ``ROUND(x, 1)`` (PostgreSQL
    -- n'accepte pas round(double, integer) sans cast explicite —
    -- corrigé Sprint 22+ suite erreur déploiement VPS).
    ROUND(
        ((l.current_speed / NULLIF(a7.v85_7j, 0)) * 100)::numeric,
        1
    )                                                       AS sat_now_pct,
    l.current_speed                                        AS current_speed_kmh,
    -- Amplitude = range 24h / v85_7j * 100
    --   > 50% = variation typique (fluide ↔ bouchon)
    --   < 2%  = suspect (capteur stuck)
    ROUND(
        (((a24.vmax_24h - a24.vmin_24h) / NULLIF(a7.v85_7j, 0)) * 100)::numeric,
        1
    )                                                       AS amp_pct,
    -- Statut de santé
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

-- UNIQUE INDEX obligatoire pour REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- Sans lui, le refresh bloque les reads pendant la durée du recompute.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sensor_saturation_channel
    ON gold.mv_sensor_saturation (channel_id);

-- Index secondaires pour les filtres les plus probables du widget.
CREATE INDEX IF NOT EXISTS idx_mv_sensor_saturation_status
    ON gold.mv_sensor_saturation (status);

COMMENT ON MATERIALIZED VIEW gold.mv_sensor_saturation IS
    'Sprint 22+ : saturation %v85 + amplitude %v85 + status par capteur.
     Refresh : REFRESH MATERIALIZED VIEW CONCURRENTLY via
     dags/maintenance/refresh_sensor_saturation.py (toutes les 15 min).
     Avant cette migration : vue non matérialisée (migration 033) qui
     timeoutait > 60s sur 889k rows en prod.';
