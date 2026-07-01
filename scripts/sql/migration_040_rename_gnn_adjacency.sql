-- =============================================================================
-- LyonFlowFull — Migration 040 (2026-07-01) — Rename gold.dim_gnn_adjacency
-- =============================================================================
-- CONTEXTE :
--   Le tandem GNN (ST-GRU-GNN) a été archivé Sprint 24+ (2026-06-30,
--   commit 2ffd37b7, archive/legacy/gnn/). En nettoyant les traces GNN du
--   code actif (2026-07-01), on a découvert que gold.dim_gnn_adjacency
--   n'est PAS un artefact mort : elle alimente gold.mv_congestion_propagation_pairs
--   (Sprint 17 Axe 2, migration_024) via le widget propagation_map.py
--   (Pro_3_Correlation.py), refresh */30 min par
--   dags/maintenance/refresh_congestion_propagation.py.
--
--   Le nom "dim_gnn_adjacency" est un artefact historique — la table est
--   un simple index de voisinage spatial (K=2 grid), indépendant du modèle
--   GNN. On la renomme pour ne plus laisser croire qu'elle dépend du GNN.
--
-- IMPORTANT : dags/transforms/build_spatial_mapping.py écrit déjà dans
--   gold.dim_spatial_adjacency (code mis à jour AVANT cette migration).
--   Tant que cette migration n'est pas appliquée, le prochain run du DAG
--   build_spatial_mapping (quotidien 02h30) échouera avec
--   "relation gold.dim_spatial_adjacency does not exist".
--
-- SÛRETÉ :
--   ALTER TABLE ... RENAME est une opération de catalogue pure (pas de
--   réécriture de données, verrou ACCESS EXCLUSIVE bref). Postgres résout
--   les dépendances (vues, FK) par OID, pas par nom — donc
--   gold.mv_congestion_propagation_pairs continue de fonctionner sans
--   recréation.
--
-- IDEMPOTENT : vérifie l'existence avant de renommer (rejouable sans erreur).
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'gold' AND tablename = 'dim_gnn_adjacency'
    ) THEN
        ALTER TABLE gold.dim_gnn_adjacency RENAME TO dim_spatial_adjacency;
        ALTER TABLE gold.dim_spatial_adjacency RENAME CONSTRAINT dim_gnn_adjacency_pkey TO dim_spatial_adjacency_pkey;
    END IF;
END
$$;

-- Tracking
INSERT INTO public.schema_migrations (version) VALUES (40)
ON CONFLICT (version) DO NOTHING;

-- === VERIFY (hors transaction) ===
SELECT
    to_regclass('gold.dim_spatial_adjacency')::text AS table_exists,
    to_regclass('gold.dim_gnn_adjacency')::text AS old_name_should_be_null,
    (SELECT COUNT(*) FROM gold.dim_spatial_adjacency) AS row_count,
    (SELECT COUNT(*) FROM gold.mv_congestion_propagation_pairs) AS mv_still_readable,
    version AS tracked
FROM public.schema_migrations
WHERE version = 40;
