-- Migration 035 (réécrite v3 — 2026-06-30) — MV dernière position connue par channel
--
-- Bug originel : `build_spatial_mapping` exécutait à chaque run un
--   SELECT DISTINCT ON (channel_id) ORDER BY channel_id, measurement_time DESC
--   sur silver.trafic_boucles_clean (~1.55M rows × geom). Sans index composite,
--   sort complet en RAM → swap → disque sdb 100% util → query active 24h+.
--
-- Pourquoi v1 a échoué (2026-06-29) : CREATE INDEX non-concurrent = SHARE lock
--   sur silver.trafic_boucles_clean → bloque les INSERT collect_bronze 5+ min.
-- Pourquoi v2 a re-échoué (2026-06-30) : exécutions CONCURRENTES (plusieurs
--   agents en parallèle) ont lancé 3× le même CREATE INDEX en
--   parallèle → contention + cancels → index laissés INVALIDES.
--
-- Fix v3 — ajoute les 2 garde-fous manquants à v2 :
--   A) pg_try_advisory_lock : une seule session applique 035 à la fois.
--      Toute exécution concurrente s'ABORTE proprement (au lieu de racer).
--   B) Nettoyage des index INVALIDES (restes de CONCURRENTLY cancellés) :
--      sinon `IF NOT EXISTS` skipe un index cassé → MV en full sort.
--
-- Exécution : psql -f (AUTOCOMMIT — ne PAS wrapper le fichier dans BEGIN/COMMIT
--   global, sinon CREATE/DROP INDEX CONCURRENTLY échoue « cannot run inside a
--   transaction block »). Monitorer via pg_stat_progress_create_index.

-- =============================================================================
-- GARDE-FOU A — verrou anti-concurrence (session-level, survit aux commits)
-- =============================================================================
SELECT pg_try_advisory_lock(351035) AS got_lock \gset
\if :got_lock
  \echo '>> Lock 351035 acquis — application de la migration 035.'
\else
  \echo '!! Migration 035 déjà en cours dans une autre session — ABORT (pas de race).'
  \q
\endif

-- =============================================================================
-- GARDE-FOU B — purge d'un index INVALIDE laissé par un CONCURRENTLY cancellé
-- =============================================================================
-- DROP seulement si l'index existe ET est invalide (indisvalid = false).
-- Un index invalide n'est pas utilisé par le planner → la MV retomberait en
-- full sort. DROP INDEX CONCURRENTLY = non-bloquant (autocommit, hors txn).
SELECT (
    EXISTS (SELECT 1 FROM pg_class WHERE relname = 'idx_silver_trafic_chn_time_geom')
    AND NOT EXISTS (
        SELECT 1 FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = 'idx_silver_trafic_chn_time_geom' AND i.indisvalid
    )
) AS need_drop \gset
\if :need_drop
  \echo '>> Index idx_silver_trafic_chn_time_geom INVALIDE détecté → DROP CONCURRENTLY.'
  DROP INDEX CONCURRENTLY IF EXISTS silver.idx_silver_trafic_chn_time_geom;
\endif

-- =============================================================================
-- ÉTAPE 1/3 — Index composite partiel, AUTOCOMMIT (non-bloquant)
-- =============================================================================
-- CONCURRENTLY = ShareUpdateExclusive → NE BLOQUE PAS les INSERT collect_bronze.
-- WHERE geom IS NOT NULL = index PARTIEL (ignore les capteurs désactivés).
-- statement_timeout 30 min : marge pour ~1.5M rows + geom sur disque throttlé.
-- Si timeout : l'index reste invalide → le garde-fou B le purge au prochain run.
-- Suivi temps réel : SELECT * FROM pg_stat_progress_create_index;
SET statement_timeout = '1800000';  -- 30 min

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_silver_trafic_chn_time_geom
    ON silver.trafic_boucles_clean (channel_id, measurement_time DESC)
    WHERE geom IS NOT NULL;

-- Rafraîchit les stats → le planner choisit l'index pour la MV (et débloque EXPLAIN).
ANALYZE silver.trafic_boucles_clean;

-- =============================================================================
-- ÉTAPE 2/3 — Vue matérialisée (transaction courte)
-- =============================================================================
-- Le planner utilise idx_silver_trafic_chn_time_geom → index scan ~1 row par
-- channel (~1500 sensors), plus de sort sur 1.5M rows → quasi instantané.
-- (Premier run a timeout 10 min — plan erroné pendant contention de locks.
-- Maintenant que l'index existe + ANALYZE fait, plan = Index Scan. Timeout 30
-- min pour absorber un éventuel disque très throttlé.)
SET statement_timeout = '1800000';  -- 30 min

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS gold.mv_latest_sensor_position CASCADE;

CREATE MATERIALIZED VIEW gold.mv_latest_sensor_position AS
SELECT DISTINCT ON (channel_id)
    channel_id,
    ST_Y(geom)::double precision AS lat,
    ST_X(geom)::double precision AS lon,
    geom,
    measurement_time AS last_seen_at
FROM silver.trafic_boucles_clean
WHERE geom IS NOT NULL
ORDER BY channel_id, measurement_time DESC;

-- Index UNIQUE obligatoire pour un futur REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_sensor_position_chn
    ON gold.mv_latest_sensor_position (channel_id);

GRANT SELECT ON gold.mv_latest_sensor_position TO lyonflow;

ANALYZE gold.mv_latest_sensor_position;

INSERT INTO public.schema_migrations (version) VALUES (35)
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- =============================================================================
-- Libération du verrou + vérification (hors transaction)
-- =============================================================================
SELECT pg_advisory_unlock(351035) AS lock_released;

SELECT
    to_regclass('gold.mv_latest_sensor_position')::text AS mv_exists,
    (SELECT COUNT(*) FROM gold.mv_latest_sensor_position) AS channel_count,
    (SELECT indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
     WHERE c.relname = 'idx_silver_trafic_chn_time_geom') AS index_valid,
    (SELECT version FROM public.schema_migrations WHERE version = 35) AS tracked;
