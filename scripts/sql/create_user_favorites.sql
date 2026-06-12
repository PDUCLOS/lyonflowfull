-- =============================================================================
-- LyonFlowFull — Table user_favorites (favoris usager)
-- =============================================================================
-- Sprint 10 (2026-06-12) — Persistance des favoris usager.
--
-- Schéma : user_id (PK composite, texte — pour l'instant "default_user")
--          id     (PK composite, UUID généré en Python)
-- Colonnes : name, origin, destination, usual_mode, usual_duration_min,
--            alert_subscribed, created_at, updated_at
--
-- Usage :
--   psql $POSTGRES_DB -f scripts/sql/create_user_favorites.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS public;

CREATE TABLE IF NOT EXISTS public.user_favorites (
    user_id              TEXT        NOT NULL,
    id                   TEXT        NOT NULL,
    name                 TEXT        NOT NULL,
    origin               TEXT        NOT NULL,
    destination          TEXT        NOT NULL,
    usual_mode           TEXT        NOT NULL,
    usual_duration_min   INTEGER     NOT NULL DEFAULT 0,
    alert_subscribed     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id ON public.user_favorites (user_id);

COMMENT ON TABLE  public.user_favorites IS 'Favoris usager (itinéraires sauvegardés). Sprint 10 — remplace les mocks MOCK_FAVORITES.';
COMMENT ON COLUMN public.user_favorites.user_id            IS 'Identifiant usager (texte, pour l''instant hardcodé default_user)';
COMMENT ON COLUMN public.user_favorites.id                 IS 'UUID généré côté Python (pas SERIAL, pour éviter les collisions)';
COMMENT ON COLUMN public.user_favorites.usual_mode         IS 'Ligne TCLfavorite (ex: M_A, T1, C17)';
COMMENT ON COLUMN public.user_favorites.usual_duration_min IS 'Durée habituelle en minutes';
COMMENT ON COLUMN public.user_favorites.alert_subscribed   IS 'Souscription aux alertes perturbation sur ce favori';
