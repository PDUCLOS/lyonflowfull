-- Backfill lat/lon pour gold.dim_spatial_grid_mapping
-- Sprint 5 a écrit node_idx, properties_twgid, h3_id, etc. mais PAS lat/lon.
-- Le pathfinder (graph.py) filtre WHERE lat IS NOT NULL AND lon IS NOT NULL
-- et ne trouvait donc aucun nœud → 0 segments Dijkstra.
-- Solution : JOIN sur silver.trafic_boucles_clean pour récupérer (ST_Y, ST_X).
--
-- Le canal "LY00107" vs "LYO00002" → propriétés_twgid est varchar, channel_id est text.
-- Comparaison case-sensitive, mais on peut normaliser via UPPER(REPLACE(...)).
--
-- Idempotent : on ne touche que les rows où lat/lon sont NULL.

SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow;

-- 1) Aperçu avant
SELECT 'before' AS step,
       count(*) AS total,
       count(lat) AS with_lat,
       count(lon) AS with_lon
FROM gold.dim_spatial_grid_mapping;

-- 2) Update lat/lon via JOIN (twgid exact match)
UPDATE gold.dim_spatial_grid_mapping m
SET lat  = sub.lat,
    lon  = sub.lon
FROM (
    SELECT DISTINCT ON (channel_id)
        channel_id,
        ST_Y(geom) AS lat,
        ST_X(geom) AS lon
    FROM silver.trafic_boucles_clean
    WHERE geom IS NOT NULL
) sub
WHERE m.properties_twgid = sub.channel_id
  AND (m.lat IS NULL OR m.lon IS NULL);

-- 3) Update lat/lon via normalisation (twgid format LYO00002 vs LYO01L...)
-- (décommenter si besoin après l'étape 2)
-- UPDATE gold.dim_spatial_grid_mapping m
-- SET lat  = sub.lat,
--     lon  = sub.lon
-- FROM (
--     SELECT DISTINCT ON (channel_id_normalized)
--         channel_id,
--         UPPER(REPLACE(channel_id, ' ', '')) AS channel_id_normalized,
--         ST_Y(geom) AS lat,
--         ST_X(geom) AS lon
--     FROM silver.trafic_boucles_clean
--     WHERE geom IS NOT NULL
-- ) sub
-- WHERE UPPER(REPLACE(m.properties_twgid, ' ', '')) = sub.channel_id_normalized
--   AND (m.lat IS NULL OR m.lon IS NULL);

-- 4) Aperçu après
SELECT 'after' AS step,
       count(*) AS total,
       count(lat) AS with_lat,
       count(lon) AS with_lon
FROM gold.dim_spatial_grid_mapping;
