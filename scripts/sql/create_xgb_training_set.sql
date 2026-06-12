-- =============================================================================
-- LyonFlowFull — gold.xgb_training_set (training set materialisé pour XGBoost)
-- =============================================================================
-- Sprint 9+ (2026-06-12) — Sprint 8 (zéro mock + focus H+1h) démontrait
-- que la query ``_load_training_data()`` avec ``LEAD() OVER (...)`` sur
-- 2.4M rows de gold.traffic_features_live prenaît 11.5s en postgres
-- direct, et timeout depuis le container Streamlit.
--
-- Solution : matérialiser le target H+1h dans une table dédiée,
-- rafraîchie tous les jours à 02h30 par le DAG
-- ``build_xgb_training_set``. La query utilise un self-join sur
-- ``computed_at + INTERVAL '60 min'`` (indexable) au lieu d'un
-- window function sur 2.4M rows.
--
-- Schéma v0.3.1 de gold.traffic_features_live :
--   id, channel_id, fetched_at, computed_at, speed_kmh, vitesse_limite_kmh,
--   lag_1, lag_2, lag_3, delta_current, delta_1, rolling_mean_3,
--   hour_of_day, day_of_week, is_weekend, sin_hour, cos_hour,
--   sin_dow, cos_dow, channel_hash,
--   temperature_2m, precipitation, rain, is_raining, visibility,
--   wind_speed_10m, weather_code, lat, lon, importance_code,
--   x_2154, y_2154, is_vacances, is_ferie
--
-- FEATURE_COLS alignées (11 features) :
--   speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3,
--   sin_hour, cos_hour, temperature_2m, precipitation,
--   is_vacances, is_ferie
--
-- Cible : target_speed = speed_kmh de la même channel 60 min plus tard.
-- Les features (lag_1..3, rolling_mean_3) sont calculées à l'instant t
-- (par le DAG silver→gold). Le target est joint sur computed_at + 60min.
--
-- Idempotent : DROP IF EXISTS + CREATE.
-- =============================================================================

DROP TABLE IF EXISTS gold.xgb_training_set CASCADE;

CREATE TABLE gold.xgb_training_set (
    -- Identité
    feature_id              BIGSERIAL PRIMARY KEY,
    computed_at             TIMESTAMPTZ NOT NULL,
    target_computed_at      TIMESTAMPTZ NOT NULL,
    channel_id              TEXT NOT NULL,
    channel_hash            DOUBLE PRECISION,
    -- Cible
    target_speed            DOUBLE PRECISION NOT NULL,
    -- Features (11 alignées FEATURE_COLS)
    speed_kmh               DOUBLE PRECISION,
    lag_1                   DOUBLE PRECISION,
    lag_2                   DOUBLE PRECISION,
    lag_3                   DOUBLE PRECISION,
    rolling_mean_3          DOUBLE PRECISION,
    sin_hour                DOUBLE PRECISION,
    cos_hour                DOUBLE PRECISION,
    temperature_2m          DOUBLE PRECISION,
    precipitation           DOUBLE PRECISION,
    is_vacances             BOOLEAN,
    is_ferie                BOOLEAN,
    -- Métadonnées (pour debug / future sélection)
    lat                     DOUBLE PRECISION,
    lon                     DOUBLE PRECISION,
    importance_code         SMALLINT,
    created_at              TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Index essentiels (H+1h self-join + filter channel_id)
CREATE INDEX idx_xgb_train_channel_target_at
    ON gold.xgb_training_set (channel_id, target_computed_at DESC);
CREATE INDEX idx_xgb_train_computed_at
    ON gold.xgb_training_set (computed_at DESC);
CREATE INDEX idx_xgb_train_target_speed_not_null
    ON gold.xgb_training_set (target_computed_at)
    WHERE target_speed IS NOT NULL;

COMMENT ON TABLE gold.xgb_training_set IS
    'Training set materialisé pour XGBoost H+1h. Sprint 9+ (2026-06-12). '
    'Self-join sur computed_at + 60min au lieu de LEAD() sur 2.4M rows. '
    'Peuplé quotidiennement 02h30 par DAG build_xgb_training_set. '
    'Rétention 14 jours (auto-purge par le DAG).';
