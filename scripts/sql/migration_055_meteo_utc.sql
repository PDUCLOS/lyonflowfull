-- migration_055_meteo_utc.sql
-- ============================================================================
-- Météo / qualité de l'air : heures Open-Meteo enfin en UTC + météo « courante »
-- ============================================================================
-- Contexte (2026-10-03) :
-- 1. Open-Meteo est appelé avec timezone=Europe/Paris (src/ingestion/meteo.py,
--    air_quality.py) : ses heures sont LOCALES (« 2026-10-02T00:00 »). Elles
--    étaient insérées telles quelles dans une colonne timestamptz avec une
--    session en UTC → tout silver.meteo_hourly / silver.air_quality_clean était
--    décalé de +2 h l'été, +1 h l'hiver. bronze_to_silver convertit désormais
--    à l'insertion ; cette migration recale l'historique :
--        UTC réel = (measurement_time AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris'
-- 2. gold.mv_multimodal_grid prenait « la dernière ligne » de meteo_hourly,
--    c'est-à-dire la prévision de J+1 23h : borné à measurement_time <= NOW()
--    (même correctif que silver_to_gold.latest_meteo).
--
-- À appliquer DAG transform_bronze_to_silver en pause (sinon un run de l'ancien
-- code réécrirait des heures dans l'ancienne convention entre le code et la
-- migration). Idempotente : un marqueur sur la colonne empêche un second
-- recalage (qui décalerait encore de 2 h sans erreur).
-- ============================================================================

DO $$
DECLARE
    v_marker   TEXT;
    v_before   INTEGER;
    v_after    INTEGER;
BEGIN
    SELECT col_description('silver.meteo_hourly'::regclass, a.attnum) INTO v_marker
    FROM pg_attribute a
    WHERE a.attrelid = 'silver.meteo_hourly'::regclass AND a.attname = 'measurement_time';

    IF COALESCE(v_marker, '') LIKE '%migration 055%' THEN
        RAISE NOTICE 'migration 055 déjà appliquée (marqueur présent) : aucun recalage';
        RETURN;
    END IF;

    LOCK TABLE silver.meteo_hourly, silver.air_quality_clean IN EXCLUSIVE MODE;

    -- measurement_time est la clé primaire : un UPDATE décalant de 1-2 h
    -- entrerait en collision avec les lignes voisines. Copie, vidage, réinsertion.
    CREATE TEMP TABLE m055_meteo ON COMMIT DROP AS SELECT * FROM silver.meteo_hourly;
    SELECT count(*) INTO v_before FROM m055_meteo;
    DELETE FROM silver.meteo_hourly;
    INSERT INTO silver.meteo_hourly (
        measurement_time, temperature_c, rain_mm, rain, cloud_cover, weather_code,
        visibility, wind_speed_10m, wind_gusts_10m, uv_index, humidity, fetched_at, is_forecast
    )
    SELECT
        (m.measurement_time AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris',
        m.temperature_c, m.rain_mm, m.rain, m.cloud_cover, m.weather_code,
        m.visibility, m.wind_speed_10m, m.wind_gusts_10m, m.uv_index, m.humidity, m.fetched_at,
        CASE
            WHEN m.fetched_at IS NULL THEN m.is_forecast
            ELSE ((m.measurement_time AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris') > m.fetched_at
        END
    FROM m055_meteo m
    -- Passage à l'heure d'été : l'heure locale 02:00 inexistante peut tomber sur 03:00
    ON CONFLICT (measurement_time) DO NOTHING;
    GET DIAGNOSTICS v_after = ROW_COUNT;
    RAISE NOTICE 'silver.meteo_hourly : % lignes recalées sur % (% écartées par collision DST)',
        v_after, v_before, v_before - v_after;

    CREATE TEMP TABLE m055_aq ON COMMIT DROP AS SELECT * FROM silver.air_quality_clean;
    SELECT count(*) INTO v_before FROM m055_aq;
    DELETE FROM silver.air_quality_clean;
    INSERT INTO silver.air_quality_clean (
        measurement_time, european_aqi, pm10, pm2_5, nitrogen_dioxide, ozone, carbon_monoxide, fetched_at
    )
    SELECT
        (a.measurement_time AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris',
        a.european_aqi, a.pm10, a.pm2_5, a.nitrogen_dioxide, a.ozone, a.carbon_monoxide, a.fetched_at
    FROM m055_aq a
    ON CONFLICT (measurement_time) DO NOTHING;
    GET DIAGNOSTICS v_after = ROW_COUNT;
    RAISE NOTICE 'silver.air_quality_clean : % lignes recalées sur % (% écartées par collision DST)',
        v_after, v_before, v_before - v_after;

    COMMENT ON COLUMN silver.meteo_hourly.measurement_time IS
        'Heure UTC réelle. Heures Open-Meteo locales (Europe/Paris) converties à l''insertion ; historique recalé par la migration 055.';
    COMMENT ON COLUMN silver.air_quality_clean.measurement_time IS
        'Heure UTC réelle. Heures Open-Meteo locales (Europe/Paris) converties à l''insertion ; historique recalé par la migration 055.';
END $$;


-- gold.mv_multimodal_grid : météo courante au lieu de la dernière prévision.
-- Définition identique à la prod (pg_get_viewdef, = migration 017) sauf le CTE meteo.
BEGIN;

DROP MATERIALIZED VIEW IF EXISTS gold.mv_multimodal_grid;

CREATE MATERIALIZED VIEW gold.mv_multimodal_grid AS
WITH
trafic_grid AS (
    SELECT
        ROUND(lat::numeric, 2)                       AS grid_lat,
        ROUND(lon::numeric, 2)                       AS grid_lon,
        AVG(speed_kmh)::numeric(6,2)                 AS avg_speed_kmh,
        COUNT(*)::int                                AS n_sensors,
        (SUM(CASE WHEN speed_kmh < 25 THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2)  AS pct_congestion
    FROM gold.traffic_features_live
    WHERE fetched_at >= NOW() - INTERVAL '1 hour'
      AND lat IS NOT NULL AND lon IS NOT NULL
    GROUP BY 1, 2
),
tcl_grid AS (
    SELECT
        ROUND(latitude::numeric, 2)                  AS grid_lat,
        ROUND(longitude::numeric, 2)                 AS grid_lon,
        AVG(delay_seconds)::numeric(8,2)             AS avg_delay_sec,
        COUNT(*)::int                                AS n_vehicles,
        (SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2)  AS pct_delayed
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at >= NOW() - INTERVAL '1 hour'
      AND latitude IS NOT NULL AND longitude IS NOT NULL
    GROUP BY 1, 2
),
velov_grid AS (
    SELECT
        ROUND(lat::numeric, 2)                       AS grid_lat,
        ROUND(lon::numeric, 2)                       AS grid_lon,
        SUM(num_bikes_available)::int                AS bikes_available,
        SUM(num_docks_available)::int                AS docks_available,
        COUNT(*)::int                                AS n_stations
    FROM silver.velov_clean
    WHERE fetched_at >= NOW() - INTERVAL '15 minutes'
      AND lat IS NOT NULL AND lon IS NOT NULL
    GROUP BY 1, 2
),
-- Météo courante : dernière heure <= maintenant (la table contient aussi les prévisions)
meteo AS (
    SELECT temperature_c, rain_mm
    FROM silver.meteo_hourly
    WHERE measurement_time <= NOW()
    ORDER BY measurement_time DESC
    LIMIT 1
)
SELECT
    COALESCE(t.grid_lat, c.grid_lat, v.grid_lat)    AS lat,
    COALESCE(t.grid_lon, c.grid_lon, v.grid_lon)    AS lon,
    COALESCE(t.avg_speed_kmh, 0)                    AS avg_speed_kmh,
    COALESCE(t.pct_congestion, 0)                   AS pct_congestion,
    COALESCE(t.n_sensors, 0)                        AS n_sensors,
    COALESCE(c.avg_delay_sec, 0)                    AS avg_delay_sec,
    COALESCE(c.pct_delayed, 0)                      AS pct_delayed,
    COALESCE(c.n_vehicles, 0)                       AS n_vehicles,
    COALESCE(v.bikes_available, 0)                  AS bikes_available,
    COALESCE(v.docks_available, 0)                  AS docks_available,
    COALESCE(v.n_stations, 0)                       AS n_stations,
    m.temperature_c,
    m.rain_mm,
    GREATEST(0, LEAST(10,
        0.5 * COALESCE(t.pct_congestion, 0) / 10.0
      + 0.5 * COALESCE(c.pct_delayed, 0) / 10.0
      - CASE WHEN COALESCE(v.bikes_available, 0) >= 5 THEN 1.0 ELSE 0.0 END
    ))::numeric(4,2)                                AS score_multimodal,
    CASE
        WHEN COALESCE(t.pct_congestion, 0) > 60
         AND COALESCE(c.pct_delayed, 0) > 40       THEN 'saturated'
        WHEN COALESCE(t.pct_congestion, 0) > 60     THEN 'road_congested'
        WHEN COALESCE(c.pct_delayed, 0) > 40       THEN 'transit_delayed'
        WHEN COALESCE(v.bikes_available, 0) < 3
         AND COALESCE(v.n_stations, 0) > 0          THEN 'velov_scarce'
        ELSE 'ok'
    END                                             AS diagnosis,
    NOW()                                           AS computed_at
FROM trafic_grid t
FULL OUTER JOIN tcl_grid c
    ON t.grid_lat = c.grid_lat AND t.grid_lon = c.grid_lon
FULL OUTER JOIN velov_grid v
    ON COALESCE(t.grid_lat, c.grid_lat) = v.grid_lat
   AND COALESCE(t.grid_lon, c.grid_lon) = v.grid_lon
CROSS JOIN meteo m
WHERE COALESCE(t.grid_lat, c.grid_lat, v.grid_lat) IS NOT NULL;

CREATE UNIQUE INDEX idx_mv_multimodal_grid_latlon ON gold.mv_multimodal_grid (lat, lon);
CREATE INDEX idx_mv_multimodal_grid_diagnosis ON gold.mv_multimodal_grid (diagnosis);
CREATE INDEX idx_mv_multimodal_grid_score ON gold.mv_multimodal_grid (score_multimodal DESC);

COMMENT ON MATERIALIZED VIEW gold.mv_multimodal_grid IS
    'Sprint 15+ (2026-06-19) — Grille multimodale 0.01° (~1 km) Lyon. Fusionne trafic (gold.traffic_features_live), TCL temps réel (gold.tcl_vehicle_realtime), Vélov (silver.velov_clean) et météo courante (silver.meteo_hourly, heure <= NOW() depuis la migration 055). Score multimodal 0-10 (haut = saturé) + diagnostic dominant. Refresh par le DAG transform_silver_to_gold. Source du widget Pro_TCL "multimodal_heatmap".';

COMMIT;
