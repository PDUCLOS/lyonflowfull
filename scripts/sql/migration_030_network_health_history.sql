-- =============================================================================
-- Migration 030 : gold.network_health_history (Sprint 21 P4.3)
-- =============================================================================
-- Table d'historique des scores de santé réseau (Axe 5) pour alimenter
-- la sparkline 24h du widget network_health_gauge (Élu).
--
-- Peuplement : DAG ``record_network_health`` (*/15 min) qui INSERT le score
-- actuel calculé par gold.fn_network_health_score() à l'instant T.
--
-- Rétention : 7 jours (purge automatique via maintenance.py). Au-delà, les
-- données sont aggrégées par jour (max/min/mean) dans une table d'archive.
--
-- Volume estimé : 96 snapshots/jour × 7 jours = 672 rows (négligeable).
-- =============================================================================

CREATE TABLE IF NOT EXISTS gold.network_health_history (
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score            NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
    traffic_score    NUMERIC(5,2),
    tcl_score        NUMERIC(5,2),
    velov_score      NUMERIC(5,2),
    meteo_score      NUMERIC(5,2),
    available_sources TEXT[],  -- sources actives au moment du snapshot
    PRIMARY KEY (recorded_at)
);

-- Index pour la lecture sparkline 24h (derniers 96 snapshots max)
CREATE INDEX IF NOT EXISTS idx_network_health_history_recorded_at
    ON gold.network_health_history (recorded_at DESC);

-- Commentaires
COMMENT ON TABLE gold.network_health_history IS
    'Historique 15-min des scores de santé réseau (Axe 5, widget Élu). Rétention 7j.';

COMMENT ON COLUMN gold.network_health_history.recorded_at IS
    'Timestamp du snapshot (UTC, INSERT par DAG */15 min)';

COMMENT ON COLUMN gold.network_health_history.score IS
    'Score global 0-100 (gold.fn_network_health_score())';

COMMENT ON COLUMN gold.network_health_history.traffic_score IS
    'Sous-score trafic routier 0-100 (0 = indispo)';

COMMENT ON COLUMN gold.network_health_history.tcl_score IS
    'Sous-score TCL temps réel 0-100 (0 = indispo)';

COMMENT ON COLUMN gold.network_health_history.velov_score IS
    'Sous-score Vélov 0-100 (0 = indispo)';

COMMENT ON COLUMN gold.network_health_history.meteo_score IS
    'Sous-score météo 0-100 (0 = indispo)';

COMMENT ON COLUMN gold.network_health_history.available_sources IS
    'Liste des sources actives au moment du snapshot (pour redistribution poids)';
