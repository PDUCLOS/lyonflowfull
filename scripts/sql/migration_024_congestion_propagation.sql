-- =============================================================================
-- Migration 024 — Sprint 17 Axe 2 : Propagation de congestion (v3)
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.9.0 (cible)
-- Branche     : main
-- Prérequis   : Sprint 8+ (gold.traffic_features_live schéma v0.3.1)
--               Sprint 9+ (gold.dim_spatial_grid_mapping peuplé)
--               build_spatial_mapping.py tourne → dim_gnn_adjacency alimenté
--
-- Crée :
--   gold.mv_congestion_propagation_pairs — Vue matérialisée : index des
--   paires de capteurs adjacents (K=2 grid via gold.dim_gnn_adjacency)
--   avec lat/lon des 2 nœuds. PAS de CORR calculée ici (trop coûteux
--   en SQL pur : 4072 paires × 4 subqueries × lag = timeout 4+ min).
--
--   Le widget ``propagation_map.py`` charge cette MV + les séries
--   temporelles depuis gold.traffic_features_live et calcule les CORR
--   en Python (pandas/numpy, vectorisé, ~10s pour 1000 paires × 6h).
--
-- Notes sur le schéma réel (vs spec d'origine) :
--   * La spec d'origine utilise ``channel_id`` directement. Le schéma
--     réel a ``dim_gnn_adjacency`` (PK = (node_u, node_v), 4072 arêtes
--     K=2) et ``dim_spatial_grid_mapping`` (mapping node_idx ↔ channel_id
--     via properties_twgid). On JOIN via properties_twgid pour ramener
--     les channel_id Grand Lyon réels.
--   * Sprint 17 (2026-06-20) — découplage node_idx ↔ channel_id :
--     la MV stocke les channel_id + lat/lon des 2 nœuds (pas les
--     node_idx) pour rester consommable directement par le widget Folium
--     (qui a besoin de lat/lon pour les flèches directionnelles).
--
-- Notes Sprint 17 v3 (2026-06-20) — approche pragmatique :
--   * Test initial 24h × 4 subqueries CORR par paire : timeout 3 min
--   * Test v2 6h × single-pass : timeout 4 min (CTE JOIN explose en cartésien)
--   * v3 : la MV stocke JUSTE les paires (rapide, < 5s). Le widget
--     calcule les CORR en Python (vectorisé). C'est 10-100x plus rapide
--     que SQL pur pour ce genre de calcul itératif.
--   * Limite reconnue : la spec §3.2 voulait CORR en SQL (pour
--     réutilisation par d'autres requêtes). Sprint 17 fait le compromis
--     perf vs spec, en gardant les lat/lon pré-calculés (gros gain).
--   * Phase 2 spec §3.3 (Granger statsmodels) reste hors scope Sprint 17.
--
-- Refresh :
--   Toutes les 30 min par ``dags/maintenance/refresh_congestion_propagation.py``
--   (REFRESH MATERIALIZED VIEW CONCURRENTLY, donc index unique requis).
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW + index unique.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : mv_congestion_propagation_pairs
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_congestion_propagation_pairs CASCADE;

CREATE MATERIALIZED VIEW gold.mv_congestion_propagation_pairs AS
SELECT DISTINCT
    mu.properties_twgid    AS node_a,
    mu.lat                 AS lat_a,
    mu.lon                 AS lon_a,
    mv.properties_twgid    AS node_b,
    mv.lat                 AS lat_b,
    mv.lon                 AS lon_b
FROM gold.dim_gnn_adjacency adj
JOIN gold.dim_spatial_grid_mapping mu ON mu.node_idx = adj.node_u
JOIN gold.dim_spatial_grid_mapping mv ON mv.node_idx = adj.node_v
WHERE adj.is_connected = TRUE
  AND adj.node_u <> adj.node_v
  AND mu.properties_twgid IS NOT NULL
  AND mv.properties_twgid IS NOT NULL
ORDER BY node_a, node_b;

-- Index unique sur (node_a, node_b) : permet REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_gold_mv_congestion_propagation_pairs_pk
    ON gold.mv_congestion_propagation_pairs (node_a, node_b);

COMMENT ON MATERIALIZED VIEW gold.mv_congestion_propagation_pairs IS
    'Sprint 17 Axe 2 v3 — Index des paires de capteurs adjacents (K=2 grid
     via gold.dim_gnn_adjacency) avec lat/lon des 2 nœuds. PAS de CORR
     calculée ici (trop coûteux en SQL). Le widget propagation_map calcule
     les CORR en Python depuis gold.traffic_features_live (6h × 5min).
     Refresh */30 min par dags/maintenance/refresh_congestion_propagation.py.
     Spec : docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §3.';

-- Permissions
GRANT SELECT ON gold.mv_congestion_propagation_pairs TO PUBLIC;
