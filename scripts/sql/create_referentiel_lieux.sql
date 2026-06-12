-- =============================================================================
-- LyonFlowFull — Référentiel lieux Lyon (gares, places, quartiers, parcs, etc.)
-- =============================================================================
-- Sprint VPS-6 (2026-06-11) — Référentiel statique démoctisé.
-- Avant : mock src.data.mock.lyon_addresses.LYON_ADDRESSES (codé en dur).
-- Après : table PostgreSQL ``referentiel.lieux_lyon`` lue via data_loader.
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING.
-- Peut être rejoué sans risque.
--
-- Source : 21 lieux emblématiques de Lyon (gares, places, quartiers, parcs,
-- universités, banlieue). Coordonnées GPS vérifiées à la main (lat/lon WGS84).
--
-- Usage :
--   psql $POSTGRES_DB -f scripts/sql/create_referentiel_lieux.sql
--   OU : python scripts/seed_lieux_lyon.py (idempotent + logging)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS referentiel;

CREATE TABLE IF NOT EXISTS referentiel.lieux_lyon (
    lieu_id     SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    lon         DOUBLE PRECISION NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    type        TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lieux_lyon_type ON referentiel.lieux_lyon (type);
CREATE INDEX IF NOT EXISTS idx_lieux_lyon_active ON referentiel.lieux_lyon (is_active);

COMMENT ON TABLE  referentiel.lieux_lyon IS 'Référentiel statique lieux Lyon (gares, places, quartiers, parcs). Source : main courante, 21 lieux emblématiques. Alimente search_bar + itinerary widgets.';
COMMENT ON COLUMN referentiel.lieux_lyon.lon IS 'Longitude WGS84';
COMMENT ON COLUMN referentiel.lieux_lyon.lat IS 'Latitude WGS84';
COMMENT ON COLUMN referentiel.lieux_lyon.type IS 'Catégorie : gare, place, monument, quartier, parc, universite, banlieue';
COMMENT ON COLUMN referentiel.lieux_lyon.is_active IS 'False = exclu de l''autocomplete (Sprint 7+ : soft delete)';

-- Seed des 21 lieux emblématiques.
INSERT INTO referentiel.lieux_lyon (name, lon, lat, type) VALUES
    -- Gares & hubs
    ('Part-Dieu, Lyon',         4.8589, 45.7607, 'gare'),
    ('Perrache, Lyon',          4.8340, 45.7480, 'gare'),
    -- Places & monuments
    ('Place Bellecour, Lyon',   4.8324, 45.7575, 'place'),
    ('Hôtel de Ville, Lyon',    4.8342, 45.7672, 'monument'),
    ('Place des Terreaux, Lyon',4.8340, 45.7671, 'place'),
    ('Opéra de Lyon',           4.8362, 45.7692, 'monument'),
    -- Quartiers
    ('Vieux Lyon',              4.8271, 45.7626, 'quartier'),
    ('Presqu''île, Lyon',       4.8340, 45.7580, 'quartier'),
    ('Confluence, Lyon',        4.8165, 45.7405, 'quartier'),
    ('Croix-Rousse, Lyon',      4.8281, 45.7773, 'quartier'),
    ('Vaise, Lyon',             4.8058, 45.7798, 'quartier'),
    ('Gerland, Lyon',           4.8339, 45.7280, 'quartier'),
    ('Mermoz, Lyon',            4.8700, 45.7310, 'quartier'),
    ('Monplaisir, Lyon',        4.8603, 45.7434, 'quartier'),
    ('Guillotière, Lyon',       4.8408, 45.7431, 'quartier'),
    -- Places
    ('Place Jean Macé, Lyon',   4.8417, 45.7456, 'place'),
    ('Saxe-Gambetta, Lyon',     4.8461, 45.7496, 'place'),
    -- Parcs & universités
    ('Parc de la Tête d''Or, Lyon', 4.8525, 45.7745, 'parc'),
    ('Université Lyon 3, Lyon', 4.8513, 45.7481, 'universite'),
    -- Banlieue
    ('Villeurbanne',            4.8810, 45.7715, 'banlieue'),
    ('Bron',                    4.9100, 45.7370, 'banlieue')
ON CONFLICT (name) DO NOTHING;

-- Vérification post-seed
DO $$
DECLARE
    n_lieux INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_lieux FROM referentiel.lieux_lyon;
    RAISE NOTICE 'referentiel.lieux_lyon : % lieux seedés', n_lieux;
END $$;
