-- =============================================================================
-- Migration 049 — Suppression index jamais scannés (Sprint 26, 2026-09-22)
-- =============================================================================
-- Reprise du stub migration_038 (Sprint 24+) avec les garde-fous appliqués :
--   - stats_reset = NULL sur pg_stat_database (jamais reset), postmaster
--     démarré le 2026-09-09 → au minimum 13 jours de compteurs.
--   - Tous les index ci-dessous : idx_scan = 0 sur cette période, alors que
--     les autres index des mêmes tables cumulent des millions de scans
--     (idx_gold_traffic_channel_computed 6,8 M, trafic_boucles_clean_pkey 9 M).
--   - Aucune PRIMARY KEY ni contrainte UNIQUE touchée.
--
-- Mesures VPS 2026-09-22 :
--   gold.idx_gold_traffic_ml                     2 534 Mo  idx_scan 0
--   silver.idx_silver_boucles_channel            3 701 Mo  idx_scan 0
--   silver.idx_silver_trafic_chn_time_geom       3 530 Mo  idx_scan 0
--     (recréé migration 035 pour build_spatial_mapping ; le planner prend la
--      pkey — 13 runs quotidiens, 0 scan)
--   gold.idx_traffic_features_live_computed_at     116 Mo  idx_scan 0
--     (doublon strict de idx_gold_traffic_features_live_computed_at, 6,5 k scans)
--
-- Gain : ~9,9 Go libérés sur sdb + moins de travail à chaque INSERT sur
-- silver.trafic_boucles_clean (287 runs/jour) et gold.traffic_features_live.
--
-- DROP INDEX CONCURRENTLY : pas de lock table, chaque statement = sa propre
-- transaction (autocommit apply-migrations.sh). IF EXISTS pour idempotence.
-- Rollback : recréer via CREATE INDEX CONCURRENTLY avec les définitions
-- d'origine (migrations 035 / pg_dump schéma pré-migration).
-- =============================================================================

SET lock_timeout = '120s';
SET statement_timeout = '1800s';

\echo '>> 049.1 gold.idx_gold_traffic_ml (2,5 Go)'
DROP INDEX CONCURRENTLY IF EXISTS gold.idx_gold_traffic_ml;

\echo '>> 049.2 silver.idx_silver_boucles_channel (3,7 Go)'
DROP INDEX CONCURRENTLY IF EXISTS silver.idx_silver_boucles_channel;

\echo '>> 049.3 silver.idx_silver_trafic_chn_time_geom (3,5 Go)'
DROP INDEX CONCURRENTLY IF EXISTS silver.idx_silver_trafic_chn_time_geom;

\echo '>> 049.4 gold.idx_traffic_features_live_computed_at (doublon, 116 Mo)'
DROP INDEX CONCURRENTLY IF EXISTS gold.idx_traffic_features_live_computed_at;
