-- =============================================================================
-- LyonFlowFull — Vue materialisee mapping LYO <-> properties_twgid (H3 hash)
-- =============================================================================
-- Sprint 10+ (2026-06-12) — Le pipeline bronze→silver→gold stocke
-- channel_id au format LYO0xxxx (ex. LYO02251) dans
-- gold.traffic_features_live, mais gold.dim_spatial_grid_mapping utilise
-- properties_twgid (entier en string, ex. "537"). Les deux identifiants
-- désignent le même capteur physique, mais aucune FK ne les relie.
--
-- Conséquence : le pathfinder JOIN les deux sur
-- ``t.channel_id = m.properties_twgid`` → 0 match → speed_map vide →
-- vitesse fallback 30.0 km/h sur tous les nœuds du graphe routier.
--
-- Solution Sprint 10+ : vue matérialisée ``gold.mv_twgid_to_lyo`` qui
-- associe pour chaque properties_twgid le channel_id LYO0xxxx du capteur
-- partageant la même cellule H3 res 11 (rayon ~50m). O(1) hash join, pas
-- de calcul de distance. Refrshable par le DAG de maintenance.
--
-- Idempotent : DROP + CREATE.
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS gold.mv_twgid_to_lyo CASCADE;

CREATE MATERIALIZED VIEW gold.mv_twgid_to_lyo AS
WITH lyo_h3 AS (
    -- Index LYO channel_id par cellule H3 res 11
    SELECT
        channel_id,
        lat,
        lon,
        h3_lat_lng_to_cell(lat, lon, 11) AS h3_cell
    FROM (
        SELECT DISTINCT ON (channel_id)
            channel_id,
            lat,
            lon
        FROM gold.traffic_features_live
        WHERE lat IS NOT NULL
          AND lon IS NOT NULL
          AND computed_at > NOW() - INTERVAL '14 days'
        ORDER BY channel_id, computed_at DESC
    ) latest
),
twgid_h3 AS (
    -- Index properties_twgid par cellule H3 res 11
    SELECT
        properties_twgid,
        lat,
        lon,
        h3_lat_lng_to_cell(lat, lon, 11) AS h3_cell
    FROM gold.dim_spatial_grid_mapping
    WHERE lat IS NOT NULL
      AND lon IS NOT NULL
)
SELECT
    t.properties_twgid,
    t.lat              AS twgid_lat,
    t.lon              AS twgid_lon,
    l.channel_id,
    l.lat              AS lyo_lat,
    l.lon              AS lyo_lon
FROM twgid_h3 t
JOIN lyo_h3 l
  ON l.h3_cell = t.h3_cell;

CREATE UNIQUE INDEX idx_mv_twgid_to_lyo_pk
    ON gold.mv_twgid_to_lyo (properties_twgid);
CREATE INDEX idx_mv_twgid_to_lyo_channel
    ON gold.mv_twgid_to_lyo (channel_id);

COMMENT ON MATERIALIZED VIEW gold.mv_twgid_to_lyo IS
    'Sprint 10+ (2026-06-12) — Mapping properties_twgid <-> channel_id LYO '
    'via H3 res 11 hash join (~50m). Refreshable par DAG. '
    'Corrige le bug pathfinder 30.0 km/h (Sprint 8+).';
