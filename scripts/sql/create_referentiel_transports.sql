-- =============================================================================
-- LyonFlowFull — Référentiel lieux × transports (Sprint VPS-6)
-- =============================================================================
-- Sprint VPS-6 (2026-06-11) — Enrichissement du référentiel lieux avec :
--   * les arrêts/stations TCL qui desservent chaque lieu (N-N)
--   * la distance à pied (en mètres) entre le lieu et l'arrêt
--   * la ligne TCL (line_ref) qui passe à cet arrêt
--   * un ordre de préférence (1 = arrêt le plus proche)
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING.
-- Source : connaissance experte du réseau TCL (Lyon) — pas de geocoder.
-- GTFS complet (stops.txt) prévu Sprint 7+ via open-data-grand-lyon.fr.
--
-- Usage :
--   psql $POSTGRES_DB -f scripts/sql/create_referentiel_transports.sql
--   OU : python scripts/seed_referentiel_transports.py
-- =============================================================================

CREATE TABLE IF NOT EXISTS referentiel.lieux_transports (
    id              SERIAL PRIMARY KEY,
    lieu_id         INTEGER NOT NULL REFERENCES referentiel.lieux_lyon(lieu_id) ON DELETE CASCADE,
    line_ref        TEXT NOT NULL,                   -- ex: 'T1', 'M_A', 'C3', '38'
    line_mode       TEXT NOT NULL,                   -- metro, tram, bus, funicular
    stop_name       TEXT NOT NULL,                   -- ex: 'Place Bellecour'
    distance_m      INTEGER NOT NULL,                -- mètres à pied (estimé main)
    rank            INTEGER NOT NULL DEFAULT 1,      -- 1 = le plus proche du lieu
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    source          TEXT NOT NULL DEFAULT 'expert', -- 'expert' | 'gtfs'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lieu_line_stop UNIQUE (lieu_id, line_ref, stop_name)
);

CREATE INDEX IF NOT EXISTS idx_lieux_transports_lieu ON referentiel.lieux_transports (lieu_id);
CREATE INDEX IF NOT EXISTS idx_lieux_transports_line ON referentiel.lieux_transports (line_ref);
CREATE INDEX IF NOT EXISTS idx_lieux_transports_active ON referentiel.lieux_transports (is_active);

COMMENT ON TABLE  referentiel.lieux_transports IS 'Dessertes TCL par lieu : pour chaque lieu, les arrêts et lignes qui le desservent. Source : expert (Sprint VPS-6), GTFS Sprint 7+.';
COMMENT ON COLUMN referentiel.lieux_transports.distance_m IS 'Distance à pied lieu → arrêt (mètres, estimée à la main).';
COMMENT ON COLUMN referentiel.lieux_transports.rank IS '1 = arrêt le plus proche du lieu, 2 = 2e plus proche, etc.';
COMMENT ON COLUMN referentiel.lieux_transports.source IS 'expert (connaissance réseau) ou gtfs (Sprint 7+ quand GTFS ingéré).';

-- =============================================================================
-- Seed des dessertes — 21 lieux emblématiques × leurs lignes TCL connues
-- =============================================================================
-- Réseau TCL Lyon :
--   * 4 métros : A (Perrache→Vaulx-en-Velin), B (Charpennes→Oullins), C (Hôtel de
--     Ville→Cuire), D (Gare de Vaise→Gare de Vénissieux)
--   * 7 trams : T1 (Debourg→IUT-Feyssine), T2 (Perrache→Saint-Priest), T3, T4,
--     T5, T6, T7 + TB11, TB12 (bronzes/gardes)
--   * 2 funiculaires : F1, F2 (Fourvière)
--   * ~160 lignes de bus (Cxxx = Chrono, lignes numérotées 1-100)
--
-- Données "expert" — cohérence géographique. À recouper Sprint 7+ avec GTFS.
-- =============================================================================

-- Part-Dieu (gare + hub métro/tram/bus)
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Part-Dieu, Lyon'), 'M_B', 'metro',   'Gare Part-Dieu - Vivier Merle', 100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Part-Dieu, Lyon'), 'T_3','tram',    'Part-Dieu - Servient',           150, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Part-Dieu, Lyon'), 'T_4','tram',    'Part-Dieu - Servient',           150, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Part-Dieu, Lyon'), 'C_3','bus',     'Part-Dieu - Vivier Merle',       120, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Perrache (gare + hub métro/tram/bus)
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Perrache, Lyon'), 'M_A', 'metro', 'Perrache',                       50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Perrache, Lyon'), 'M_C', 'metro', 'Perrache',                       50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Perrache, Lyon'), 'T_1', 'tram',  'Perrache',                       80, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Perrache, Lyon'), 'T_2', 'tram',  'Perrache',                       80, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Perrache, Lyon'), 'C_3', 'bus',   'Perrache',                       50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Place Bellecour
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Bellecour, Lyon'), 'M_A', 'metro', 'Bellecour',          50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Bellecour, Lyon'), 'M_C', 'metro', 'Bellecour',          50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Bellecour, Lyon'), 'M_D', 'metro', 'Bellecour',          80, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Bellecour, Lyon'), 'C_3', 'bus',   'Bellecour',          50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Hôtel de Ville
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Hôtel de Ville, Lyon'), 'M_A', 'metro', 'Hôtel de Ville',           30, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Hôtel de Ville, Lyon'), 'M_C', 'metro', 'Hôtel de Ville',           30, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Place des Terreaux (à côté de Hôtel de Ville)
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place des Terreaux, Lyon'), 'M_A', 'metro', 'Hôtel de Ville',  150, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place des Terreaux, Lyon'), 'M_C', 'metro', 'Hôtel de Ville',  150, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place des Terreaux, Lyon'), 'C_13','bus',   'Terreaux',         30, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Opéra de Lyon
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Opéra de Lyon'), 'M_A', 'metro', 'Hôtel de Ville',  200, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Opéra de Lyon'), 'M_C', 'metro', 'Hôtel de Ville',  200, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Vieux Lyon
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Vieux Lyon'), 'M_C', 'metro', 'Vieux Lyon - Cathédrale Saint-Jean', 100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Vieux Lyon'), 'F_1', 'funicular', 'Vieux Lyon', 200, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Vieux Lyon'), 'F_2', 'funicular', 'Vieux Lyon', 200, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Presqu'île (zone large, plusieurs arrêts)
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Presqu''île, Lyon'), 'M_A', 'metro', 'Bellecour',           100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Presqu''île, Lyon'), 'M_C', 'metro', 'Bellecour',           100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Presqu''île, Lyon'), 'M_A', 'metro', 'Hôtel de Ville',      200, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Confluence
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Confluence, Lyon'), 'M_A', 'metro', 'Confluence',                  80, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Confluence, Lyon'), 'T_1', 'tram',  'Hôtel de Région',             300, 2),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Confluence, Lyon'), 'C_7', 'bus',   'Confluence',                  80, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Croix-Rousse
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Croix-Rousse, Lyon'), 'M_C', 'metro', 'Croix-Rousse',           50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Croix-Rousse, Lyon'), 'C_13','bus',   'Croix-Rousse',           80, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Vaise
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Vaise, Lyon'), 'M_D', 'metro', 'Gare de Vaise',           200, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Vaise, Lyon'), 'C_6', 'bus',   'Gare de Vaise',           200, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Gerland
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Gerland, Lyon'), 'M_B', 'metro', 'Stade de Gerland',          150, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Gerland, Lyon'), 'T_1', 'tram',  'Debourg',                   400, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Mermoz
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Mermoz, Lyon'), 'M_D', 'metro', 'Mermoz - Pinel',             200, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Mermoz, Lyon'), 'C_8', 'bus',   'Mermoz',                     100, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Monplaisir
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Monplaisir, Lyon'), 'M_D', 'metro', 'Monplaisir - Lumière', 100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Monplaisir, Lyon'), 'T_4', 'tram',  'Jet d''Eau - Mendes France', 400, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Guillotière
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Guillotière, Lyon'), 'M_D', 'metro', 'Guillotière',           100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Guillotière, Lyon'), 'T_1', 'tram',  'Guillotière',           100, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Place Jean Macé
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Jean Macé, Lyon'), 'M_B', 'metro', 'Place Jean Macé',  50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Place Jean Macé, Lyon'), 'T_2', 'tram',  'Place Jean Macé',  50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Saxe-Gambetta
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Saxe-Gambetta, Lyon'), 'M_B', 'metro', 'Saxe - Gambetta',  50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Saxe-Gambetta, Lyon'), 'M_D', 'metro', 'Saxe - Gambetta',  50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Parc de la Tête d'Or
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Parc de la Tête d''Or, Lyon'), 'M_A', 'metro', 'Masséna',         300, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Parc de la Tête d''Or, Lyon'), 'C_1', 'bus',   'Tête d''Or',       50, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Parc de la Tête d''Or, Lyon'), 'C_2', 'bus',   'Tête d''Or',       50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Université Lyon 3
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Université Lyon 3, Lyon'), 'M_B', 'metro', 'Grange Blanche',  200, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Université Lyon 3, Lyon'), 'T_2', 'tram',  'Grange Blanche',  200, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Université Lyon 3, Lyon'), 'C_3', 'bus',   'Universités',      100, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Villeurbanne
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Villeurbanne'), 'M_A', 'metro', 'Laurent Bonnevay',  400, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Villeurbanne'), 'T_3', 'tram',  'Charpennes',        100, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Villeurbanne'), 'C_3', 'bus',   'Gratte-Ciel',       300, 2)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Bron
INSERT INTO referentiel.lieux_transports (lieu_id, line_ref, line_mode, stop_name, distance_m, rank) VALUES
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Bron'), 'M_D', 'metro', 'Gare de Vénissieux',  600, 1),
    ((SELECT lieu_id FROM referentiel.lieux_lyon WHERE name='Bron'), 'C_17','bus',   'Bron Centre',          50, 1)
ON CONFLICT (lieu_id, line_ref, stop_name) DO NOTHING;

-- Vérification post-seed
DO $$
DECLARE
    n_liens INTEGER;
    n_lieux_avec_liens INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_liens FROM referentiel.lieux_transports;
    SELECT COUNT(DISTINCT lieu_id) INTO n_lieux_avec_liens FROM referentiel.lieux_transports;
    RAISE NOTICE 'referentiel.lieux_transports : % liaisons pour % lieux distincts', n_liens, n_lieux_avec_liens;
END $$;
