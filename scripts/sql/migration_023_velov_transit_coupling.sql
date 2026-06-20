-- =============================================================================
-- Migration 023 — Sprint 17 Axe 4 : Vélov ↔ TC report modal
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.9.0 (cible)
-- Branche     : vps
-- Prérequis   : Sprint 8+ (silver.velov_clean + gold.tcl_vehicle_realtime)
--               PostGIS activé (ST_DWithin, ST_MakePoint, ST_SetSRID)
--
-- Crée :
--   gold.mv_velov_transit_coupling — Vue matérialisée : pour chaque station
--                                   Vélov située à < 300m d'une zone où
--                                   circule une ligne TC, calcule le z-score
--                                   (= combien d'écarts-types en dessous de
--                                   la moyenne horaire 7j) du nombre de
--                                   vélos disponibles.
--                                   Si z_score < -2 → anomaly_detected = TRUE
--                                   → alerte "report modal" probable.
--
-- Détection :
--   * Plusieurs stations Vélov proches d'une MÊME ligne TC en alarme
--     simultanée = probable incident sur cette ligne (panne métro, tram
--     interrompu, etc.) qui fait basculer les usagers vers le Vélov.
--
-- Notes sur le schéma réel (vs spec d'origine) :
--   * La spec originale utilisait ``referentiel.lieux_transports`` comme
--     référentiel des arrêts TCL. Mais ce référentiel n'a PAS de colonnes
--     lat/lon (Sprint VPS-6 : id, lieu_id, line_ref, line_mode, stop_name,
--     distance_m, rank, is_active, source). On ne peut pas faire un JOIN
--     spatial PostGIS dessus.
--   * Sprint 17 (2026-06-20) — révisé après retour utilisateur : on prend
--     les **positions GPS individuelles des véhicules TCL**
--     (``gold.tcl_vehicle_realtime``) dédupliquées par tuile
--     ROUND(lat/lon, 3) ≈ 100 m (cohérent avec migration_018, même
--     résolution 0.001°). Chaque véhicule = un point TC réel, on garde
--     la couverture spatiale effective de la ligne (~100-200 véhicules
--     en 15 min → cardinality gérable pour ST_DWithin).
--   * Avantage vs centroïde AVG : couverture spatiale réelle (pas un
--     point fictif), ST_DWithin 300m devient signifiant, pas de
--     nouvelle table de schéma.
--   * Limite connue : biais horaire nuit/dimanche (peu de véhicules =
--     faux négatifs). Acceptable pour l'alerte report modal — s'il n'y
--     a pas de bus la nuit, il n'y a pas de report modal non plus.
--   * Le rayon 300m reste celui de la spec : marche à pied ~3-4 min entre
--     la station Vélov et le véhicule TC.
--
-- Refresh :
--   Toutes les 15 min par ``dags/maintenance/refresh_velov_transit_coupling.py``
--   (REFRESH MATERIALIZED VIEW CONCURRENTLY, donc index unique requis).
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW + index unique.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : mv_velov_transit_coupling
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_velov_transit_coupling CASCADE;

CREATE MATERIALIZED VIEW gold.mv_velov_transit_coupling AS
WITH
-- Stations Vélov : dernière position connue + vélos dispos (15 min)
velov_latest AS (
    SELECT DISTINCT ON (vc.station_id)
        vc.station_id,
        vc.station_name,
        vc.lat,
        vc.lon,
        vc.num_bikes_available,
        vc.fetched_at
    FROM silver.velov_clean vc
    WHERE vc.fetched_at > NOW() - INTERVAL '15 minutes'
      AND vc.lat IS NOT NULL
      AND vc.lon IS NOT NULL
      AND vc.is_active = TRUE
    ORDER BY vc.station_id, vc.fetched_at DESC
),
-- Zones TC : positions GPS directes (1 ligne par tuile lat/lon ~100m par ligne)
-- Dédup via ROUND(lat/lon, 3) ≈ 100 m (cohérent avec migration_018, résolution
-- 0.001°). Chaque véhicule = un point TC réel, on garde la couverture spatiale
-- effective de la ligne. Évite le piège du centroïde AVG qui produit un point
-- fictif au milieu de la ligne.
tcl_zones AS (
    SELECT DISTINCT ON (line_ref, ROUND(latitude::numeric, 3), ROUND(longitude::numeric, 3))
        line_ref,
        latitude                                         AS line_lat,
        longitude                                        AS line_lon,
        1                                                AS n_vehicles
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '15 minutes'
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
    ORDER BY
        line_ref,
        ROUND(latitude::numeric, 3),
        ROUND(longitude::numeric, 3),
        recorded_at DESC
),
-- Stations Vélov dans un rayon 300m d'une zone TC
velov_near_transit AS (
    SELECT
        vl.station_id,
        vl.station_name,
        vl.num_bikes_available,
        vl.lat                                          AS station_lat,
        vl.lon                                          AS station_lon,
        tz.line_ref                                     AS transit_line,
        tz.n_vehicles                                   AS transit_n_vehicles,
        ST_Distance(
            ST_SetSRID(ST_MakePoint(vl.lon, vl.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(tz.line_lon, tz.line_lat), 4326)::geography
        )::int                                          AS distance_to_line_m
    FROM velov_latest vl
    JOIN tcl_zones tz
      ON ST_DWithin(
            ST_SetSRID(ST_MakePoint(vl.lon, vl.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(tz.line_lon, tz.line_lat), 4326)::geography,
            300  -- mètres
         )
),
-- Baseline horaire 7j : moyenne + stddev vélos dispos par (station_id, hour_of_day)
velov_baseline AS (
    SELECT
        vc.station_id,
        EXTRACT(HOUR FROM vc.fetched_at AT TIME ZONE 'Europe/Paris')::int AS hour_of_day,
        AVG(vc.num_bikes_available)::numeric(6,2)      AS avg_bikes,
        STDDEV(vc.num_bikes_available)::numeric(6,2)   AS std_bikes,
        COUNT(*)::int                                  AS n_obs
    FROM silver.velov_clean vc
    WHERE vc.fetched_at > NOW() - INTERVAL '7 days'
      AND vc.num_bikes_available IS NOT NULL
    GROUP BY vc.station_id, EXTRACT(HOUR FROM vc.fetched_at AT TIME ZONE 'Europe/Paris')
)
SELECT
    vnt.station_id,
    vnt.station_name,
    vnt.transit_line,
    vnt.transit_n_vehicles,
    vnt.station_lat,
    vnt.station_lon,
    vnt.distance_to_line_m,
    vnt.num_bikes_available                            AS bikes_now,
    vb.avg_bikes                                       AS baseline_avg_bikes,
    vb.std_bikes                                       AS baseline_std_bikes,
    vb.n_obs                                           AS baseline_n_obs,
    vb.hour_of_day,
    -- Z-score : combien d'écarts-types en dessous de la moyenne ?
    CASE WHEN vb.std_bikes IS NOT NULL AND vb.std_bikes > 0
         THEN ROUND(((vnt.num_bikes_available - vb.avg_bikes) / vb.std_bikes)::numeric, 2)
         ELSE NULL
    END                                                AS z_score,
    -- Alerte si z_score < -2 (anormalement vide)
    CASE WHEN vb.std_bikes IS NOT NULL AND vb.std_bikes > 0
              AND (vnt.num_bikes_available - vb.avg_bikes) / vb.std_bikes < -2.0
         THEN TRUE
         ELSE FALSE
    END                                                AS anomaly_detected,
    NOW()                                              AS computed_at
FROM velov_near_transit vnt
LEFT JOIN velov_baseline vb
       ON vb.station_id = vnt.station_id
      AND vb.hour_of_day = EXTRACT(HOUR FROM NOW() AT TIME ZONE 'Europe/Paris')::int
WHERE vnt.num_bikes_available IS NOT NULL
ORDER BY
    anomaly_detected DESC,        -- anomalies en premier
    z_score ASC NULLS LAST;       -- puis z-score les plus négatifs

-- Index unique sur (station_id, transit_line) : permet REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_gold_mv_velov_transit_coupling_pk
    ON gold.mv_velov_transit_coupling (station_id, transit_line);

-- Index secondaire sur transit_line (filtre widget "par ligne TC")
CREATE INDEX IF NOT EXISTS idx_gold_mv_velov_transit_coupling_line
    ON gold.mv_velov_transit_coupling (transit_line);

-- Index secondaire sur anomaly_detected (compteur KPI)
CREATE INDEX IF NOT EXISTS idx_gold_mv_velov_transit_coupling_anomaly
    ON gold.mv_velov_transit_coupling (anomaly_detected)
    WHERE anomaly_detected = TRUE;

COMMENT ON MATERIALIZED VIEW gold.mv_velov_transit_coupling IS
    'Sprint 17 Axe 4 — Couplage Vélov ↔ TC : z-score vélos dispos par station
     Vélov situee a < 300m d''une zone TC (positions GPS gold.tcl_vehicle_realtime).
     z_score < -2 -> anomaly_detected = TRUE (alerte report modal).
     Sert au widget modal_shift_alert (Pro_3_Correlation) pour detecter les
     incidents TC qui font basculer les usagers vers le Velov.
     Refresh */15 min par dags/maintenance/refresh_velov_transit_coupling.py.
     Spec : docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §5.';

-- Permissions
GRANT SELECT ON gold.mv_velov_transit_coupling TO PUBLIC;
