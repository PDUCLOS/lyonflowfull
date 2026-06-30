-- =============================================================================
-- LyonFlowFull — Migration 039 (Sprint P3.4+, 2026-06-30) —
-- Application manuelle de alembic 0002_perf_optimizations
-- =============================================================================
--
-- CONTEXTE :
-- alembic upgrade head sur VPS a échoué à cause de :
-- 1. venv cassé sur VPS (.venv/bin/python3 → /opt/homebrew/opt/python@3.14/bin/python3.14,
--    chemin macOS qui n'existe pas sur Ubuntu).
-- 2. Chaîne alembic cassée : alembic_version en DB = 0007_gold_views_and_history
--    mais le fichier 0007 est absent du repo (alembic/versions/ contient
--    uniquement 0001_initial.py et 0002_perf_optimizations.py).
--    alembic refuse de downgrader.
--
-- STRATÉGIE :
-- Application manuelle du DDL de 0002_perf_optimizations directement via
-- psql (équivalent fonctionnel). Le tracking alembic_version reste à 0007
-- (incohérence acceptée, à fixer en Sprint P3.5 quand la chaîne alembic
-- sera ré-alignée). Le tracking maison schema_migrations reçoit la
-- version 282 (282 parce que la table avait déjà 281 = version fantôme
-- héritée, le MAX(version)+1 a sauté à 282).
--
-- IDEMPOTENT : tout est CREATE OR REPLACE FUNCTION / ALTER TABLE SET (...).
-- Safe à re-runs.
--
-- CONTENU :
-- 1. Autovacuum agressif sur gold.tcl_vehicle_realtime (DELETE massif
--    toutes les 10 min) + gold.traffic_features_live (UPSERT massif).
-- 2. Fonctions PL/pgSQL _is_ferie(date) + _is_vacances(date) créées
--    permanent en DB (avant : _ensure_helpers() les recréait 3-5 fois
--    par DAG run = DDL inutile).
--
-- VERIFIÉ :
--   SELECT proname FROM pg_proc WHERE proname IN ('_is_ferie', '_is_vacances');
--   → 2 rows (présentes)
--   SELECT _is_ferie('2026-01-01'::date);
--   → t (1er janvier = férié)
--
-- =============================================================================

-- 1. Autovacuum gold.tcl_vehicle_realtime (DELETE massif */10)
-- vacuum_scale_factor = 0.01 → vacuum démarre à 1% dead tuples
-- (au lieu du défaut 20% par table, qui ne se déclenche jamais
-- sur cette table haute-fréquence).
ALTER TABLE gold.tcl_vehicle_realtime SET (
    autovacuum_vacuum_scale_factor  = 0.01,
    autovacuum_vacuum_cost_delay    = 2,
    autovacuum_analyze_scale_factor = 0.005
);

-- 2. Autovacuum gold.traffic_features_live (UPSERT massif */10)
-- Params légèrement moins agressifs (UPSERT ne génère pas autant
-- de dead tuples qu'un DELETE massif).
ALTER TABLE gold.traffic_features_live SET (
    autovacuum_vacuum_scale_factor  = 0.02,
    autovacuum_vacuum_cost_delay    = 5,
    autovacuum_analyze_scale_factor = 0.01
);

-- 3. PL/pgSQL — férié (date fixe ou raw_data date)
CREATE OR REPLACE FUNCTION _is_ferie(d date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM bronze.jours_feries jf
        WHERE jf.date_ferie = d
           OR (jf.raw_data IS NOT NULL
               AND (jf.raw_data->>'date')::date = d)
    );
$$;

-- 4. PL/pgSQL — vacances scolaires Zone A (schéma direct ou raw_data.records)
CREATE OR REPLACE FUNCTION _is_vacances(d date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM bronze.calendrier_scolaire cs
        WHERE cs.start_date <= d
          AND cs.end_date   >= d
          AND cs.zone ILIKE 'A'
    )
    OR EXISTS (
        SELECT 1
        FROM bronze.calendrier_scolaire cs,
             LATERAL jsonb_array_elements(
                 CASE WHEN jsonb_typeof(cs.raw_data->'records') = 'array'
                      THEN cs.raw_data->'records'
                      ELSE '[]'::jsonb END
             ) AS rec
        WHERE cs.start_date IS NULL
          AND (rec->'fields'->>'start_date')::date <= d
          AND (rec->'fields'->>'end_date')::date   >= d
          AND COALESCE(rec->'fields'->>'zones', '') ILIKE '%zone a%'
    );
$$;
