-- =============================================================================
-- Migration 020 — Sprint 16 Axe A : TomTom Niveau 2 — Backtest Engine
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.8.0
-- Branche     : main
-- Prérequis   : Sprint 13+ (v0.6.7, migration 14 — gold.v_tomtom_traffic_live)
--               Sprint 15+ (v0.7.1, gold.trafic_predictions schéma H+1h)
--
-- Crée :
--   1. gold.mv_xgb_vs_tomtom   — MV : paires (prédiction XGBoost, obs TomTom)
--                                  jointes spatialement (ST_DWithin 200m) et
--                                  temporellement (±10 min).
--   2. gold.v_xgb_accuracy_summary — Vue simple : MAE/MAPE/P90 par heure.
--   3. 2 index sur la MV pour les requêtes dashboard.
--
-- Refresh : toutes les 30 min (DAG refresh_xgb_vs_tomtom, Sprint 16).
-- =============================================================================

-- Drop safe (idempotent si rejoué après evolution du schéma)
DROP MATERIALIZED VIEW IF EXISTS gold.mv_xgb_vs_tomtom CASCADE;

CREATE MATERIALIZED VIEW gold.mv_xgb_vs_tomtom AS
WITH pred AS (
    -- Prédictions XGBoost H+1h les plus récentes par axis_key
    -- (filtrées sur horizon_h=1 = H+1h, focus Sprint 8+)
    SELECT
        axis_key,
        calculated_at,
        speed_pred,
        etat_pred,
        lat,
        lon,
        model_version
    FROM gold.trafic_predictions
    WHERE horizon_h = 1
      AND calculated_at > NOW() - INTERVAL '7 days'
),
tomtom AS (
    -- Observations TomTom par tuile (current_speed_kmh = vitesse GPS flottes)
    -- Note : on utilise v_tomtom_traffic_live (vue créée Sprint 13+) qui
    -- prend la dernière valeur par tile_key (DISTINCT ON).
    SELECT
        tile_key,
        fetched_at,
        current_speed_kmh AS tomtom_speed_kmh,
        free_flow_speed_kmh,
        confidence,
        lat AS lat_center,
        lon AS lon_center
    FROM gold.v_tomtom_traffic_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
)
SELECT
    p.axis_key,
    p.calculated_at,
    p.speed_pred   AS xgb_speed_kmh,
    t.tomtom_speed_kmh,
    t.free_flow_speed_kmh,
    ABS(p.speed_pred - t.tomtom_speed_kmh)    AS error_abs_kmh,
    CASE
        WHEN t.tomtom_speed_kmh > 0
        THEN ABS(p.speed_pred - t.tomtom_speed_kmh) / t.tomtom_speed_kmh * 100
        ELSE NULL
    END AS error_pct,
    t.confidence AS tomtom_confidence,
    p.model_version,
    p.etat_pred,
    p.lat AS pred_lat,
    p.lon AS pred_lon,
    t.tile_key,
    t.fetched_at AS tomtom_fetched_at,
    -- Diagnostic accuracy band (cf SPEC_SPRINT_16.md §A.1)
    CASE
        WHEN ABS(p.speed_pred - t.tomtom_speed_kmh) < 5  THEN 'accurate'
        WHEN ABS(p.speed_pred - t.tomtom_speed_kmh) < 15 THEN 'acceptable'
        ELSE 'poor'
    END AS accuracy_band
FROM pred p
JOIN tomtom t
  ON ST_DWithin(
       ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
       ST_SetSRID(ST_MakePoint(t.lon_center, t.lat_center), 4326)::geography,
       200  -- 200 m (même seuil que cohérence Sprint 13+, migration 14)
     )
  AND t.fetched_at BETWEEN p.calculated_at - INTERVAL '10 minutes'
                        AND p.calculated_at + INTERVAL '10 minutes'
WITH DATA;

COMMENT ON MATERIALIZED VIEW gold.mv_xgb_vs_tomtom IS
    'Sprint 16 Axe A — Paires (prédiction XGBoost H+1h, observation TomTom Flow)
     jointes spatialement (ST_DWithin 200m) et temporellement (±10 min).
     Sert au widget Pro_7_Model_Monitoring::backtest_dashboard et au détecteur
     de drift Evidently. Refresh toutes les 30 min par le DAG refresh_xgb_vs_tomtom.
     Note : on a abandonné prediction_timestamp (legacy Sprint 5) pour
     calculated_at (schéma v0.3.1).';

-- Index pour les requêtes dashboard
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_calculated
    ON gold.mv_xgb_vs_tomtom (calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_accuracy
    ON gold.mv_xgb_vs_tomtom (accuracy_band);
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_axis
    ON gold.mv_xgb_vs_tomtom (axis_key, calculated_at DESC);

-- -----------------------------------------------------------------------------
-- Vue agrégée (pas matérialisée) pour les KPIs dashboard
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_xgb_accuracy_summary AS
SELECT
    date_trunc('hour', calculated_at) AS hour_bucket,
    COUNT(*)                          AS n_pairs,
    AVG(error_abs_kmh)                AS mae_kmh,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY error_abs_kmh) AS median_error_kmh,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY error_abs_kmh) AS p90_error_kmh,
    AVG(error_pct) FILTER (WHERE error_pct IS NOT NULL) AS mape_pct,
    COUNT(*) FILTER (WHERE accuracy_band = 'accurate')   AS n_accurate,
    COUNT(*) FILTER (WHERE accuracy_band = 'acceptable') AS n_acceptable,
    COUNT(*) FILTER (WHERE accuracy_band = 'poor')       AS n_poor,
    AVG(tomtom_confidence) AS avg_tomtom_confidence
FROM gold.mv_xgb_vs_tomtom
GROUP BY 1
ORDER BY 1 DESC;

COMMENT ON VIEW gold.v_xgb_accuracy_summary IS
    'Sprint 16 Axe A — KPIs agrégés par heure (MAE, MAPE, P90, distribution
     accuracy_band) calculés depuis gold.mv_xgb_vs_tomtom. Sert au widget
     backtest_dashboard pour la courbe MAE temporelle et le pie distribution.';

-- Permissions (alignement sur les autres vues Gold)
GRANT SELECT ON gold.mv_xgb_vs_tomtom TO PUBLIC;
GRANT SELECT ON gold.v_xgb_accuracy_summary TO PUBLIC;
