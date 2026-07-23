-- =============================================================================
-- Migration 022 — Sprint 17 Axe 7 : Météo comme variable d'interaction
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.9.0 (cible)
-- Branche     : main
-- Prérequis   : Sprint 8+ (toutes sources Bronze actives)
--               Sprint 9+ (gold.traffic_features_live schéma v0.3.1)
--               Sprint 15+ (gold.tcl_vehicle_realtime)
--
-- Crée :
--   gold.mv_meteo_impact — Vue matérialisée : impact de la météo (5 bandes)
--                          sur 3 modes (trafic, TCL, Vélov), avec delta vs
--                          baseline "beau temps" (fair_weather).
--
-- Bandes météo (CASE WHEN sur précipitations + température) :
--   * heavy_rain  : precipitation > 5 mm/h
--   * light_rain  : precipitation > 1 mm/h
--   * frost       : temperature_c < 0
--   * heatwave    : temperature_c > 35
--   * fair        : reste (baseline)
--
-- Métriques calculées (par bande) :
--   * trafic  : avg_speed_kmh, std_speed, n_obs, delta vs fair
--   * TCL     : avg_delay_seconds, n_obs, delta vs fair
--   * Vélov   : avg_bikes_available, n_obs, delta vs fair
--
-- Refresh :
--   Quotidien 04h30 par ``dags/maintenance/refresh_meteo_impact.py``
--   (REFRESH MATERIALIZED VIEW CONCURRENTLY, donc index unique requis).
--
-- Notes sur le schéma réel (vs spec d'origine) :
--   * ``silver.meteo_hourly`` a ``temperature_c`` et ``rain_mm``
--     (PAS ``temperature_2m``/``precipitation`` comme dans la spec).
--   * ``gold.traffic_features_live`` a ``fetched_at`` et ``speed_kmh``.
--   * ``gold.tcl_vehicle_realtime`` a ``recorded_at`` et ``delay_seconds``.
--   * ``silver.velov_clean`` a ``fetched_at`` et ``num_bikes_available``.
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW + index unique.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : mv_meteo_impact
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_meteo_impact CASCADE;

CREATE MATERIALIZED VIEW gold.mv_meteo_impact AS
WITH
-- Bande météo par heure (30 jours de fenêtre)
meteo_bands AS (
    SELECT
        measurement_time,
        temperature_c,
        rain_mm,
        CASE
            WHEN rain_mm > 5             THEN 'heavy_rain'
            WHEN rain_mm > 1             THEN 'light_rain'
            WHEN temperature_c < 0       THEN 'frost'
            WHEN temperature_c > 35      THEN 'heatwave'
            ELSE 'fair'
        END AS meteo_band
    FROM silver.meteo_hourly
    WHERE measurement_time > NOW() - INTERVAL '30 days'
),
-- Trafic : moyenne vitesse par bande
traffic_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(tf.speed_kmh)::numeric(6,2)                  AS avg_speed_kmh,
        STDDEV(tf.speed_kmh)::numeric(6,2)               AS std_speed_kmh,
        COUNT(*)                                          AS n_obs
    FROM gold.traffic_features_live tf
    JOIN meteo_bands mb
      ON DATE_TRUNC('hour', tf.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
),
-- TCL : retard moyen par bande
tcl_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(tr.delay_seconds)::numeric(8,2)               AS avg_delay_seconds,
        COUNT(*)                                          AS n_obs
    FROM gold.tcl_vehicle_realtime tr
    JOIN meteo_bands mb
      ON DATE_TRUNC('hour', tr.recorded_at) = DATE_TRUNC('hour', mb.measurement_time)
    WHERE tr.delay_seconds IS NOT NULL
    GROUP BY mb.meteo_band
),
-- Vélov : vélos dispos par bande
velov_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(vc.num_bikes_available)::numeric(6,2)         AS avg_bikes_available,
        COUNT(*)                                          AS n_obs
    FROM silver.velov_clean vc
    JOIN meteo_bands mb
      ON DATE_TRUNC('hour', vc.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    WHERE vc.num_bikes_available IS NOT NULL
    GROUP BY mb.meteo_band
),
-- Baselines "beau temps" (1 ligne par mode, filtrée sur fair)
fair_t AS (SELECT avg_speed_kmh       FROM traffic_by_meteo WHERE meteo_band = 'fair'),
fair_c AS (SELECT avg_delay_seconds   FROM tcl_by_meteo     WHERE meteo_band = 'fair'),
fair_v AS (SELECT avg_bikes_available FROM velov_by_meteo   WHERE meteo_band = 'fair')
SELECT
    t.meteo_band,
    -- Trafic
    t.avg_speed_kmh,
    t.std_speed_kmh,
    t.n_obs                                       AS traffic_n_obs,
    (t.avg_speed_kmh - (SELECT avg_speed_kmh FROM fair_t))::numeric(6,2)
                                                  AS traffic_delta_kmh_vs_fair,
    -- TCL
    c.avg_delay_seconds,
    c.n_obs                                       AS tcl_n_obs,
    (c.avg_delay_seconds - (SELECT avg_delay_seconds FROM fair_c))::numeric(8,2)
                                                  AS tcl_delay_delta_sec_vs_fair,
    -- Vélov
    v.avg_bikes_available,
    v.n_obs                                       AS velov_n_obs,
    (v.avg_bikes_available - (SELECT avg_bikes_available FROM fair_v))::numeric(6,2)
                                                  AS velov_delta_bikes_vs_fair,
    NOW()                                         AS computed_at
FROM traffic_by_meteo t
JOIN tcl_by_meteo     c ON c.meteo_band = t.meteo_band
JOIN velov_by_meteo   v ON v.meteo_band = t.meteo_band
ORDER BY
    CASE t.meteo_band
        WHEN 'fair'        THEN 1
        WHEN 'light_rain'  THEN 2
        WHEN 'heavy_rain'  THEN 3
        WHEN 'frost'       THEN 4
        WHEN 'heatwave'    THEN 5
    END;

-- Index unique sur meteo_band : permet REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_gold_mv_meteo_impact_band
    ON gold.mv_meteo_impact (meteo_band);

COMMENT ON MATERIALIZED VIEW gold.mv_meteo_impact IS
    'Sprint 17 Axe 7 — Impact météo par bande (5) × mode (3).
     trafic_delta_kmh_vs_fair     : delta vitesse moyenne (km/h, négatif = congestion)
     tcl_delay_delta_sec_vs_fair  : delta retard moyen (sec, positif = plus de retard)
     velov_delta_bikes_vs_fair    : delta vélos dispos (négatif = moins de vélos).
     Sert au widget meteo_impact (Pro_3_Correlation) pour tableau comparatif.
     Refresh quotidien 04h30 par dags/maintenance/refresh_meteo_impact.py.';

-- Permissions
GRANT SELECT ON gold.mv_meteo_impact TO PUBLIC;
