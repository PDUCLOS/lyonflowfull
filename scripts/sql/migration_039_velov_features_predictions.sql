-- =============================================================================
-- LyonFlowFull — Migration 039 (Sprint P3.4, 2026-06-30)
-- =============================================================================
-- Versionnage explicite de gold.velov_features et gold.velov_predictions.
--
-- CONTEXTE :
--   Ces deux tables existaient dans scripts/migrate_realign_v0.3.1.sql
--   (migration de réconciliation schéma v0.3.1) mais n'avaient pas de fichier
--   de migration dédié dans scripts/sql/. En cas de recréation DB depuis zéro,
--   elles auraient été perdues.
--
--   Source de vérité : scripts/migrate_realign_v0.3.1.sql lignes 125-160.
--   Cette migration est idempotente (IF NOT EXISTS partout).
--
-- TABLES CRÉÉES :
--   gold.velov_features     — features ML Vélov (station_id encodé, temporel,
--                             météo, lags, rolling). Alimente le retrain XGBoost.
--   gold.velov_predictions  — prédictions H+60min (focus H+1h Sprint 8+).
--                             Colonnes : horizon_minutes, station_id, predicted_bikes.
--
-- APPLIQUER VIA :
--   psql -U lyonflow -d lyonflow -f scripts/sql/migration_039_velov_features_predictions.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. gold.velov_features
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.velov_features (
    id                  BIGSERIAL PRIMARY KEY,
    measurement_time    TIMESTAMPTZ NOT NULL,
    station_id          TEXT NOT NULL,
    station_id_encoded  INTEGER NOT NULL,
    num_bikes_available INTEGER,
    capacity            INTEGER,
    fill_ratio          REAL,
    hour_sin            REAL,
    hour_cos            REAL,
    day_sin             REAL,
    day_cos             REAL,
    is_vacances         BOOLEAN,
    is_ferie            BOOLEAN,
    rain_mm             REAL,
    temperature_c       REAL,
    lag_30min           REAL,
    lag_60min           REAL,
    rolling_mean_1h     REAL,
    CONSTRAINT gold_velov_feat_uniq UNIQUE (station_id, measurement_time)
);

CREATE INDEX IF NOT EXISTS idx_gold_velov_feat_time
    ON gold.velov_features (measurement_time DESC);

-- -----------------------------------------------------------------------------
-- 2. gold.velov_predictions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.velov_predictions (
    id                   BIGSERIAL PRIMARY KEY,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    target_timestamp     TIMESTAMPTZ NOT NULL,
    horizon_minutes      SMALLINT NOT NULL,
    station_id           TEXT NOT NULL,
    predicted_bikes      REAL,
    actual_bikes         REAL,
    model_name           TEXT,
    model_version        TEXT
);

CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_time
    ON gold.velov_predictions (prediction_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_station
    ON gold.velov_predictions (station_id, horizon_minutes);

-- -----------------------------------------------------------------------------
-- 3. Tracking
-- -----------------------------------------------------------------------------
INSERT INTO public.schema_migrations (version) VALUES (39)
ON CONFLICT (version) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 4. Verify
-- -----------------------------------------------------------------------------
SELECT
    to_regclass('gold.velov_features')::text    AS velov_features_exists,
    to_regclass('gold.velov_predictions')::text  AS velov_predictions_exists,
    version AS tracked
FROM public.schema_migrations
WHERE version = 39;
