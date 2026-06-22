-- migration_028_fix_sensor_to_way.sql
-- Fix : mv_sensor_to_way vide à cause du JOIN cassé
-- dim_spatial_grid_mapping.properties_twgid ("LYO02236") ≠ mv_twgid_to_lyo.properties_twgid (647)
--
-- Solution : bypass dim_spatial_grid_mapping + mv_twgid_to_lyo.
-- On va directement depuis gold.traffic_features_live qui a :
--   - channel_id (format LYO0xxxx)
--   - lat, lon (coords GPS)
--   - speed_kmh (vitesse temps réel)
-- C'est la seule table qu'on utilise dans refresh_traffic_costs() de toute façon.

-- 1. Table helper : positions des capteurs Grand Lyon (indexée spatialement)
-- ~1100 capteurs, refresh rare (positions fixes)
DROP TABLE IF EXISTS osm.sensor_positions CASCADE;
CREATE TABLE osm.sensor_positions (
    channel_id   TEXT PRIMARY KEY,
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    geom         GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX idx_sensor_positions_geom
    ON osm.sensor_positions USING GIST (geom);

-- Peupler depuis traffic_features_live (dernières 14 jours)
INSERT INTO osm.sensor_positions (channel_id, lat, lon, geom)
SELECT DISTINCT ON (channel_id)
    channel_id,
    lat,
    lon,
    ST_SetSRID(ST_MakePoint(lon, lat), 4326)
FROM gold.traffic_features_live
WHERE lat IS NOT NULL
  AND lon IS NOT NULL
  AND computed_at > NOW() - INTERVAL '14 days'
ORDER BY channel_id, computed_at DESC;

-- 2. Recréer mv_sensor_to_way avec JOIN spatial direct
-- Pour chaque arête OSM, trouver le capteur le plus proche < 200m
DROP MATERIALIZED VIEW IF EXISTS osm.mv_sensor_to_way CASCADE;

CREATE MATERIALIZED VIEW osm.mv_sensor_to_way AS
SELECT DISTINCT ON (w.gid)
    w.gid AS way_gid,
    s.channel_id AS lyo_channel_id,
    ST_Distance(
        s.geom::geography,
        ST_ClosestPoint(w.the_geom, s.geom)::geography
    ) AS distance_m
FROM osm.ways w
INNER JOIN osm.sensor_positions s
    ON ST_DWithin(s.geom::geography, w.the_geom::geography, 200)
ORDER BY w.gid,
    ST_Distance(s.geom::geography, ST_ClosestPoint(w.the_geom, s.geom)::geography) ASC;

CREATE UNIQUE INDEX idx_mv_sensor_to_way_gid
    ON osm.mv_sensor_to_way (way_gid);

-- 3. Mettre à jour refresh_traffic_costs() — plus simple, même logique
CREATE OR REPLACE FUNCTION osm.refresh_traffic_costs()
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.mv_sensor_to_way;

    WITH live_speeds AS (
        SELECT DISTINCT ON (stw.way_gid)
            stw.way_gid,
            t.speed_kmh
        FROM osm.mv_sensor_to_way stw
        JOIN gold.traffic_features_live t
            ON t.channel_id = stw.lyo_channel_id
        WHERE t.computed_at >= NOW() - INTERVAL '1 hour'
            AND t.speed_kmh > 0
            AND t.speed_kmh IS NOT NULL
        ORDER BY stw.way_gid, t.computed_at DESC
    )
    UPDATE osm.ways w
    SET cost = CASE
            WHEN ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.length_m / (GREATEST(w.maxspeed_forward, 5.0) / 3.6)
        END,
        reverse_cost = CASE
            WHEN w.one_way = 1 THEN -1
            WHEN ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.length_m / (GREATEST(w.maxspeed_forward, 5.0) / 3.6)
        END
    FROM live_speeds ls
    WHERE w.gid = ls.way_gid;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 4. Stats
SELECT COUNT(*) AS sensors_total FROM osm.sensor_positions;
SELECT COUNT(*) AS ways_with_sensor FROM osm.mv_sensor_to_way;
SELECT
    ROUND(AVG(distance_m)::numeric, 1) AS avg_distance_m,
    ROUND(MAX(distance_m)::numeric, 1) AS max_distance_m
FROM osm.mv_sensor_to_way;
