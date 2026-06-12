-- =============================================================================
-- LyonFlowFull — Seed user_favorites (migration des 4 MOCK_FAVORITES)
-- =============================================================================
-- Sprint 10 (2026-06-12) — Migration des favoris mock vers la DB.
-- UUIDs générés en Python (uuid.uuid4()) pour correspondre aux ids mock.
--
-- Ids conservés pour compatibilité : fav_1..fav_4 (UUID format texte)
-- =============================================================================

INSERT INTO public.user_favorites
    (user_id, id, name, origin, destination, usual_mode, usual_duration_min, alert_subscribed, created_at, updated_at)
VALUES
    ('default_user', 'fav_1',
     '🏠 Maison → 💼 Boulot', 'Villeurbanne', 'Part-Dieu', 'M A', 22, TRUE,
     '2026-06-01T08:00:00+02:00', '2026-06-01T08:00:00+02:00'),

    ('default_user', 'fav_2',
     '💼 Boulot → 🏠 Maison', 'Part-Dieu', 'Villeurbanne', 'M A', 22, TRUE,
     '2026-06-01T08:00:00+02:00', '2026-06-01T08:00:00+02:00'),

    ('default_user', 'fav_3',
     '🏠 Maison → 🛒 Carrefour', 'Villeurbanne', 'Bron', 'C17', 35, FALSE,
     '2026-06-01T08:00:00+02:00', '2026-06-01T08:00:00+02:00'),

    ('default_user', 'fav_4',
     '💼 Boulot → 🏋️ Salle de sport', 'Part-Dieu', 'Confluence', 'T1', 18, TRUE,
     '2026-06-01T08:00:00+02:00', '2026-06-01T08:00:00+02:00')
ON CONFLICT (user_id, id) DO UPDATE
    SET name               = EXCLUDED.name,
        origin             = EXCLUDED.origin,
        destination        = EXCLUDED.destination,
        usual_mode         = EXCLUDED.usual_mode,
        usual_duration_min = EXCLUDED.usual_duration_min,
        alert_subscribed   = EXCLUDED.alert_subscribed,
        updated_at         = NOW();

-- Vérification post-seed
DO $$
DECLARE
    n_fav INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_fav FROM public.user_favorites WHERE user_id = 'default_user';
    RAISE NOTICE 'user_favorites : % favoris seedés pour default_user', n_fav;
END $$;
