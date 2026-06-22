-- migration_027_reconcile_pgrouting_schema.sql
-- Réconciliation après osm2pgrouting --clean qui a droppé certaines tables/views
-- de migration_026. Adapt au schéma réel créé par osm2pgrouting 2.3.8.

-- 1. Recréer mv_sensor_to_way (droppé par osm2pgrouting)
DROP MATERIALIZED VIEW IF EXISTS osm.mv_sensor_to_way CASCADE;
CREATE MATERIALIZED VIEW osm.mv_sensor_to_way AS
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

-- 2. Recréer refresh_traffic_costs() — adapté au schéma osm2pgrouting
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
            ELSE w.length_m / (GREATEST(w.maxspeed_forward, 5.0) / 3.6)
        END,
        reverse_cost = CASE
            WHEN w.one_way = 1 THEN -1
            WHEN ls.speed_kmh IS NOT NULL AND ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.length_m / (GREATEST(w.maxspeed_forward, 5.0) / 3.6)
        END
    FROM latest_speeds ls
    WHERE w.gid = ls.way_gid;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 3. Recréer route_car() — adapté pour utiliser maxspeed_forward au lieu de maxspeed_kmh
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
            ELSE COALESCE(w.maxspeed_forward, 30.0)
        END AS speed_kmh,
        COALESCE(w.name, '') AS road_name,
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
    'Routing voiture Dijkstra dirigé via pgRouting. Retourne chemin avec géométrie OSM par arête. Adapté au schéma osm2pgrouting 2.3.8 (maxspeed_forward, pas maxspeed_kmh).';