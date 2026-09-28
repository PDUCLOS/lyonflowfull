-- =============================================================================
-- Migration 051 — Évaluation XGBoost H+1h contre la vitesse observée Grand Lyon (Sprint 26, 2026-09-28)
-- =============================================================================
-- Pourquoi cette migration existe :
-- ``gold.mv_xgb_vs_tomtom`` (migration 020) comparait chaque prédiction H+1h à
-- ``gold.v_tomtom_traffic_live``. Deux défauts :
--   1. Dépendance à TomTom : la clé API est rejetée (HTTP 403) depuis le
--      2026-09-23, ``bronze.tomtom_traffic`` est vide → MV vide → page Usager
--      « Notre modèle » et carte « Modèle » de Usager_5 bloquées sur
--      « Indéterminé — pas encore 7 jours d'historique de production ».
--   2. ``v_tomtom_traffic_live`` ne garde que le DERNIER point par tuile sur
--      24 h (DISTINCT ON) : la fenêtre « 7 jours » de la MV n'a jamais pu
--      contenir plus que les ~10 dernières minutes de paires. Et la jointure
--      ±10 min autour de ``calculated_at`` comparait une prédiction H+1h à la
--      vitesse de l'instant de calcul, pas à celle de l'heure prédite.
--
-- Cette migration redéfinit la MV avec la vérité terrain du projet :
-- ``gold.traffic_features_live.speed_kmh`` (boucles Grand Lyon, même
-- ``channel_id`` que ``trafic_predictions.axis_key``), observée à
-- ``calculated_at + 1 h`` (point le plus proche dans ±10 min).
-- Mesuré sur le VPS le 2026-09-28 : 96 k paires / 24 h, MAE 2,29 km/h.
--
-- Compatibilité : nom de la MV et liste de colonnes inchangés (widget
-- backtest_dashboard, drift_detector, v_xgb_accuracy_summary).
-- ``tomtom_speed_kmh`` contient désormais la vitesse observée de référence ;
-- ``tomtom_confidence`` est NULL ; ``reference_source`` = 'grandlyon'.
-- Idempotent : DROP ... IF EXISTS CASCADE puis recréation.
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS gold.mv_xgb_vs_tomtom CASCADE;

CREATE MATERIALIZED VIEW gold.mv_xgb_vs_tomtom AS
SELECT
    p.axis_key,
    p.calculated_at,
    p.speed_pred                                   AS xgb_speed_kmh,
    o.speed_kmh                                    AS tomtom_speed_kmh,
    NULL::double precision                         AS free_flow_speed_kmh,
    abs(p.speed_pred::double precision - o.speed_kmh) AS error_abs_kmh,
    CASE
        WHEN o.speed_kmh > 0
            THEN abs(p.speed_pred::double precision - o.speed_kmh) / o.speed_kmh * 100
        ELSE NULL
    END                                            AS error_pct,
    NULL::double precision                         AS tomtom_confidence,
    p.model_version,
    p.etat_pred,
    p.lat                                          AS pred_lat,
    p.lon                                          AS pred_lon,
    NULL::text                                     AS tile_key,
    o.fetched_at                                   AS tomtom_fetched_at,
    CASE
        WHEN abs(p.speed_pred::double precision - o.speed_kmh) < 5  THEN 'accurate'
        WHEN abs(p.speed_pred::double precision - o.speed_kmh) < 15 THEN 'acceptable'
        ELSE 'poor'
    END                                            AS accuracy_band,
    'grandlyon'::text                              AS reference_source
FROM gold.trafic_predictions p
JOIN LATERAL (
    SELECT f.speed_kmh::double precision AS speed_kmh, f.fetched_at
    FROM gold.traffic_features_live f
    WHERE f.channel_id = p.axis_key
      AND f.fetched_at BETWEEN p.calculated_at + INTERVAL '50 minutes'
                           AND p.calculated_at + INTERVAL '70 minutes'
      AND f.speed_kmh IS NOT NULL
    ORDER BY abs(extract(epoch FROM f.fetched_at - (p.calculated_at + INTERVAL '1 hour')))
    LIMIT 1
) o ON true
WHERE p.horizon_h = 1
  AND p.calculated_at > NOW() - INTERVAL '7 days'
WITH DATA;

COMMENT ON MATERIALIZED VIEW gold.mv_xgb_vs_tomtom IS
    'Migration 051 — Paires (prédiction XGBoost H+1h, vitesse observée Grand Lyon
     à calculated_at + 1 h ±10 min, même channel_id). Nom historique conservé
     (ex-TomTom, migration 020) pour compatibilité : tomtom_speed_kmh = vitesse
     observée de référence, reference_source = grandlyon. Refresh par le DAG
     refresh_xgb_vs_tomtom.';

-- UNIQUE requis pour REFRESH ... CONCURRENTLY (pas de lock lecteurs pendant
-- le refresh). trafic_predictions a pour PK (axis_key, horizon_h, calculated_at)
-- et horizon_h est filtré à 1 → (axis_key, calculated_at) est unique.
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_xgb_vs_tomtom_axis_calc
    ON gold.mv_xgb_vs_tomtom (axis_key, calculated_at);
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_calculated
    ON gold.mv_xgb_vs_tomtom (calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_accuracy
    ON gold.mv_xgb_vs_tomtom (accuracy_band);

-- Vue agrégée recréée à l'identique (supprimée par le CASCADE)
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
    'KPIs agrégés par heure (MAE, MAPE, P90, distribution accuracy_band) depuis
     gold.mv_xgb_vs_tomtom (référence Grand Lyon depuis migration 051).';

GRANT SELECT ON gold.mv_xgb_vs_tomtom TO PUBLIC;
GRANT SELECT ON gold.v_xgb_accuracy_summary TO PUBLIC;
