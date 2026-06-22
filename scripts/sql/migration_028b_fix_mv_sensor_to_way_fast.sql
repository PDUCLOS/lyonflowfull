-- migration_028b_fix_mv_sensor_to_way_fast.sql
-- Fix : la version 028 avec ORDER BY ST_Distance() hang sur 100k ways × 1159 sensors
-- (32s pour COUNT mais >1h pour DISTINCT ON + ORDER BY distance).
--
-- Solution : utiliser l'opérateur KNN `<->` de GiST qui est optimisé pour
-- "trouver les K plus proches voisins". Avec LATERAL + ORDER BY <-> LIMIT 1,
-- PostgreSQL utilise l'index KNN pour aller directement au plus proche.

-- 1. Recréer mv_sensor_to_way avec LATERAL KNN
DROP MATERIALIZED VIEW IF EXISTS osm.mv_sensor_to_way CASCADE;

CREATE MATERIALIZED VIEW osm.mv_sensor_to_way AS
SELECT
    w.gid AS way_gid,
    s.channel_id AS lyo_channel_id,
    ST_Distance(
        s.geom::geography,
        ST_ClosestPoint(w.the_geom, s.geom)::geography
    ) AS distance_m
FROM osm.ways w
CROSS JOIN LATERAL (
    SELECT channel_id, geom
    FROM osm.sensor_positions s
    WHERE ST_DWithin(s.geom, w.the_geom, 0.002)  -- ~200m en degrés
    ORDER BY s.geom <-> w.the_geom                  -- KNN : utilise index GiST
    LIMIT 1
) s
WHERE s.channel_id IS NOT NULL;

CREATE UNIQUE INDEX idx_mv_sensor_to_way_gid
    ON osm.mv_sensor_to_way (way_gid);

-- 2. Mettre à jour refresh_traffic_costs() — identique à 028
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

-- 3. Stats
SELECT COUNT(*) AS sensors_total FROM osm.sensor_positions;
SELECT COUNT(*) AS ways_with_sensor FROM osm.mv_sensor_to_way;
SELECT
    ROUND(AVG(distance_m)::numeric, 1) AS avg_distance_m,
    ROUND(MIN(distance_m)::numeric, 1) AS min_distance_m,
    ROUND(MAX(distance_m)::numeric, 1) AS max_distance_m
FROM osm.mv_sensor_to_way;