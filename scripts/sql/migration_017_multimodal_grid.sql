-- =============================================================================
-- LyonFlowFull — Migration 17 (Sprint 15+, 2026-06-19)
-- =============================================================================
-- Vue matérialisée : gold.mv_multimodal_grid
--
-- Fusion multi-sources sur une grille spatiale 0.01° (~1 km) :
--   * gold.traffic_features_live  → vitesse moyenne, % congestion
--   * gold.tcl_vehicle_realtime   → retard moyen bus, % véhicules en retard
--   * silver.velov_clean          → vélos/docks disponibles
--   * silver.meteo_hourly         → température + précipitations (CROSS JOIN)
--
-- Score multimodal (0-10) :
--   score = clamp(0.5 * pct_congestion/10 + 0.5 * pct_delayed/10 - velov_bonus)
--   * velov_bonus = 1.0 si vélos dispo >= 5 dans la cellule (résilience)
--   * Plus le score est haut, plus la cellule est saturée
--
-- Diagnostic dominant (5 états) :
--   * saturated       : pct_congestion > 60 AND pct_delayed > 40
--   * road_congested  : pct_congestion > 60
--   * transit_delayed : pct_delayed > 40
--   * velov_scarce    : vélos < 3 et au moins 1 station
--   * ok              : reste
--
-- Refresh :
--   Toutes les 10 min par ``dags/transforms/transform_silver_to_gold.py``
--   (tâche ``refresh_mv_multimodal_grid`` ajoutée Sprint 15+).
--
-- Notes sur le schéma réel (vs spec d'origine) :
--   * ``silver.meteo_hourly.temperature_c`` et ``rain_mm``
--     (PAS ``temperature_2m`` / ``precipitation`` comme dans le spec —
--      le schéma effectif utilise des noms courts depuis Sprint VPS-3).
--   * ``gold.traffic_features_live`` a ``lat``/``lon`` (renommé depuis
--     ``measurement_time``/``node_idx`` en Sprint VPS-5).
--   * ``gold.tcl_vehicle_realtime`` a ``latitude``/``longitude`` et
--     ``recorded_at`` (1 ligne par véhicule, dernière position < 1h).
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW (pattern cohérent
-- avec les migrations 15 + create_mv_line_kpis_otp.sql).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : mv_multimodal_grid
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_multimodal_grid CASCADE;

CREATE MATERIALIZED VIEW gold.mv_multimodal_grid AS
WITH
-- Agrégation trafic routier par cellule 0.01°
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
-- Agrégation TCL par cellule 0.01° (1 véhicule = 1 ligne dans tcl_vehicle_realtime)
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
-- Agrégation Vélov par cellule 0.01° (15 min de fraîcheur = standard GBFS)
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
-- Météo courante (single row) — dernière mesure horaire dispo
meteo AS (
    SELECT temperature_c, rain_mm
    FROM silver.meteo_hourly
    ORDER BY measurement_time DESC
    LIMIT 1
)
SELECT
    COALESCE(t.grid_lat, c.grid_lat, v.grid_lat)    AS lat,
    COALESCE(t.grid_lon, c.grid_lon, v.grid_lon)    AS lon,
    -- Trafic
    COALESCE(t.avg_speed_kmh, 0)                    AS avg_speed_kmh,
    COALESCE(t.pct_congestion, 0)                   AS pct_congestion,
    COALESCE(t.n_sensors, 0)                        AS n_sensors,
    -- TCL
    COALESCE(c.avg_delay_sec, 0)                    AS avg_delay_sec,
    COALESCE(c.pct_delayed, 0)                      AS pct_delayed,
    COALESCE(c.n_vehicles, 0)                       AS n_vehicles,
    -- Vélov
    COALESCE(v.bikes_available, 0)                  AS bikes_available,
    COALESCE(v.docks_available, 0)                  AS docks_available,
    COALESCE(v.n_stations, 0)                       AS n_stations,
    -- Météo (CROSS JOIN → 1 valeur répétée par cellule)
    m.temperature_c,
    m.rain_mm,
    -- Score multimodal (0-10, haut = saturé)
    GREATEST(0, LEAST(10,
        0.5 * COALESCE(t.pct_congestion, 0) / 10.0
      + 0.5 * COALESCE(c.pct_delayed, 0) / 10.0
      - CASE WHEN COALESCE(v.bikes_available, 0) >= 5 THEN 1.0 ELSE 0.0 END
    ))::numeric(4,2)                                AS score_multimodal,
    -- Diagnostic textuel dominant
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

-- Index unique requis pour REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_multimodal_grid_latlon
    ON gold.mv_multimodal_grid (lat, lon);

-- Index secondaires pour les filtres dashboard
CREATE INDEX IF NOT EXISTS idx_mv_multimodal_grid_diagnosis
    ON gold.mv_multimodal_grid (diagnosis);
CREATE INDEX IF NOT EXISTS idx_mv_multimodal_grid_score
    ON gold.mv_multimodal_grid (score_multimodal DESC);

COMMENT ON MATERIALIZED VIEW gold.mv_multimodal_grid IS
    'Sprint 15+ (2026-06-19) — Grille multimodale 0.01° (~1 km) Lyon. '
    'Fusionne trafic (gold.traffic_features_live), TCL temps réel '
    '(gold.tcl_vehicle_realtime), Vélov (silver.velov_clean) et météo '
    '(silver.meteo_hourly) sur une seule vue. Score multimodal 0-10 '
    '(haut = saturé) + diagnostic dominant. Refresh toutes les 10 min par '
    'DAG transform_silver_to_gold. Source du widget Pro_TCL "multimodal_heatmap".';


-- =============================================================================
-- Vérification post-migration
-- =============================================================================
-- SELECT COUNT(*) AS cellules,
--        COUNT(*) FILTER (WHERE diagnosis = 'saturated')      AS saturees,
--        COUNT(*) FILTER (WHERE diagnosis = 'road_congested') AS route,
--        COUNT(*) FILTER (WHERE diagnosis = 'transit_delayed')AS tc,
--        COUNT(*) FILTER (WHERE diagnosis = 'velov_scarce')   AS velov,
--        COUNT(*) FILTER (WHERE diagnosis = 'ok')             AS ok,
--        ROUND(AVG(score_multimodal)::numeric, 2) AS score_moyen
-- FROM gold.mv_multimodal_grid;
--
-- Attendu après quelques jours : ~100-300 cellules sur Lyon intra-muros,
-- distribution dominée par 'ok' en heures creuses, 'saturated' aux heures
-- de pointe sur les grands axes.
