-- =============================================================================
-- Migration 025 — Sprint 17 Axe 6 : gold.data_quality_log (Sprint 17, 2026-06-21)
-- =============================================================================
-- Date        : 2026-06-21
-- Version     : v0.9.0 (cible)
-- Branche     : vps
-- Prérequis   : src/transformation/data_quality.py (Sprint 17 Axe 6)
--               dags/maintenance/maintenance.py (utilise _log_quality_report)
--
-- Crée :
--   gold.data_quality_log — table append-only qui stocke 1 ligne par
--   sous-check (CheckDetail) exécuté par les 3 validators
--   (validate_traffic_features, validate_tcl_realtime, validate_velov_clean).
--
-- Pourquoi une table append-only :
-- * Permet de tracer l'historique des checks qualité dans le temps
--   (tendance, récurrence des problèmes)
-- * UPSERT n'a pas de sens — on veut l'historique, pas juste le dernier
-- * Taille raisonnable : 6 checks × 3-5 sous-checks × 1/jour × 365j
--   = ~10k rows/an. Trivial.
--
-- Schéma :
--   id              : PK
--   checked_at      : timestamp du check (défaut NOW())
--   table_name      : 'gold.traffic_features_live' / 'gold.tcl_vehicle_realtime' / 'silver.velov_clean'
--   check_name      : 'range_speed_kmh' / 'null_ratio_speed_kmh' / 'duplicate_ratio' / 'min_rows' / ...
--   status          : 'ok' | 'warning' | 'critical'
--   metric_value    : valeur observée de la métrique (ex: nb de violations, ratio nulls)
--   threshold       : seuil de la config (ex: 130.0 pour speed_max, 0.30 pour max_null_ratio)
--   details         : texte libre (description, comptage, etc.)
--
-- Index :
--   idx_gold_dql_checked_at_table sur (checked_at DESC, table_name) — le
--   dashboard lit toujours "dernier check par table" (les autres usages
--   ponctuels sont des seq scans acceptables).
--
-- Idempotent : DROP IF EXISTS + CREATE TABLE.
-- =============================================================================


DROP TABLE IF EXISTS gold.data_quality_log CASCADE;

CREATE TABLE gold.data_quality_log (
    id              BIGSERIAL PRIMARY KEY,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    table_name      TEXT NOT NULL,
    check_name      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'warning', 'critical')),
    metric_value    DOUBLE PRECISION,
    threshold       DOUBLE PRECISION,
    details         TEXT
);

-- Index principal : "dernier check par table" (usage dashboard).
CREATE INDEX IF NOT EXISTS idx_gold_dql_checked_at_table
    ON gold.data_quality_log (checked_at DESC, table_name);

COMMENT ON TABLE gold.data_quality_log IS
    'Sprint 17 Axe 6 (2026-06-21) — Append-only log des checks qualité '
    'exécutés par src.transformation.data_quality (3 validators × N '
    'sous-checks × 1/jour via le DAG data_quality_daily). Permet le '
    'suivi temporel et la détection de tendances (récurrence de '
    'critical, dégradation progressive). Spec : '
    'docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §7.';

-- Permissions
GRANT SELECT, INSERT ON gold.data_quality_log TO PUBLIC;
