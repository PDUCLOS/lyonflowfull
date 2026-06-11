-- =============================================================================
-- LyonFlowFull — Pathfinding helpers (Sprint VPS-6, 2026-06-11)
-- =============================================================================
-- Fonctions utilitaires pour le calcul de trajet multimode :
--   * distance haversine entre 2 points GPS
--   * K plus proches stations Vélov d'un point
--   * K plus proches nœuds routiers (gold.dim_spatial_grid_mapping) d'un point
--   * Calcul vitesse moyenne prédite H+1h pour un nœud routier
--
-- Toutes les fonctions sont IMMUTABLE / STABLE donc cacheables par PostgreSQL.
-- Idempotent : CREATE OR REPLACE.
-- =============================================================================


-- Distance haversine (mètres) entre 2 points GPS (WGS84)
CREATE OR REPLACE FUNCTION referentiel.haversine_m(
    lat1 DOUBLE PRECISION,
    lon1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION,
    lon2 DOUBLE PRECISION
) RETURNS DOUBLE PRECISION
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    -- 6371000 = rayon Terre en mètres
    SELECT 6371000 * 2 * ASIN(SQRT(
        POWER(SIN(RADIANS(lat2 - lat1) / 2), 2) +
        COS(RADIANS(lat1)) * COS(RADIANS(lat2)) *
        POWER(SIN(RADIANS(lon2 - lon1) / 2), 2)
    ));
$$;

COMMENT ON FUNCTION referentiel.haversine_m IS 'Distance haversine en mètres entre 2 points WGS84. R = 6371 km.';


-- K plus proches stations Vélov d'un point GPS
-- (utilise silver.velov_clean au snapshot le plus récent = dispo temps réel)
CREATE OR REPLACE FUNCTION referentiel.nearest_velov_stations(
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    k INTEGER DEFAULT 3,
    min_bikes INTEGER DEFAULT 0,
    min_docks INTEGER DEFAULT 0
) RETURNS TABLE (
    station_id          TEXT,
    station_name        TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    distance_m          DOUBLE PRECISION,
    is_active           BOOLEAN
)
LANGUAGE SQL
STABLE
AS $$
    WITH latest AS (
        -- Dernier snapshot par station
        SELECT DISTINCT ON (v.station_id)
            v.station_id, v.station_name, v.lat, v.lon,
            v.num_bikes_available, v.num_docks_available, v.is_active
        FROM silver.velov_clean v
        WHERE v.is_active = TRUE
        ORDER BY v.station_id, v.fetched_at DESC
    )
    SELECT
        l.station_id, l.station_name, l.lat, l.lon,
        l.num_bikes_available, l.num_docks_available,
        referentiel.haversine_m($1, $2, l.lat, l.lon) AS distance_m,
        l.is_active
    FROM latest l
    WHERE l.num_bikes_available >= $4
      AND l.num_docks_available >= $5
    ORDER BY distance_m ASC
    LIMIT $3;
$$;

COMMENT ON FUNCTION referentiel.nearest_velov_stations IS 'K plus proches stations Vélov avec dispo temps réel (silver.velov_clean, dernier snapshot). Filtres min_bikes/min_docks. Triées par distance haversine.';


-- K plus proches nœuds routiers (gold.dim_spatial_grid_mapping) d'un point
CREATE OR REPLACE FUNCTION referentiel.nearest_traffic_nodes(
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    k INTEGER DEFAULT 1
) RETURNS TABLE (
    node_idx            INTEGER,
    properties_twgid    TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    distance_m          DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        m.node_idx, m.properties_twgid, m.lat, m.lon,
        referentiel.haversine_m($1, $2, m.lat, m.lon) AS distance_m
    FROM gold.dim_spatial_grid_mapping m
    WHERE m.lat IS NOT NULL AND m.lon IS NOT NULL
    ORDER BY distance_m ASC
    LIMIT $3;
$$;

COMMENT ON FUNCTION referentiel.nearest_traffic_nodes IS 'K plus proches nœuds routiers (capteurs trafic) d''un point GPS. Utilise gold.dim_spatial_grid_mapping (1520 nœuds H3).';


-- Vitesse moyenne prédite H+1h (par défaut) pour un nœud routier
-- Source : gold.trafic_predictions (Sprint VPS-5, populée par dag_live_speed_retrain)
-- Schéma réel : (axis_key, horizon_h, calculated_at, speed_pred, etat_pred, color, lat, lon, ...)
CREATE OR REPLACE FUNCTION referentiel.predicted_speed_for_node(
    p_axis_key TEXT,
    p_horizon_h INTEGER DEFAULT 1
) RETURNS TABLE (
    axis_key        TEXT,
    speed_pred      DOUBLE PRECISION,
    etat_pred       TEXT,
    color           TEXT,
    calculated_at   TIMESTAMPTZ
)
LANGUAGE SQL
STABLE
AS $$
    -- Prend la prédiction la plus récente pour cet axis_key à l'horizon demandé
    SELECT
        tp.axis_key, tp.speed_pred::float8, tp.etat_pred, tp.color, tp.calculated_at
    FROM gold.trafic_predictions tp
    WHERE tp.axis_key = $1
      AND tp.horizon_h = $2
    ORDER BY tp.calculated_at DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION referentiel.predicted_speed_for_node IS 'Vitesse prédite pour un axis_key (capteur/segment) à un horizon donné. gold.trafic_predictions (Sprint VPS-5). Schéma v0.3.1.';


-- Vue : vitesse moyenne par nœud (moyenne historique 7j)
-- Sert de fallback si gold.trafic_predictions n'est pas encore peuplée pour H+1h
CREATE OR REPLACE VIEW referentiel.v_avg_speed_7d AS
SELECT
    m.node_idx,
    m.properties_twgid,
    m.lat,
    m.lon,
    AVG(t.speed_kmh) AS avg_speed_kmh,
    COUNT(*)         AS n_obs
FROM gold.dim_spatial_grid_mapping m
LEFT JOIN gold.traffic_features_live t
  ON t.channel_id::text = m.properties_twgid::text
 AND t.computed_at >= NOW() - INTERVAL '7 days'
WHERE m.lat IS NOT NULL
GROUP BY m.node_idx, m.properties_twgid, m.lat, m.lon;

COMMENT ON VIEW referentiel.v_avg_speed_7d IS 'Vitesse moyenne historique 7j par nœud routier. Fallback si trafric_predictions vide.';


-- ============================================================================
-- Pathfinding voiture (route-based via H3 nodes)
-- ============================================================================
-- Algorithme : on snap la position GPS au nœud routier le plus proche, on
-- calcule la distance haversine au nœud destination, et on divise par la
-- vitesse prédite (H+1h) pour estimer la durée.
--
-- Pas un vrai A* (pas de graphe routier chargé), mais une **estimation
-- trafic-aware** qui exploite les prédictions GNN/XGBoost. Pour un A* réel
-- (sens de circulation, OSM), Sprint 7+ : ingérer Overpass API.
-- ============================================================================
CREATE OR REPLACE FUNCTION referentiel.estimate_car_trip(
    p_origin_lat DOUBLE PRECISION,
    p_origin_lon DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION,
    p_dest_lon   DOUBLE PRECISION,
    p_horizon_h  INTEGER DEFAULT 1,
    p_avg_speed_fallback_kmh DOUBLE PRECISION DEFAULT 30.0
) RETURNS TABLE (
    origin_node_idx        INTEGER,
    dest_node_idx          INTEGER,
    haversine_distance_m   DOUBLE PRECISION,
    predicted_speed_kmh    DOUBLE PRECISION,
    source                 TEXT,        -- 'predicted' | 'avg_7d' | 'fallback'
    estimated_duration_min DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
    WITH origin_node AS (
        SELECT node_idx, properties_twgid, lat, lon, distance_m
        FROM referentiel.nearest_traffic_nodes($1, $2, 1)
    ),
    dest_node AS (
        SELECT node_idx, properties_twgid, lat, lon, distance_m
        FROM referentiel.nearest_traffic_nodes($3, $4, 1)
    ),
    speed_lookup AS (
        -- Lookup prédiction via axis_key = properties_twgid (mapping Sprint VPS-5)
        SELECT
            o.node_idx AS origin_node_idx,
            d.node_idx AS dest_node_idx,
            COALESCE(
                (SELECT speed_pred FROM referentiel.predicted_speed_for_node(d.properties_twgid, $5) LIMIT 1),
                (SELECT avg_speed_kmh FROM referentiel.v_avg_speed_7d WHERE node_idx = d.node_idx LIMIT 1),
                $6
            ) AS speed_kmh,
            CASE
                WHEN (SELECT speed_pred FROM referentiel.predicted_speed_for_node(d.properties_twgid, $5) LIMIT 1) IS NOT NULL
                    THEN 'predicted'
                WHEN (SELECT avg_speed_kmh FROM referentiel.v_avg_speed_7d WHERE node_idx = d.node_idx LIMIT 1) IS NOT NULL
                    THEN 'avg_7d'
                ELSE 'fallback'
            END AS source
        FROM origin_node o, dest_node d
    ),
    dist AS (
        SELECT
            s.origin_node_idx, s.dest_node_idx, s.speed_kmh, s.source,
            referentiel.haversine_m(o.lat, o.lon, d.lat, d.lon) AS haversine_m
        FROM speed_lookup s
        JOIN origin_node o ON o.node_idx = s.origin_node_idx
        JOIN dest_node d ON d.node_idx = s.dest_node_idx
    )
    SELECT
        origin_node_idx, dest_node_idx, haversine_m,
        speed_kmh AS predicted_speed_kmh, source,
        -- durée en minutes : (distance_km / speed_kmh) * 60
        ROUND(((haversine_m / 1000.0) / NULLIF(speed_kmh, 0) * 60.0)::numeric, 1) AS est_min
    FROM dist;
$$;

COMMENT ON FUNCTION referentiel.estimate_car_trip IS 'Estimation durée trajet voiture entre 2 points GPS. Snappe aux nœuds H3, utilise trafric_predictions (H+h) si dispo, sinon moyenne 7j, sinon fallback configurable. Pas un vrai A* — Sprint 7+ ingère OSM/Overpass.';


-- ============================================================================
-- Pathfinding Vélov + marche
-- ============================================================================
-- Origine (lat,lon) → marche 5min vers Vélov le plus proche → Vélov station
-- la plus proche de la destination → marche 5min vers destination.
-- ============================================================================
CREATE OR REPLACE FUNCTION referentiel.estimate_velov_trip(
    p_origin_lat DOUBLE PRECISION,
    p_origin_lon DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION,
    p_dest_lon   DOUBLE PRECISION,
    p_walk_speed_kmh DOUBLE PRECISION DEFAULT 4.5,  -- marche piétonne moyenne
    p_cyclist_speed_kmh DOUBLE PRECISION DEFAULT 15.0  -- Vélov urbain
) RETURNS TABLE (
    segment              TEXT,        -- 'walk_to_station' | 'cycle_between' | 'walk_to_dest'
    from_label           TEXT,
    to_label             TEXT,
    from_lat             DOUBLE PRECISION,
    from_lon             DOUBLE PRECISION,
    to_lat               DOUBLE PRECISION,
    to_lon               DOUBLE PRECISION,
    distance_m           DOUBLE PRECISION,
    duration_min         DOUBLE PRECISION,
    n_bikes_depart       INTEGER,
    n_docks_arrive       INTEGER
)
LANGUAGE SQL
STABLE
AS $$
    WITH
    origin_station AS (
        SELECT * FROM referentiel.nearest_velov_stations($1, $2, 1, 1, 0) LIMIT 1
    ),
    dest_station AS (
        SELECT * FROM referentiel.nearest_velov_stations($3, $4, 1, 0, 1) LIMIT 1
    )
    -- Segment 1 : marche origine → station Vélov
    SELECT
        'walk_to_station'::TEXT AS segment,
        'Origin'::TEXT           AS from_label,
        os.station_name         AS to_label,
        $1::DOUBLE PRECISION    AS from_lat,
        $2::DOUBLE PRECISION    AS from_lon,
        os.lat                 AS to_lat,
        os.lon                 AS to_lon,
        os.distance_m,
        ROUND((os.distance_m / 1000.0 / $5 * 60.0)::numeric, 1) AS duration_min,
        os.num_bikes_available  AS n_bikes_depart,
        NULL::INTEGER           AS n_docks_arrive
    FROM origin_station os

    UNION ALL

    -- Segment 2 : Vélov entre les 2 stations
    SELECT
        'cycle_between'::TEXT,
        os.station_name,
        ds.station_name,
        os.lat, os.lon, ds.lat, ds.lon,
        referentiel.haversine_m(os.lat, os.lon, ds.lat, ds.lon) AS dist_m,
        ROUND((referentiel.haversine_m(os.lat, os.lon, ds.lat, ds.lon) / 1000.0 / $6 * 60.0)::numeric, 1),
        os.num_bikes_available,
        ds.num_docks_available
    FROM origin_station os, dest_station ds

    UNION ALL

    -- Segment 3 : marche station Vélov → destination
    SELECT
        'walk_to_dest'::TEXT,
        ds.station_name,
        'Destination'::TEXT,
        ds.lat, ds.lon,
        $3::DOUBLE PRECISION, $4::DOUBLE PRECISION,
        ds.distance_m,
        ROUND((ds.distance_m / 1000.0 / $5 * 60.0)::numeric, 1),
        NULL::INTEGER,
        ds.num_docks_available
    FROM dest_station ds;
$$;

COMMENT ON FUNCTION referentiel.estimate_velov_trip IS 'Estimation trajet Vélov+marche entre 2 points GPS. 3 segments : marche→Vélov, Vélov, Vélov→marche. Utilise silver.velov_clean (dernier snapshot) pour dispo. Pas un vrai routing — heuristique haversine.';
