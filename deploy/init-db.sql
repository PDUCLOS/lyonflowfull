-- =============================================================================
-- LyonFlowFull — Initialisation base de données
-- =============================================================================
-- Schéma Bronze / Silver / Gold (architecture Medallion)
-- + Schéma RGPD (consentement, audit)
-- + Schéma governance (data dictionary, lineage)
-- + Schéma Airflow (créé automatiquement par Airflow)
-- + Schéma MLflow (créé automatiquement par MLflow)
-- =============================================================================

-- Activation PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- SCHÉMAS
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS rgpd;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS mlflow;
CREATE SCHEMA IF NOT EXISTS airflow;

-- =============================================================================
-- BRONZE — Données brutes (immutable, fetched_at + raw_data JSONB)
-- =============================================================================

-- Grand Lyon boucles de trafic (pvotrafic)
CREATE TABLE IF NOT EXISTS bronze.trafic_boucles (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    measurement_time TIMESTAMPTZ,
    channel_id TEXT,
    raw_data JSONB NOT NULL,
    ingestion_source TEXT DEFAULT 'pvotrafic'
);
CREATE INDEX IF NOT EXISTS idx_trafic_boucles_fetched ON bronze.trafic_boucles(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_trafic_boucles_channel ON bronze.trafic_boucles(channel_id);
CREATE INDEX IF NOT EXISTS idx_trafic_boucles_measurement ON bronze.trafic_boucles(measurement_time DESC);

-- Grand Lyon PVO trafic (autre granularité)
CREATE TABLE IF NOT EXISTS bronze.pvotrafic_snapshots (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pvotrafic_fetched ON bronze.pvotrafic_snapshots(fetched_at DESC);

-- Vélo'v GBFS
CREATE TABLE IF NOT EXISTS bronze.velov (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_velov_fetched ON bronze.velov(fetched_at DESC);

-- TCL SIRI Lite
CREATE TABLE IF NOT EXISTS bronze.tcl_vehicles (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tcl_fetched ON bronze.tcl_vehicles(fetched_at DESC);

-- Météo Open-Meteo
CREATE TABLE IF NOT EXISTS bronze.meteo (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meteo_fetched ON bronze.meteo(fetched_at DESC);

-- Qualité de l'air Open-Meteo
CREATE TABLE IF NOT EXISTS bronze.air_quality (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aq_fetched ON bronze.air_quality(fetched_at DESC);

-- Chantiers Grand Lyon
CREATE TABLE IF NOT EXISTS bronze.chantiers (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chantiers_fetched ON bronze.chantiers(fetched_at DESC);

-- Vitesses limites
CREATE TABLE IF NOT EXISTS bronze.vitesse_limite_ref (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vitesse_fetched ON bronze.vitesse_limite_ref(fetched_at DESC);

-- Tables référentielles (mensuelles)
CREATE TABLE IF NOT EXISTS bronze.calendrier_scolaire (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.jours_feries (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);

-- =============================================================================
-- SILVER — Données nettoyées (dédup, géo, normalisées)
-- =============================================================================

CREATE TABLE IF NOT EXISTS silver.trafic_boucles_clean (
    measurement_time TIMESTAMPTZ NOT NULL,
    channel_id TEXT NOT NULL,
    vitesse_kmh NUMERIC(6, 2),
    etat TEXT,
    flow_state TEXT,
    importance_code TEXT,
    geom_wgs84 GEOMETRY(LineString, 4326),
    geom_lamb93 GEOMETRY(LineString, 2154),
    h3_index_res13 TEXT,
    PRIMARY KEY (channel_id, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_silver_trafic_time ON silver.trafic_boucles_clean(measurement_time DESC);
CREATE INDEX IF NOT EXISTS idx_silver_trafic_channel ON silver.trafic_boucles_clean(channel_id);
CREATE INDEX IF NOT EXISTS idx_silver_trafic_geom ON silver.trafic_boucles_clean USING GIST(geom_wgs84);
CREATE INDEX IF NOT EXISTS idx_silver_trafic_h3 ON silver.trafic_boucles_clean(h3_index_res13);

CREATE TABLE IF NOT EXISTS silver.velov_clean (
    fetched_at TIMESTAMPTZ NOT NULL,
    station_id TEXT NOT NULL,
    station_name TEXT,
    bikes_available INTEGER,
    stands_available INTEGER,
    is_installed BOOLEAN,
    is_renting BOOLEAN,
    is_returning BOOLEAN,
    lat NUMERIC(10, 7),
    lon NUMERIC(10, 7),
    PRIMARY KEY (station_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_silver_velov_time ON silver.velov_clean(fetched_at DESC);

CREATE TABLE IF NOT EXISTS silver.tcl_vehicles_clean (
    fetched_at TIMESTAMPTZ NOT NULL,
    vehicle_ref TEXT NOT NULL,
    line_ref TEXT,
    direction_ref TEXT,
    delay_seconds INTEGER,
    latitude NUMERIC(10, 7),
    longitude NUMERIC(10, 7),
    monitored BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (vehicle_ref, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_silver_tcl_time ON silver.tcl_vehicles_clean(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_silver_tcl_line ON silver.tcl_vehicles_clean(line_ref);

CREATE TABLE IF NOT EXISTS silver.meteo_hourly (
    measurement_time TIMESTAMPTZ NOT NULL PRIMARY KEY,
    temperature_c NUMERIC(5, 2),
    humidity_pct NUMERIC(5, 2),
    rain_mm NUMERIC(6, 2),
    wind_kmh NUMERIC(5, 2),
    weather_code INTEGER,
    is_vacances_scolaires BOOLEAN DEFAULT FALSE,
    is_ferie BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS silver.chantiers_actifs (
    chantier_id TEXT PRIMARY KEY,
    date_debut DATE,
    date_fin DATE,
    localisation TEXT,
    impact_lines TEXT[],
    geom_wgs84 GEOMETRY(Point, 4326),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chantiers_actifs_dates ON silver.chantiers_actifs(date_debut, date_fin);
CREATE INDEX IF NOT EXISTS idx_chantiers_actifs_geom ON silver.chantiers_actifs USING GIST(geom_wgs84);

-- =============================================================================
-- GOLD — Features ML + analytique
-- =============================================================================

-- Référentiel capteurs
CREATE TABLE IF NOT EXISTS gold.dim_spatial_grid_mapping (
    node_idx INTEGER PRIMARY KEY,
    channel_id TEXT UNIQUE NOT NULL,
    matrix_i INTEGER,
    matrix_j INTEGER,
    h3_id TEXT,
    geom_wgs84 GEOMETRY(Point, 4326),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gold_mapping_channel ON gold.dim_spatial_grid_mapping(channel_id);

-- Arêtes graphe GNN
CREATE TABLE IF NOT EXISTS gold.dim_gnn_adjacency (
    edge_id BIGSERIAL PRIMARY KEY,
    node_u INTEGER NOT NULL REFERENCES gold.dim_spatial_grid_mapping(node_idx) ON DELETE CASCADE,
    node_v INTEGER NOT NULL REFERENCES gold.dim_spatial_grid_mapping(node_idx) ON DELETE CASCADE,
    is_connected BOOLEAN DEFAULT TRUE,
    distance_m NUMERIC(10, 2),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gold_adj_u ON gold.dim_gnn_adjacency(node_u);
CREATE INDEX IF NOT EXISTS idx_gold_adj_v ON gold.dim_gnn_adjacency(node_v);

-- Features trafic (Gold)
CREATE TABLE IF NOT EXISTS gold.traffic_features_live (
    measurement_time TIMESTAMPTZ NOT NULL,
    node_idx INTEGER NOT NULL,
    channel_id TEXT NOT NULL,
    speed_kmh NUMERIC(6, 2),
    speed_lag_1 NUMERIC(6, 2),
    speed_lag_2 NUMERIC(6, 2),
    speed_lag_3 NUMERIC(6, 2),
    speed_delta_1 NUMERIC(6, 2),
    rolling_mean_5min NUMERIC(6, 2),
    hour_sin NUMERIC(5, 4),
    hour_cos NUMERIC(5, 4),
    day_sin NUMERIC(5, 4),
    day_cos NUMERIC(5, 4),
    temperature_c NUMERIC(5, 2),
    rain_mm NUMERIC(6, 2),
    is_vacances BOOLEAN,
    is_ferie BOOLEAN,
    importance_code TEXT,
    PRIMARY KEY (node_idx, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_gold_features_time ON gold.traffic_features_live(measurement_time DESC);
CREATE INDEX IF NOT EXISTS idx_gold_features_channel ON gold.traffic_features_live(channel_id);

-- Prédictions (Gold)
CREATE TABLE IF NOT EXISTS gold.trafic_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    target_timestamp TIMESTAMPTZ NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    node_idx INTEGER NOT NULL,
    model_version TEXT,
    model_name TEXT,
    predicted_speed NUMERIC(6, 2),
    confidence_low NUMERIC(6, 2),
    confidence_high NUMERIC(6, 2),
    actual_speed NUMERIC(6, 2)
);
CREATE INDEX IF NOT EXISTS idx_gold_pred_time ON gold.trafic_predictions(prediction_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gold_pred_target ON gold.trafic_predictions(target_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gold_pred_node ON gold.trafic_predictions(node_idx, target_timestamp);

-- Backtesting
CREATE TABLE IF NOT EXISTS gold.predictions_vs_actuals (
    prediction_id BIGINT REFERENCES gold.trafic_predictions(prediction_id) ON DELETE CASCADE,
    horizon_minutes INTEGER,
    model_name TEXT,
    predicted_speed NUMERIC(6, 2),
    actual_speed NUMERIC(6, 2),
    error_kmh NUMERIC(6, 2),
    error_pct NUMERIC(5, 2),
    PRIMARY KEY (prediction_id)
);

-- Prédictions Vélov
CREATE TABLE IF NOT EXISTS gold.velov_features (
    measurement_time TIMESTAMPTZ NOT NULL,
    station_id_encoded INTEGER NOT NULL,
    station_id TEXT,
    bikes_available INTEGER,
    bikes_lag_1 INTEGER,
    bikes_lag_2 INTEGER,
    bikes_lag_3 INTEGER,
    rolling_mean_3h NUMERIC(6, 2),
    hour_sin NUMERIC(5, 4),
    hour_cos NUMERIC(5, 4),
    temperature_c NUMERIC(5, 2),
    rain_mm NUMERIC(6, 2),
    is_vacances BOOLEAN,
    is_ferie BOOLEAN,
    PRIMARY KEY (station_id_encoded, measurement_time)
);

CREATE TABLE IF NOT EXISTS gold.velov_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    target_timestamp TIMESTAMPTZ NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    station_id_encoded INTEGER,
    station_id TEXT,
    predicted_bikes NUMERIC(6, 2),
    actual_bikes INTEGER
);

-- Bus delay (analyse)
CREATE TABLE IF NOT EXISTS gold.bus_delay_segments (
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    line_ref TEXT NOT NULL,
    segment_id TEXT,
    avg_delay_seconds NUMERIC(8, 2),
    n_observations INTEGER,
    is_vacances BOOLEAN,
    is_ferie BOOLEAN,
    weather_code INTEGER,
    PRIMARY KEY (date, hour, line_ref, segment_id)
);

-- Bottlenecks infrastructure
CREATE TABLE IF NOT EXISTS gold.infrastructure_bottlenecks (
    bottleneck_id SERIAL PRIMARY KEY,
    segment_id TEXT,
    line_refs TEXT[],
    diagnosis TEXT, -- 'infra' | 'operations' | 'bus_lane_ok' | 'ok'
    impact_score NUMERIC(5, 2),
    voyageurs_jour INTEGER,
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    geom_wgs84 GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_bottlenecks_geom ON gold.infrastructure_bottlenecks USING GIST(geom_wgs84);
CREATE INDEX IF NOT EXISTS idx_bottlenecks_diag ON gold.infrastructure_bottlenecks(diagnosis);

-- =============================================================================
-- RGPD — Conformité
-- =============================================================================

-- Consentement utilisateur
CREATE TABLE IF NOT EXISTS rgpd.user_consents (
    consent_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_identifier TEXT,  -- hash anonyme, jamais nominatif
    consent_type TEXT NOT NULL, -- 'analytics' | 'tracking' | 'marketing' | 'all'
    granted BOOLEAN NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    ip_hash TEXT,
    user_agent_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_consent_user ON rgpd.user_consents(user_identifier);
CREATE INDEX IF NOT EXISTS idx_consent_granted ON rgpd.user_consents(granted, granted_at);

-- Demandes d'accès RGPD
CREATE TABLE IF NOT EXISTS rgpd.data_subject_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_identifier TEXT NOT NULL,
    request_type TEXT NOT NULL, -- 'access' | 'deletion' | 'portability' | 'rectification'
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'in_progress' | 'completed' | 'rejected'
    requested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    response_data JSONB,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_dsr_user ON rgpd.data_subject_requests(user_identifier);
CREATE INDEX IF NOT EXISTS idx_dsr_status ON rgpd.data_subject_requests(status);

-- Audit log
CREATE TABLE IF NOT EXISTS rgpd.audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    actor TEXT,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip_address INET,
    user_agent TEXT,
    details JSONB
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON rgpd.audit_log(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON rgpd.audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON rgpd.audit_log(action);

-- Purge tracking
CREATE TABLE IF NOT EXISTS rgpd.purge_log (
    purge_id BIGSERIAL PRIMARY KEY,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    rows_purged INTEGER NOT NULL,
    retention_days INTEGER NOT NULL,
    purged_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- GOVERNANCE — Data dictionary + lineage
-- =============================================================================

CREATE TABLE IF NOT EXISTS governance.data_dictionary (
    field_id SERIAL PRIMARY KEY,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    data_type TEXT,
    description TEXT,
    pii_level TEXT,  -- 'none' | 'low' | 'medium' | 'high'
    source TEXT,
    example_value TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (schema_name, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS governance.lineage (
    lineage_id SERIAL PRIMARY KEY,
    source_table TEXT NOT NULL,
    target_table TEXT NOT NULL,
    transformation TEXT, -- SQL ou description
    dag_id TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- UTILISATEURS APP (pour auth simple)
-- =============================================================================

CREATE TABLE IF NOT EXISTS gold.app_users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    persona_id TEXT NOT NULL,  -- 'usager' | 'pro_tcl' | 'elu'
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,  -- bcrypt
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_app_users_username ON gold.app_users(username);
CREATE INDEX IF NOT EXISTS idx_app_users_persona ON gold.app_users(persona_id);

-- =============================================================================
-- FIN — Schéma initial créé
-- =============================================================================
-- Les tables Airflow et MLflow seront créées par leurs propres init scripts.
-- =============================================================================
