-- migration_054_route_car_access_alternatives.sql
-- ============================================================================
-- Routage voiture : respect des accès + vraies alternatives d'itinéraire
-- ============================================================================
-- Contexte (2026-10-03) :
-- 1. osm.route_car / osm.route_car_ksp routaient sur tout osm.ways : le
--    trajet Villeurbanne → Part-Dieu passait par la plateforme du tram T1 et
--    des couloirs bus. On exclut car_access = 'no' (migration 053) et on
--    pénalise les voies privées (x10) pour qu'elles ne servent pas de
--    raccourci. Le point de départ / d'arrivée est accroché à la voie
--    publique la plus proche (plus au nœud le plus proche, qui pouvait être
--    sur un couloir bus).
-- 2. pgr_ksp (Yen) renvoyait 3 fois le même trajet à un pâté de maisons
--    près (88-90 % de longueur commune, mêmes 3,3 km / 9 min). Remplacé par
--    la méthode de pénalité : Dijkstra, puis on double le coût des arêtes
--    déjà utilisées et on relance. Une alternative est gardée si elle
--    partage au plus 75 % de sa longueur avec chaque itinéraire déjà retenu
--    et si elle reste à moins de +50 % du temps du meilleur. Mieux vaut
--    rendre moins de K itinéraires que des quasi-doublons.
--
-- Les coûts renvoyés (cost_s, agg_cost_s, total_cost_s) sont les coûts
-- RÉELS des arêtes dans le sens parcouru, jamais les coûts pénalisés.
-- Signatures et colonnes inchangées : aucun changement côté Python.
-- Prérequis : migration 053 (osm.ways.car_access, osm.ways_vertices_pgr.car_routable).
-- ============================================================================

-- Garde-fou : sans les colonnes de la 053 (échec, lock_timeout…), les fonctions
-- ci-dessous planteraient au premier itinéraire demandé. On échoue ici.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'osm' AND table_name = 'ways' AND column_name = 'car_access'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'osm' AND table_name = 'ways_vertices_pgr' AND column_name = 'car_routable'
    ) THEN
        RAISE EXCEPTION 'Colonnes de la migration 053 absentes : l''appliquer avant la 054';
    END IF;
END $$;

-- Point d'accroche : nœud routable (migration 053) le plus proche. Le nœud le
-- plus proche tout court pouvait être sur un couloir bus, ou sur un îlot que
-- seules des voies interdites relient au réseau (=> aucun itinéraire).
CREATE OR REPLACE FUNCTION osm.car_snap_vertex(
    p_lon DOUBLE PRECISION,
    p_lat DOUBLE PRECISION
)
RETURNS BIGINT AS $$
    SELECT v.id
    FROM osm.ways_vertices_pgr v
    WHERE v.car_routable
    ORDER BY v.the_geom <-> ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)
    LIMIT 1;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION osm.car_snap_vertex IS
    'Nœud de départ/arrivée voiture : nœud car_routable le plus proche (plus grande composante fortement connexe des voies autorisées).';


-- SQL des arêtes pour pgr_dijkstra. p_penalized : arêtes dont le coût est
-- multiplié par p_factor (alternatives). Voies privées x10, interdites exclues.
CREATE OR REPLACE FUNCTION osm.car_edges_sql(
    p_penalized BIGINT[] DEFAULT '{}',
    p_factor    DOUBLE PRECISION DEFAULT 1.0
)
RETURNS TEXT AS $$
    SELECT format(
        $q$
        SELECT w.gid AS id, w.source, w.target,
               w.cost * m.f AS cost,
               CASE WHEN w.reverse_cost > 0 THEN w.reverse_cost * m.f ELSE -1 END AS reverse_cost
        FROM osm.ways w
        LEFT JOIN unnest(%L::BIGINT[]) AS u(gid) ON u.gid = w.gid
        CROSS JOIN LATERAL (
            SELECT (CASE WHEN w.car_access = 'private' THEN 10.0 ELSE 1.0 END)
                 * (CASE WHEN u.gid IS NOT NULL THEN %s ELSE 1.0 END) AS f
        ) m
        WHERE w.cost > 0 AND w.car_access <> 'no'
        $q$,
        p_penalized::TEXT,
        p_factor
    );
$$ LANGUAGE sql IMMUTABLE;


CREATE OR REPLACE FUNCTION osm.route_car(
    p_origin_lon DOUBLE PRECISION,
    p_origin_lat DOUBLE PRECISION,
    p_dest_lon   DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION
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
#variable_conflict use_column
DECLARE
    v_source BIGINT := osm.car_snap_vertex(p_origin_lon, p_origin_lat);
    v_target BIGINT := osm.car_snap_vertex(p_dest_lon, p_dest_lat);
BEGIN
    IF v_source IS NULL OR v_target IS NULL OR v_source = v_target THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        d.seq::INTEGER,
        d.edge::BIGINT,
        d.node::BIGINT,
        r.real_cost,
        SUM(r.real_cost) OVER (ORDER BY d.seq),
        w.length_m,
        CASE WHEN r.real_cost > 0 THEN w.length_m / r.real_cost * 3.6
             ELSE COALESCE(w.maxspeed_forward, 30.0) END,
        COALESCE(w.name, ''),
        ST_AsGeoJSON(w.the_geom)::TEXT
    FROM pgr_dijkstra(osm.car_edges_sql(), v_source, v_target, directed := true) d
    JOIN osm.ways w ON w.gid = d.edge
    CROSS JOIN LATERAL (
        SELECT (CASE WHEN d.node = w.source THEN w.cost ELSE w.reverse_cost END)::DOUBLE PRECISION AS real_cost
    ) r
    WHERE d.edge > 0
    ORDER BY d.seq;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION osm.route_car IS
    'Itinéraire voiture le plus rapide (pgr_dijkstra) sur les voies autorisées (car_access <> no, privées x10). Coûts réels en secondes.';


-- Nom conservé (appelé par src/routing/graph.py) mais ce n'est plus pgr_ksp.
CREATE OR REPLACE FUNCTION osm.route_car_ksp(
    p_origin_lon DOUBLE PRECISION,
    p_origin_lat DOUBLE PRECISION,
    p_dest_lon   DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION,
    p_k          INTEGER DEFAULT 3
)
RETURNS TABLE (
    route_id       INTEGER,
    seq            INTEGER,
    edge_id        BIGINT,
    node_id        BIGINT,
    cost_s         DOUBLE PRECISION,
    agg_cost_s     DOUBLE PRECISION,
    length_m       DOUBLE PRECISION,
    speed_kmh      DOUBLE PRECISION,
    road_name      TEXT,
    geom_geojson   TEXT,
    total_length_m DOUBLE PRECISION,
    total_cost_s   DOUBLE PRECISION
) AS $$
#variable_conflict use_column
DECLARE
    c_penalty     CONSTANT DOUBLE PRECISION := 2.0;   -- coût x2 sur les arêtes déjà utilisées
    c_max_overlap CONSTANT DOUBLE PRECISION := 0.75;  -- part de longueur commune max
    c_max_detour  CONSTANT DOUBLE PRECISION := 1.5;   -- +50 % de temps max vs le meilleur
    v_source      BIGINT := osm.car_snap_vertex(p_origin_lon, p_origin_lat);
    v_target      BIGINT := osm.car_snap_vertex(p_dest_lon, p_dest_lat);
    v_used        BIGINT[] := '{}';
    v_kept_edges  BIGINT[] := '{}';
    v_kept_route  INTEGER[] := '{}';
    v_edges       BIGINT[];
    v_nodes       BIGINT[];
    v_cost        DOUBLE PRECISION;
    v_len         DOUBLE PRECISION;
    v_best_cost   DOUBLE PRECISION;
    v_overlap     DOUBLE PRECISION;
    v_n           INTEGER := 0;
    v_try         INTEGER := 0;
BEGIN
    p_k := LEAST(GREATEST(p_k, 1), 5);
    IF v_source IS NULL OR v_target IS NULL OR v_source = v_target THEN
        RETURN;
    END IF;

    WHILE v_n < p_k AND v_try < p_k + 2 LOOP
        v_try := v_try + 1;

        SELECT array_agg(d.edge ORDER BY d.seq), array_agg(d.node ORDER BY d.seq)
        INTO v_edges, v_nodes
        FROM pgr_dijkstra(osm.car_edges_sql(v_used, c_penalty), v_source, v_target, directed := true) d
        WHERE d.edge > 0;

        EXIT WHEN v_edges IS NULL;

        SELECT SUM(CASE WHEN e.node = w.source THEN w.cost ELSE w.reverse_cost END), SUM(w.length_m)
        INTO v_cost, v_len
        FROM unnest(v_edges, v_nodes) AS e(edge, node)
        JOIN osm.ways w ON w.gid = e.edge;

        IF v_n = 0 THEN
            v_best_cost := v_cost;
            v_overlap := 0;
        ELSE
            -- Part de la longueur du candidat commune avec chaque itinéraire retenu
            SELECT COALESCE(MAX(s.shared), 0) INTO v_overlap
            FROM (
                SELECT k.route, SUM(w.length_m) / NULLIF(v_len, 0) AS shared
                FROM unnest(v_kept_edges, v_kept_route) AS k(edge, route)
                JOIN unnest(v_edges) AS c(edge) ON c.edge = k.edge
                JOIN osm.ways w ON w.gid = k.edge
                GROUP BY k.route
            ) s;
        END IF;

        IF v_n = 0 OR (v_overlap <= c_max_overlap AND v_cost <= v_best_cost * c_max_detour) THEN
            v_n := v_n + 1;
            v_kept_edges := v_kept_edges || v_edges;
            v_kept_route := v_kept_route || array_fill(v_n, ARRAY[cardinality(v_edges)]);

            RETURN QUERY
            SELECT
                v_n,
                e.ord::INTEGER,
                e.edge,
                e.node,
                r.real_cost,
                SUM(r.real_cost) OVER (ORDER BY e.ord),
                w.length_m,
                CASE WHEN r.real_cost > 0 THEN w.length_m / r.real_cost * 3.6
                     ELSE COALESCE(w.maxspeed_forward, 30.0) END,
                COALESCE(w.name, ''),
                ST_AsGeoJSON(w.the_geom)::TEXT,
                v_len,
                v_cost
            FROM unnest(v_edges, v_nodes) WITH ORDINALITY AS e(edge, node, ord)
            JOIN osm.ways w ON w.gid = e.edge
            CROSS JOIN LATERAL (
                SELECT (CASE WHEN e.node = w.source THEN w.cost ELSE w.reverse_cost END)::DOUBLE PRECISION
                       AS real_cost
            ) r
            ORDER BY e.ord;
        END IF;

        -- On pénalise aussi les candidats rejetés pour pousser l'exploration ailleurs
        v_used := ARRAY(SELECT DISTINCT x FROM unnest(v_used || v_edges) AS x);
    END LOOP;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION osm.route_car_ksp IS
    'Jusqu''à K itinéraires voiture réellement différents (méthode de pénalité : Dijkstra répété, arêtes déjà utilisées x2 ; overlap <= 75 %, détour <= +50 %). route_id 1 = le plus rapide. Coûts réels. Nom historique : ce n''est plus pgr_ksp.';
