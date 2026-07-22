-- =============================================================================
-- LyonFlowFull — Migration 037 (Sprint 24+, 2026-06-29)
-- =============================================================================
-- Optimisation : index sur gold.traffic_features_live.computed_at pour
-- supporter la purge récurrente (cycle */30, task
-- refresh_heavy_mv.purge_old_traffic_features).
--
-- CONTEXTE :
--   gold.traffic_features_live est une table "LIVE" (court terme) qui alimente
--   plusieurs MV gold en aval :
--     - mv_multimodal_grid (grille 1 km, migration 017)
--     - mv_bus_traffic_spatial (zone 100 m, migration 018/036 — fenêtre 48h)
--     - gold.infrastructure_bottlenecks (legacy, à supprimer)
--   Aucune ne requête au-delà de 48-72h. Une purge cyclique divise le volume
--   par ~3-5 sur le VPS 12 Go RAM → scans gold downstream significativement
--   plus rapides (cf. SPRINT_24_FIX_GOLD_STALE.md section 7).
--
-- INDEX :
--   Sans index sur computed_at, le DELETE WHERE computed_at < ... fait un
--   seq scan complet (coûteux sur 1M+ rows). Cet index permet un Index Scan
--   + DELETE ciblé → DELETE en < 1 s même sur 1M rows purgées.
--
-- IDEMPOTENT : CREATE INDEX IF NOT EXISTS + ANALYZE.
--
-- APPLIQUER AVANT le premier déploiement de la tâche purge_old_traffic_features
--     (sinon le 1er DELETE sera un seq scan bloquant).
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_gold_traffic_features_live_computed_at
    ON gold.traffic_features_live (computed_at);

-- Stats fraîches pour le planner (l'index change la sélectivité estimée)
ANALYZE gold.traffic_features_live;

-- Tracking
INSERT INTO public.schema_migrations (version) VALUES (37)
ON CONFLICT (version) DO NOTHING;

-- === VERIFY (hors transaction) ===
SELECT
    to_regclass('gold.traffic_features_live')::text AS table_exists,
    (SELECT COUNT(*) FROM pg_indexes
     WHERE schemaname = 'gold'
       AND tablename = 'traffic_features_live'
       AND indexname = 'idx_gold_traffic_features_live_computed_at'
    ) AS idx_exists,
    (SELECT reltuples::bigint FROM pg_class
     WHERE relname = 'traffic_features_live'
    ) AS approx_rows,
    version AS tracked
FROM public.schema_migrations
WHERE version = 37;
