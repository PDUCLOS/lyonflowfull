-- =============================================================================
-- Migration 024 — Sprint 17 Axe 2 : Propagation de congestion
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.9.0 (cible)
-- Branche     : vps
-- Prérequis   : Sprint 8+ (gold.traffic_features_live schéma v0.3.1)
--               Sprint 9+ (gold.dim_spatial_grid_mapping peuplé)
--               build_spatial_mapping.py tourne → dim_gnn_adjacency alimenté
--
-- Crée :
--   gold.mv_congestion_propagation — Vue matérialisée : pour chaque paire
--                                   de capteurs adjacents (K=2 grid),
--                                   calcule la lag cross-corrélation des
--                                   vitesses (5/10 min) sur 24h.
--                                   Classification :
--                                     * propagation_a_to_b : corr_lag5 > corr_lag0 + 0.05
--                                     * co_congested       : corr_lag0 > 0.7
--                                     * independent        : reste
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
--   * Limite pragmatique (cf. spec §3.2) : CORR sur 24h × paires
--     K=2. Coût estimé : 4072 paires × 5min × 24h = ~2.4M rows en
--     scan, acceptable sur VPS 12 Go RAM.
--
-- Refresh :
--   Toutes les 30 min par ``dags/maintenance/refresh_congestion_propagation.py``
--   (REFRESH MATERIALIZED VIEW CONCURRENTLY, donc index unique requis).
--   Coût moyen (CORR sur 24h × paires) — refresh 30 min évite
--   de surcharger la DB en permanence.
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW + index unique.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : mv_congestion_propagation
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_congestion_propagation CASCADE;

CREATE MATERIALIZED VIEW gold.mv_congestion_propagation AS
WITH
-- Séries temporelles 5 min sur 24h pour les nœuds du graphe
speed_series AS (
    SELECT
        tf.channel_id,
        DATE_TRUNC('minute', tf.fetched_at) - (EXTRACT(MINUTE FROM tf.fetched_at)::int % 5) * INTERVAL '1 minute' AS ts_5min,
        AVG(tf.speed_kmh)                                                   AS speed
    FROM gold.traffic_features_live tf
    WHERE tf.fetched_at > NOW() - INTERVAL '24 hours'
      AND tf.speed_kmh IS NOT NULL
    GROUP BY tf.channel_id, DATE_TRUNC('minute', tf.fetched_at) - (EXTRACT(MINUTE FROM tf.fetched_at)::int % 5) * INTERVAL '1 minute'
),
-- Paires de capteurs adjacents via dim_gnn_adjacency + dim_spatial_grid_mapping
pairs AS (
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
)
SELECT
    p.node_a,
    p.node_b,
    p.lat_a,
    p.lon_a,
    p.lat_b,
    p.lon_b,
    -- Corrélation Pearson à lag 0 (simultanée)
    COALESCE(
        (SELECT CORR(a.speed, b.speed)
         FROM speed_series a
         JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
         WHERE a.channel_id = p.node_a),
        0
    )::numeric(6,3)                                                  AS corr_lag0,
    -- Corrélation à lag +5 min : b(t+5min) vs a(t) → A cause-t-il B ?
    COALESCE(
        (SELECT CORR(a.speed, b_lag1.speed)
         FROM speed_series a
         JOIN speed_series b_lag1
           ON b_lag1.channel_id = p.node_b
          AND b_lag1.ts_5min = a.ts_5min + INTERVAL '5 minutes'
         WHERE a.channel_id = p.node_a),
        0
    )::numeric(6,3)                                                  AS corr_lag5min,
    -- Corrélation à lag +10 min
    COALESCE(
        (SELECT CORR(a.speed, b_lag2.speed)
         FROM speed_series a
         JOIN speed_series b_lag2
           ON b_lag2.channel_id = p.node_b
          AND b_lag2.ts_5min = a.ts_5min + INTERVAL '10 minutes'
         WHERE a.channel_id = p.node_a),
        0
    )::numeric(6,3)                                                  AS corr_lag10min,
    -- Classification lag cross-correlation (cf. spec §3.2)
    -- propagation_a_to_b : lag 5 min améliore la corrélation de +0.05
    --                      → A précède B (congestion se propage de A vers B)
    -- co_congested       : corr_lag0 > 0.7 → même cause externe (chantier, etc.)
    -- independent        : reste
    CASE
        WHEN (SELECT CORR(a.speed, b_lag1.speed)
              FROM speed_series a
              JOIN speed_series b_lag1
                ON b_lag1.channel_id = p.node_b
               AND b_lag1.ts_5min = a.ts_5min + INTERVAL '5 minutes'
              WHERE a.channel_id = p.node_a)
             > (SELECT CORR(a.speed, b.speed)
                FROM speed_series a
                JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
                WHERE a.channel_id = p.node_a) + 0.05
        THEN 'propagation_a_to_b'
        WHEN (SELECT CORR(a.speed, b.speed)
              FROM speed_series a
              JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
              WHERE a.channel_id = p.node_a) > 0.7
        THEN 'co_congested'
        ELSE 'independent'
    END                                                              AS relationship,
    NOW()                                                            AS computed_at
FROM pairs p
ORDER BY
    CASE
        WHEN (SELECT CORR(a.speed, b_lag1.speed)
              FROM speed_series a
              JOIN speed_series b_lag1
                ON b_lag1.channel_id = p.node_b
               AND b_lag1.ts_5min = a.ts_5min + INTERVAL '5 minutes'
              WHERE a.channel_id = p.node_a)
             > (SELECT CORR(a.speed, b.speed)
                FROM speed_series a
                JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
                WHERE a.channel_id = p.node_a) + 0.05
        THEN 1
        WHEN (SELECT CORR(a.speed, b.speed)
              FROM speed_series a
              JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
              WHERE a.channel_id = p.node_a) > 0.7
        THEN 2
        ELSE 3
    END,
    node_a,
    node_b;

-- Index unique sur (node_a, node_b) : permet REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_gold_mv_congestion_propagation_pk
    ON gold.mv_congestion_propagation (node_a, node_b);

-- Index secondaire sur relationship (filtre widget "par type")
CREATE INDEX IF NOT EXISTS idx_gold_mv_congestion_propagation_relationship
    ON gold.mv_congestion_propagation (relationship);

COMMENT ON MATERIALIZED VIEW gold.mv_congestion_propagation IS
    'Sprint 17 Axe 2 — Propagation de congestion entre paires de capteurs
     adjacents (K=2 grid via gold.dim_gnn_adjacency). Lag cross-corrélation
     0/5/10 min sur 24h de gold.traffic_features_live (5-min buckets).
     3 classes : propagation_a_to_b (lag 5min ameliore corr > 0.05),
     co_congested (corr_lag0 > 0.7), independent (reste).
     Sert au widget propagation_map (Pro_3_Correlation) pour la carte
     Folium avec fleches directionnelles entre capteurs A -> B.
     Refresh */30 min par dags/maintenance/refresh_congestion_propagation.py.
     Spec : docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §3.';

-- Permissions
GRANT SELECT ON gold.mv_congestion_propagation TO PUBLIC;
