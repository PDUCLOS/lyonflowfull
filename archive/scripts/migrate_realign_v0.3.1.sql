-- =============================================================================
-- LyonFlowFull — Realignement schema v0.3.1
-- =============================================================================
-- Objectif : aligner le schema DB avec le modele attendu par le code
-- (CLAUDE.md + db_query.py + collecteurs).
--
-- Securite :
-- - IF NOT EXISTS / IF EXISTS partout
-- - Aucune suppression de donnees existantes
-- - TomTom CONSERVE (controle de coherence cross-source)
-- - Idempotent : peut etre re-execute sans danger
--
-- Application :
--   docker exec lyonflow-postgres psql -U lyonflow -d lyonflow \
--     -f /opt/lyonflow/scripts/migrate_realign_v0.3.1.sql
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. BRONZE — Ajout colonne raw_data manquante (debloque collecteurs)
-- -----------------------------------------------------------------------------
-- Les collecteurs base.py font INSERT INTO bronze.X (fetched_at, raw_data).
-- Sans cette colonne, meteo + air_quality + velov plantent a chaque ingestion.

ALTER TABLE bronze.meteo       ADD COLUMN IF NOT EXISTS raw_data JSONB;
ALTER TABLE bronze.air_quality ADD COLUMN IF NOT EXISTS raw_data JSONB;
ALTER TABLE bronze.velov       ADD COLUMN IF NOT EXISTS raw_data JSONB;

-- Index sur fetched_at (deja present sur la plupart, idempotent)
CREATE INDEX IF NOT EXISTS idx_bronze_meteo_fetched_at       ON bronze.meteo (fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_bronze_air_quality_fetched_at ON bronze.air_quality (fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_bronze_velov_fetched_at       ON bronze.velov (fetched_at DESC);

-- -----------------------------------------------------------------------------
-- 2. SILVER — Tables propres manquantes
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.tcl_vehicles_clean (
    id              BIGSERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL,
    measurement_time TIMESTAMPTZ NOT NULL,
    line_ref        TEXT NOT NULL,
    direction_ref   TEXT,
    journey_ref     TEXT,
    stop_ref        TEXT,
    delay_seconds   INTEGER,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    raw_data        JSONB,
    CONSTRAINT silver_tcl_uniq UNIQUE (line_ref, journey_ref, stop_ref, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_silver_tcl_line_time ON silver.tcl_vehicles_clean (line_ref, measurement_time DESC);

CREATE TABLE IF NOT EXISTS silver.velov_clean (
    id                  BIGSERIAL PRIMARY KEY,
    fetched_at          TIMESTAMPTZ NOT NULL,
    measurement_time    TIMESTAMPTZ NOT NULL,
    station_id          TEXT NOT NULL,
    station_name        TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    is_active           BOOLEAN DEFAULT TRUE,
    CONSTRAINT silver_velov_uniq UNIQUE (station_id, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_silver_velov_station_time ON silver.velov_clean (station_id, measurement_time DESC);

CREATE TABLE IF NOT EXISTS silver.chantiers_actifs (
    id              BIGSERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL,
    chantier_id     TEXT NOT NULL,
    titre           TEXT,
    description     TEXT,
    date_debut      DATE,
    date_fin        DATE,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    is_active       BOOLEAN GENERATED ALWAYS AS (
        date_debut <= CURRENT_DATE AND (date_fin IS NULL OR date_fin >= CURRENT_DATE)
    ) STORED,
    raw_data        JSONB,
    CONSTRAINT silver_chantiers_uniq UNIQUE (chantier_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_silver_chantiers_active ON silver.chantiers_actifs (is_active, date_fin);

-- -----------------------------------------------------------------------------
-- 3. GOLD — Tables Bus + Velov manquantes
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.bus_delay_segments (
    id                  BIGSERIAL PRIMARY KEY,
    line_ref            TEXT NOT NULL,
    segment_id          TEXT NOT NULL,
    hour_of_day         SMALLINT,
    day_of_week         SMALLINT,
    is_vacances         BOOLEAN,
    is_ferie            BOOLEAN,
    weather_code        INTEGER,
    avg_delay_seconds   REAL,
    p90_delay_seconds   REAL,
    n_observations      INTEGER,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT gold_bus_delay_uniq UNIQUE (line_ref, segment_id, hour_of_day, day_of_week)
);
CREATE INDEX IF NOT EXISTS idx_gold_bus_delay_line ON gold.bus_delay_segments (line_ref);

CREATE TABLE IF NOT EXISTS gold.infrastructure_bottlenecks (
    id                  BIGSERIAL PRIMARY KEY,
    segment_id          TEXT NOT NULL,
    line_ref            TEXT,
    diagnosis           TEXT NOT NULL,  -- 'infra' | 'operations' | 'bus_lane_ok' | 'ok'
    bus_delay_seconds   REAL,
    traffic_speed_kmh   REAL,
    traffic_congestion  REAL,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    n_observations      INTEGER,
    CONSTRAINT gold_infra_uniq UNIQUE (segment_id, line_ref, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_gold_infra_diagnosis ON gold.infrastructure_bottlenecks (diagnosis);

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
CREATE INDEX IF NOT EXISTS idx_gold_velov_feat_time ON gold.velov_features (measurement_time DESC);

CREATE TABLE IF NOT EXISTS gold.velov_predictions (
    id                  BIGSERIAL PRIMARY KEY,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    target_timestamp    TIMESTAMPTZ NOT NULL,
    horizon_minutes     SMALLINT NOT NULL,  -- 30 ou 60
    station_id          TEXT NOT NULL,
    predicted_bikes     REAL,
    actual_bikes        REAL,
    model_name          TEXT,
    model_version       TEXT
);
CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_time ON gold.velov_predictions (prediction_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_station ON gold.velov_predictions (station_id, horizon_minutes);

-- -----------------------------------------------------------------------------
-- 4. GOLD — Vue coherence TomTom vs Grand Lyon (cross-validation)
-- -----------------------------------------------------------------------------
-- Compare la vitesse TomTom (current_speed_kmh) avec la vitesse Grand Lyon
-- (trafic_boucles) sur les memes zones et fenetres de temps. Permet de
-- detecter si une source devie (capteur HS, API stale, etc.)
--
-- Si NULL des deux cotes => zone sans coverage
-- Si ecart > 20 km/h => anomalie a investiguer

CREATE OR REPLACE VIEW gold.v_coherence_tomtom_vs_grandlyon AS
SELECT
    DATE_TRUNC('hour', tt.collected_at) AS window_hour,
    tt.point_name,
    tt.query_lat,
    tt.query_lon,
    AVG(tt.current_speed_kmh) AS tomtom_speed_avg,
    AVG(tt.free_flow_speed_kmh) AS tomtom_freeflow_avg,
    AVG(tt.ratio_congestion) AS tomtom_congestion_avg,
    COUNT(*) AS n_tomtom_obs
FROM bronze.tomtom_flow tt
WHERE tt.collected_at >= NOW() - INTERVAL '7 days'
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2;

-- Note : le join precis avec trafic_boucles necessite un mapping spatial
-- (channel_id <-> point TomTom). A faire dans une migration ulterieure
-- une fois que le mapping est defini (probable: ST_DWithin sur geom).

-- -----------------------------------------------------------------------------
-- 8. BRONZE — tcl_vehicles : relâcher contraintes (collector stocke blob JSON)
-- -----------------------------------------------------------------------------
-- Le collecteur _save_raw insère 1 row par fetch avec raw_data JSONB entier.
-- Le parse en silver.tcl_vehicles_clean extrait vehicle_ref depuis raw_data.
-- D'où DROP NOT NULL + DROP unique constraint historique.
ALTER TABLE bronze.tcl_vehicles ALTER COLUMN vehicle_ref DROP NOT NULL;
ALTER TABLE bronze.tcl_vehicles DROP CONSTRAINT IF EXISTS tcl_vehicles_fetched_at_vehicle_ref_key;

COMMIT;

-- =============================================================================
-- Verification post-migration
-- =============================================================================
-- A executer apres COMMIT pour valider :
--
-- SELECT 'bronze.meteo.raw_data', column_name FROM information_schema.columns
-- WHERE table_schema='bronze' AND table_name='meteo' AND column_name='raw_data';
--
-- SELECT table_schema, table_name FROM information_schema.tables
-- WHERE (table_schema='silver' AND table_name IN ('tcl_vehicles_clean','velov_clean','chantiers_actifs'))
--    OR (table_schema='gold'   AND table_name IN ('bus_delay_segments','infrastructure_bottlenecks','velov_features','velov_predictions'))
-- ORDER BY table_schema, table_name;