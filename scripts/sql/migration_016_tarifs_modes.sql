-- =============================================================================
-- LyonFlowFull — Migration 016 (Sprint 15+, 2026-06-19)
-- =============================================================================
-- Table référentielle ``gold.tarifs_modes`` — grille tarifaire des modes
-- de transport Lyon (Sprint 15+ comparateur modes Usager).
--
-- Sources :
--   - SYTRAL TCL 2026 (tickets unitaires, carnets, abonnements)
--   - Ville de Lyon 2025 (parking voirie zones 1/2/3)
--   - Vélov SYTRAL 2026 (tickets + abonnements)
--   - SP95 prix moyen France 2026-05 (carburant voiture)
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING.
-- Mis à jour manuellement 1-2x/an quand SYTRAL/Ville de Lyon publient leurs
-- nouvelles grilles tarifaires.
--
-- Sprint 15+ usage :
--   - Phase 1 : constantes hardcodées dans ``src/routing/eco_calculator.py``
--     (zéro dépendance DB pour le calcul d'impact, rapide).
--   - Phase 2+ : lecture optionnelle via ``src/data/db_query.py`` pour gérer
--     plusieurs zones parking, abonnements par âge, etc. Hook documenté dans
--     ``eco_calculator._voiture_parking_cost_placeholder()``.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS gold.tarifs_modes (
    id              SERIAL PRIMARY KEY,
    mode            TEXT NOT NULL,            -- 'tcl' | 'velov' | 'voiture'
    produit         TEXT NOT NULL,            -- 'ticket_unitaire', 'velov_1jour', etc.
    produit_label   TEXT NOT NULL,
    age_min         INT DEFAULT NULL,
    age_max         INT DEFAULT NULL,
    prix_eur        NUMERIC(6,3) NOT NULL,
    duree_min       INT DEFAULT NULL,         -- durée de validité (min), NULL = N/A
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mode, produit, age_min, age_max)
);

CREATE INDEX IF NOT EXISTS idx_tarifs_modes_mode
    ON gold.tarifs_modes (mode);

COMMENT ON TABLE gold.tarifs_modes IS
    'Sprint 15+ (2026-06-19) — Référentiel tarifs modes de transport Lyon. '
    'Sources : SYTRAL TCL 2026, Ville de Lyon 2025, Vélov SYTRAL 2026. '
    'Mis à jour 1-2x/an manuellement (publication grilles SYTRAL/Ville de Lyon). '
    'Phase 1 : utilisé via constantes dans src/routing/eco_calculator.py. '
    'Phase 2+ : lecture directe pour tarifs dynamiques (parking zones, abos âge).';


-- -----------------------------------------------------------------------------
-- Données de référence
-- -----------------------------------------------------------------------------

INSERT INTO gold.tarifs_modes
    (mode, produit, produit_label, age_min, age_max, prix_eur, duree_min, notes)
VALUES
    -- TCL (SYTRAL 2026)
    ('tcl', 'ticket_unitaire',     'Ticket unitaire TCL',         NULL, NULL,  2.05,   60, '1 trajet, validité 1h'),
    ('tcl', 'ticket_aller_retour', 'Ticket aller-retour TCL',     NULL, NULL,  4.00,  120, '2 trajets'),
    ('tcl', 'ticket_24h',          'Ticket 24h TCL',              NULL, NULL,  6.30, 1440, 'Illimité 24h'),
    ('tcl', 'ticket_jeune',        'Ticket jeunes (-25 ans)',        0,   24,  1.60,   60, NULL),
    ('tcl', 'ticket_enfant',       'Ticket enfant (4-10 ans)',       4,   10,  1.00,   60, NULL),
    ('tcl', 'ticket_gratuit',      'Gratuit (0-3 ans)',              0,    3,  0.00, NULL, NULL),
    ('tcl', 'carnet_10',           'Carnet 10 voyages',           NULL, NULL, 17.20, NULL, '1.72€/trajet'),

    -- Vélov (SYTRAL 2026)
    ('velov', 'velov_ticket_1j',   'Vélov ticket courte durée',   NULL, NULL,  1.50, 1440, '30min gratuites puis 2€/30min'),
    ('velov', 'velov_abo_mensuel', 'Vélov abonnement mensuel',    NULL, NULL,  5.00, NULL, '30min gratuites incluses'),
    ('velov', 'velov_abo_annuel',  'Vélov abonnement annuel',     NULL, NULL, 39.00, NULL, '30min gratuites incluses'),

    -- Voiture (référence coûts moyens Lyon)
    ('voiture', 'sp95_litre',      'SP95 (prix au litre)',        NULL, NULL,  1.85, NULL, 'Prix moyen 2026-05'),
    ('voiture', 'parking_z1_1h',   'Parking voirie zone 1 (1h)',  NULL, NULL,  1.00,   60, 'Véhicule sobre <1t'),
    ('voiture', 'parking_z1_2h',   'Parking voirie zone 1 (2h)',  NULL, NULL,  3.00,  120, 'Véhicule sobre <1t'),
    ('voiture', 'parking_z2_1h',   'Parking voirie zone 2 (1h)',  NULL, NULL,  2.00,   60, 'Véhicule standard 1-1.5t'),
    ('voiture', 'parking_z2_2h',   'Parking voirie zone 2 (2h)',  NULL, NULL,  6.00,  120, 'Véhicule standard 1-1.5t'),
    ('voiture', 'parking_z3_1h',   'Parking voirie zone 3 (1h)',  NULL, NULL,  3.50,   60, 'Véhicule lourd >1.5t')
ON CONFLICT DO NOTHING;


-- -----------------------------------------------------------------------------
-- Stats informatives (sanity check)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n_total INTEGER;
    n_tcl INTEGER;
    n_velov INTEGER;
    n_voiture INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_total FROM gold.tarifs_modes;
    SELECT COUNT(*) INTO n_tcl FROM gold.tarifs_modes WHERE mode = 'tcl';
    SELECT COUNT(*) INTO n_velov FROM gold.tarifs_modes WHERE mode = 'velov';
    SELECT COUNT(*) INTO n_voiture FROM gold.tarifs_modes WHERE mode = 'voiture';
    RAISE NOTICE 'gold.tarifs_modes : % enregistrements (tcl=%, velov=%, voiture=%)',
        n_total, n_tcl, n_velov, n_voiture;
    IF n_total < 15 THEN
        RAISE WARNING 'gold.tarifs_modes a moins de 15 enregistrements (%), vérifier import.', n_total;
    END IF;
END $$;


COMMIT;


-- =============================================================================
-- Rollback (si besoin — NE PAS exécuter dans le run normal)
-- =============================================================================
-- DROP TABLE IF EXISTS gold.tarifs_modes CASCADE;
-- =============================================================================