-- migration_032_route_car_ksp.sql
-- ============================================================================
-- K-shortest paths (pgr_ksp) pour proposer des alternatives d'itinéraire
-- ============================================================================
-- Contexte (2026-06-22, Sprint 22) :
-- - osm.route_car() retourne le chemin optimal unique via pgr_dijkstra.
-- - Avec coûts quasi-uniformes (capteurs ne couvrent pas toutes les rues),
--   Dijkstra retourne souvent le même chemin pour des origines/destinations
--   similaires → frustration usager "toujours le même trajet".
-- - pgr_ksp retourne les K chemins les plus courts (avec pénalité pour
--   éviter les répétitions d'arêtes), ce qui permet à l'usager de comparer
--   2-3 alternatives réelles.
--
-- Sortie : pour chaque chemin k, on retourne les arêtes avec géométrie
-- (identique au contrat osm.route_car) + colonne `route_id` (1..K).
-- L'API publique reste rétro-compatible : ajouter osm.route_car_ksp().
-- ============================================================================

CREATE OR REPLACE FUNCTION osm.route_car_ksp(
    p_origin_lon  DOUBLE PRECISION,
    p_origin_lat  DOUBLE PRECISION,
    p_dest_lon    DOUBLE PRECISION,
    p_dest_lat    DOUBLE PRECISION,
    p_k           INTEGER DEFAULT 3
)
RETURNS TABLE (
    route_id     INTEGER,
    seq          INTEGER,
    edge_id      BIGINT,
    node_id      BIGINT,
    cost_s       DOUBLE PRECISION,
    agg_cost_s   DOUBLE PRECISION,
    length_m     DOUBLE PRECISION,
    speed_kmh    DOUBLE PRECISION,
    road_name    TEXT,
    geom_geojson TEXT,
    total_length_m DOUBLE PRECISION,
    total_cost_s   DOUBLE PRECISION
) AS $$
DECLARE
    v_source BIGINT;
    v_target BIGINT;
BEGIN
    -- Clamp K entre 1 et 5 (perf vs UX : 5 alternatives max, sinon trop)
    p_k := LEAST(GREATEST(p_k, 1), 5);

    -- Trouver les nœuds OSM les plus proches
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
    WITH ksp AS (
        SELECT
            k.path_id::INTEGER                 AS path_id_int,
            k.path_seq::INTEGER                AS path_seq,
            k.edge::BIGINT                     AS edge_id,
            k.node::BIGINT                     AS node_id,
            k.cost::DOUBLE PRECISION           AS cost_s,
            k.agg_cost::DOUBLE PRECISION       AS agg_cost_s
        FROM pgr_ksp(
            'SELECT gid AS id, source, target, cost, reverse_cost
             FROM osm.ways
             WHERE cost > 0',
            v_source,
            v_target,
            p_k,
            directed := true,
            heap_paths := true
        ) k
        WHERE k.edge > 0
    ),
    agg AS (
        SELECT
            k2.path_id_int,
            SUM(w2.length_m) AS tot_len_m,
            SUM(k2.cost_s)   AS tot_cost_s
        FROM ksp k2
        JOIN osm.ways w2 ON w2.gid = k2.edge_id
        GROUP BY k2.path_id_int
    )
    SELECT
        k.path_id_int                         AS route_id,
        (ROW_NUMBER() OVER (PARTITION BY k.path_id_int ORDER BY k.path_seq))::INTEGER AS seq,
        k.edge_id,
        k.node_id,
        k.cost_s,
        k.agg_cost_s,
        w.length_m,
        CASE
            WHEN w.cost > 0 AND w.length_m > 0
                THEN (w.length_m / w.cost) * 3.6
            ELSE w.maxspeed_kmh
        END AS speed_kmh,
        w.name AS road_name,
        ST_AsGeoJSON(w.the_geom)::TEXT AS geom_geojson,
        a.tot_len_m                           AS total_length_m,
        a.tot_cost_s                          AS total_cost_s
    FROM ksp k
    JOIN osm.ways w ON w.gid = k.edge_id
    JOIN agg a ON a.path_id_int = k.path_id_int
    ORDER BY k.path_id_int, k.path_seq;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION osm.route_car_ksp IS
    'K-shortest paths (Yen algorithm) via pgRouting KSP. Retourne jusqu''à 5 alternatives d''itinéraire avec géométrie OSM par arête. Colonne route_id (1..K) + totaux (length/cost) dupliqués sur chaque ligne pour affichage rapide côté client.';

-- ============================================================================
-- Tests rapides (décommenter pour vérifier après déploiement)
-- ============================================================================
-- SELECT route_id, COUNT(*) AS edges, ROUND(total_length_m::numeric/1000, 2) AS km,
--        ROUND(total_cost_s::numeric/60, 1) AS min, MIN(road_name) AS sample_road
-- FROM osm.route_car_ksp(4.881, 45.7715, 4.8165, 45.7405, 3)
-- GROUP BY route_id, total_length_m, total_cost_s
-- ORDER BY route_id;
