-- migration_026_pgrouting_osm_network.sql
-- pgRouting : réseau routier OSM pour routing voiture
-- Prérequis : image pgrouting/pgrouting:16-3.5-3.7.3
--
-- IMPORTANT : exécuter APRÈS l'upgrade d'image Docker.
-- L'image pgrouting est PostGIS 3.5 (vs 3.4 avant).
-- Lancer d'abord : ALTER EXTENSION postgis UPDATE;

-- 0. Upgrade PostGIS 3.4 → 3.5 (fourni par la nouvelle image)
ALTER EXTENSION postgis UPDATE;

-- 1. Extension pgRouting
CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE;

-- 2. Schéma dédié pour le réseau routier OSM
CREATE SCHEMA IF NOT EXISTS osm;

-- 3. Table des noeuds (intersections routières)
-- Peuplée par osm2pgrouting depuis l'extrait OSM Lyon
CREATE TABLE IF NOT EXISTS osm.ways_vertices_pgr (
    id         BIGSERIAL PRIMARY KEY,
    cnt        INTEGER,
    chk        INTEGER,
    ein        INTEGER,
    eout       INTEGER,
    the_geom   GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_ways_vertices_geom
    ON osm.ways_vertices_pgr USING GIST (the_geom);

-- 4. Table des arêtes (tronçons routiers)
-- Peuplée par osm2pgrouting
CREATE TABLE IF NOT EXISTS osm.ways (
    gid            BIGSERIAL PRIMARY KEY,
    class_id       INTEGER,
    length         DOUBLE PRECISION,
    length_m       DOUBLE PRECISION,
    name           TEXT,
    source         BIGINT REFERENCES osm.ways_vertices_pgr(id),
    target         BIGINT REFERENCES osm.ways_vertices_pgr(id),
    cost           DOUBLE PRECISION,
    reverse_cost   DOUBLE PRECISION,
    cost_default   DOUBLE PRECISION,
    maxspeed_kmh   DOUBLE PRECISION DEFAULT 50.0,
    one_way        INTEGER DEFAULT 0,
    the_geom       GEOMETRY(LineString, 4326),
    source_osm     BIGINT,
    target_osm     BIGINT
);

CREATE INDEX IF NOT EXISTS idx_ways_geom ON osm.ways USING GIST (the_geom);
CREATE INDEX IF NOT EXISTS idx_ways_source ON osm.ways (source);
CREATE INDEX IF NOT EXISTS idx_ways_target ON osm.ways (target);

-- 5. Table de configuration des types de routes (osm2pgrouting)
CREATE TABLE IF NOT EXISTS osm.configuration (
    id         SERIAL PRIMARY KEY,
    tag_id     INTEGER,
    tag_key    TEXT,
    tag_value  TEXT,
    priority   DOUBLE PRECISION DEFAULT 1.0,
    maxspeed   DOUBLE PRECISION DEFAULT 50.0
);

-- 6. Vue matérialisée : mapping capteur Grand Lyon → arête OSM la plus proche
-- JOIN spatial KNN : chaque arête OSM est associée au capteur < 200m le plus proche
-- La plupart des arêtes OSM n'ont PAS de capteur nearby → cost_default utilisé
CREATE MATERIALIZED VIEW IF NOT EXISTS osm.mv_sensor_to_way AS
WITH sensor_coords AS (
    SELECT
        m.properties_twgid,
        mv.channel_id AS lyo_channel_id,
        m.lat AS sensor_lat,
        m.lon AS sensor_lon,
        ST_SetSRID(ST_MakePoint(m.lon, m.lat), 4326) AS sensor_geom
    FROM gold.dim_spatial_grid_mapping m
    JOIN gold.mv_twgid_to_lyo mv ON mv.properties_twgid = m.properties_twgid
    WHERE m.lat IS NOT NULL AND m.lon IS NOT NULL
)
SELECT DISTINCT ON (w.gid)
    w.gid AS way_gid,
    s.lyo_channel_id,
    s.properties_twgid,
    ST_Distance(
        s.sensor_geom::geography,
        ST_ClosestPoint(w.the_geom, s.sensor_geom)::geography
    ) AS distance_m
FROM osm.ways w
CROSS JOIN LATERAL (
    SELECT *
    FROM sensor_coords sc
    WHERE ST_DWithin(
        sc.sensor_geom::geography,
        w.the_geom::geography,
        200
    )
    ORDER BY sc.sensor_geom <-> ST_ClosestPoint(w.the_geom, sc.sensor_geom)
    LIMIT 1
) s
ORDER BY w.gid, distance_m ASC
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sensor_to_way_gid
    ON osm.mv_sensor_to_way (way_gid);

-- 7. Fonction de refresh des coûts trafic
-- Appelée par le DAG toutes les 15 min
CREATE OR REPLACE FUNCTION osm.refresh_traffic_costs()
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.mv_sensor_to_way;

    WITH live_speeds AS (
        SELECT
            stw.way_gid,
            t.speed_kmh
        FROM osm.mv_sensor_to_way stw
        JOIN gold.traffic_features_live t
            ON t.channel_id = stw.lyo_channel_id
        WHERE t.computed_at >= NOW() - INTERVAL '1 hour'
            AND t.speed_kmh > 0
            AND t.speed_kmh IS NOT NULL
    ),
    latest_speeds AS (
        SELECT DISTINCT ON (way_gid)
            way_gid, speed_kmh
        FROM live_speeds
        ORDER BY way_gid, speed_kmh DESC
    )
    UPDATE osm.ways w
    SET cost = CASE
            WHEN ls.speed_kmh IS NOT NULL AND ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.cost_default
        END,
        reverse_cost = CASE
            WHEN w.one_way = 1 THEN -1
            WHEN ls.speed_kmh IS NOT NULL AND ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.cost_default
        END
    FROM latest_speeds ls
    WHERE w.gid = ls.way_gid;

    GET DIAGNOSTICS updated_count = ROW_COUNT;

    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 8. Fonction pgRouting wrapper — Dijkstra dirigé avec géométrie
CREATE OR REPLACE FUNCTION osm.route_car(
    p_origin_lon  DOUBLE PRECISION,
    p_origin_lat  DOUBLE PRECISION,
    p_dest_lon    DOUBLE PRECISION,
    p_dest_lat    DOUBLE PRECISION
)
RETURNS TABLE (
    seq          INTEGER,
    edge_id      BIGINT,
    node_id      BIGINT,
    cost_s       DOUBLE PRECISION,
    agg_cost_s   DOUBLE PRECISION,
    length_m     DOUBLE PRECISION,
    speed_kmh    DOUBLE PRECISION,
    road_name    TEXT,
    geom_geojson TEXT
) AS $$
DECLARE
    v_source BIGINT;
    v_target BIGINT;
BEGIN
    SELECT id INTO v_source
    FROM osm.ways_vertices_pgr
    ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(p_origin_lon, p_origin_lat), 4326)
    LIMIT 1;

    SELECT id INTO v_target
    FROM osm.ways_vertices_pgr
    ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(p_dest_lon, p_dest_lat), 4326)
    LIMIT 1;

    IF v_source IS NULL OR v_target IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        d.seq::INTEGER,
        d.edge::BIGINT          AS edge_id,
        d.node::BIGINT          AS node_id,
        d.cost::DOUBLE PRECISION AS cost_s,
        d.agg_cost::DOUBLE PRECISION AS agg_cost_s,
        w.length_m,
        CASE
            WHEN w.cost > 0 AND w.length_m > 0
                THEN (w.length_m / w.cost) * 3.6
            ELSE w.maxspeed_kmh
        END AS speed_kmh,
        w.name AS road_name,
        ST_AsGeoJSON(w.the_geom)::TEXT AS geom_geojson
    FROM pgr_dijkstra(
        'SELECT gid AS id, source, target, cost, reverse_cost FROM osm.ways WHERE cost > 0',
        v_source,
        v_target,
        directed := true
    ) d
    LEFT JOIN osm.ways w ON w.gid = d.edge
    WHERE d.edge > 0
    ORDER BY d.seq;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION osm.route_car IS
    'Routing voiture Dijkstra dirigé via pgRouting. Retourne chemin avec géométrie OSM par arête.';
