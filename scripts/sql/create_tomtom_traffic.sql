-- =============================================================================
-- LyonFlowFull — TomTom Traffic (Sprint VPS-6, 2026-06-11)
-- =============================================================================
-- Table Bronze qui stocke les snapshots TomTom Flow (1 par tuile 0.02°,
-- 12 tuiles utiles de Lyon). Table append-only, déduplication sur
-- (tile_key, fetched_at).
--
-- Vue Gold qui agrège la dernière valeur TomTom par tuile, avec calcul
-- d'un "traffic_state" lissé (fluide/modéré/dense/bloqué).
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + CREATE OR REPLACE VIEW.
-- =============================================================================

CREATE TABLE IF NOT EXISTS bronze.tomtom_traffic (
    id                      BIGSERIAL PRIMARY KEY,
    lat                     DOUBLE PRECISION NOT NULL,
    lon                     DOUBLE PRECISION NOT NULL,
    current_speed_kmh       DOUBLE PRECISION NOT NULL,
    free_flow_speed_kmh     DOUBLE PRECISION NOT NULL,
    ratio                   DOUBLE PRECISION NOT NULL,       -- current/free_flow (1.0 = fluide, 0.5 = ralenti)
    confidence              DOUBLE PRECISION NOT NULL,       -- 0..1, TomTom
    current_travel_time_s   INTEGER NOT NULL,
    free_flow_travel_time_s INTEGER NOT NULL,
    tile_key                TEXT NOT NULL,                    -- ex: '45.7600_4.8500'
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_data                JSONB,                            -- payload complet TomTom (debug)
    UNIQUE (tile_key, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_tomtom_tile_fetched
    ON bronze.tomtom_traffic (tile_key, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_tomtom_fetched_brin
    ON bronze.tomtom_traffic USING brin (fetched_at);

COMMENT ON TABLE bronze.tomtom_traffic IS
    'Sprint VPS-6 (2026-06-11) — Snapshots TomTom Traffic Flow (free tier 2500 req/jour, '
    'collecte via DAG collect_tomtom_traffic toutes les 15 min sur 12 tuiles Lyon). '
    'Source = TomTom Flow Segment API. Cache 5min par tuile côté ingest.';

-- Vue Gold : dernier snapshot par tuile, avec état lissé
CREATE OR REPLACE VIEW gold.v_tomtom_traffic_live AS
SELECT DISTINCT ON (tile_key)
    tile_key,
    lat,
    lon,
    current_speed_kmh,
    free_flow_speed_kmh,
    ratio,
    confidence,
    current_travel_time_s,
    free_flow_travel_time_s,
    fetched_at,
    -- État lissé (cohérent avec gold.trafic_predictions.etat_pred)
    CASE
        WHEN ratio >= 0.85 THEN 'fluide'
        WHEN ratio >= 0.60 THEN 'modéré'
        WHEN ratio >= 0.35 THEN 'dense'
        ELSE 'bloqué'
    END AS etat,
    -- Couleur pour carte
    CASE
        WHEN ratio >= 0.85 THEN '#4CAF50'   -- vert
        WHEN ratio >= 0.60 THEN '#FF9800'   -- orange
        WHEN ratio >= 0.35 THEN '#F44336'   -- rouge
        ELSE '#B71C1C'                       -- rouge foncé
    END AS color
FROM bronze.tomtom_traffic
WHERE fetched_at >= NOW() - INTERVAL '24 hours'
ORDER BY tile_key, fetched_at DESC;

COMMENT ON VIEW gold.v_tomtom_traffic_live IS
    'Dernier snapshot TomTom Flow par tuile (24h glissantes). Utilisé par la carte '
    'trafic du dashboard (Mon Trajet) en complément de gold.trafic_predictions.';

-- Vue fusion Gold capteurs + TomTom (priorité Gold live < 5min, puis TomTom)
CREATE OR REPLACE VIEW gold.v_traffic_combined AS
WITH gold_live AS (
    -- Capteurs Grand Lyon des 5 dernières minutes, par axis_key (= channel_id)
    SELECT DISTINCT ON (channel_id)
        channel_id, lat, lon, speed_kmh, computed_at
    FROM gold.traffic_features_live
    WHERE computed_at >= NOW() - INTERVAL '5 minutes'
    ORDER BY channel_id, computed_at DESC
),
gold_pred AS (
    -- Prédictions H+1h (Sprint VPS-5) par axis_key
    SELECT DISTINCT ON (axis_key)
        axis_key AS channel_id, lat, lon, speed_pred, calculated_at
    FROM gold.trafic_predictions
    WHERE horizon_h = 1
    ORDER BY axis_key, calculated_at DESC
),
tomtom_live AS (
    SELECT tile_key, lat, lon, current_speed_kmh AS speed_kmh, ratio, fetched_at
    FROM gold.v_tomtom_traffic_live
)
-- Chaque capteur Gold a (live, sinon pred, sinon tomtom)
SELECT
    g.channel_id,
    g.lat,
    g.lon,
    g.speed_kmh,
    g.computed_at,
    'gold_live'::TEXT AS source,
    1.0 AS confidence
FROM gold_live g
UNION ALL
SELECT
    p.channel_id,
    p.lat,
    p.lon,
    p.speed_pred AS speed_kmh,
    p.calculated_at AS computed_at,
    'gold_pred'::TEXT,
    0.7 AS confidence
FROM gold_pred p
WHERE p.channel_id NOT IN (SELECT channel_id FROM gold_live)
UNION ALL
SELECT
    'TT_' || t.tile_key AS channel_id,
    t.lat,
    t.lon,
    t.speed_kmh,
    t.fetched_at AS computed_at,
    'tomtom'::TEXT,
    t.ratio AS confidence
FROM tomtom_live t;

COMMENT ON VIEW gold.v_traffic_combined IS
    'Vue unifiée trafic : priorité gold_live (capteurs <5min) > gold_pred (H+1h) > tomtom '
    '(zones sans capteur). Sprint VPS-6 : permet à la carte dashboard d''afficher du trafic '
    'temps réel partout à Lyon, y compris hors couverture des boucles Grand Lyon.';
