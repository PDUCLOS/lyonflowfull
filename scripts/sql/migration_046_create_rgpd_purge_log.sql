-- Migration 046 — Crée rgpd.purge_log (manquante depuis toujours)
--
-- dags/maintenance/maintenance.py::_purge_table() fait un INSERT dans
-- rgpd.purge_log après chaque DELETE, dans la même transaction. La table
-- n'a jamais existé : chaque purge échoue sur UndefinedTable et la
-- transaction entière (DELETE inclus) est rollback. purge_bronze est à
-- 13/13 échecs sur 14 jours — zéro ligne bronze purgée malgré la politique
-- de rétention documentée (CLAUDE.md règle "Purge auto Bronze").

CREATE SCHEMA IF NOT EXISTS rgpd;

CREATE TABLE IF NOT EXISTS rgpd.purge_log (
    id              BIGSERIAL PRIMARY KEY,
    purged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_name     TEXT NOT NULL,
    table_name      TEXT NOT NULL,
    rows_purged     BIGINT NOT NULL,
    retention_days  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rgpd_purge_log_purged_at ON rgpd.purge_log (purged_at DESC);
