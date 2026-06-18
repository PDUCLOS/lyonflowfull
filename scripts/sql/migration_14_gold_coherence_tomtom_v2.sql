-- =============================================================================
-- LyonFlowFull — Migration 14 (Sprint 13+, 2026-06-18)
-- =============================================================================
-- Vue Gold : gold.v_coherence_tomtom_vs_grandlyon v2
--
-- Réécriture complète de la vue introduite dans
-- scripts/migrate_realign_v0.3.1.sql — l'ancienne version n'agrégeait
-- que TomTom sans JOIN avec les capteurs Grand Lyon (cf. note
-- "le join precis avec trafic_boucles necessite un mapping spatial,
-- A faire dans une migration ulterieure"). C'est chose faite ici.
--
-- Principe :
-- 1. bronze.tomtom_traffic stocke des snapshots TomTom par tuile 0.02°
--    (12 tuiles Lyon, centroid tile ≈ 2 km de côté).
-- 2. gold.channels_ref stocke les capteurs Grand Lyon (channel_id,
--    lat, lon, geom Point 4326).
-- 3. Pour chaque snapshot TomTom récent (< 24h), on joint avec les
--    capteurs Grand Lyon dans un rayon de 200 m autour du centroïde
--    de tuile. Pour chaque paire (tile_key, channel_id) on calcule
--    le delta de vitesse et un flag d'alerte.
-- 4. Vue secondaire v_tomtom_gl_drift : capteurs dont le delta
--    dépasse 20 km/h sur 3 cycles consécutifs (15 min × 3 = 45 min)
--    → candidats "capteur HS" à investiguer côté Grand Lyon.
--
-- Idempotent : CREATE OR REPLACE VIEW.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue 1 — gold.v_coherence_tomtom_vs_grandlyon (instantané)
-- -----------------------------------------------------------------------------
-- Compare, sur la dernière heure, chaque tuile TomTom avec les
-- capteurs Grand Lyon à moins de 200 m. Permet de voir en un coup
-- d'œil si les 2 sources s'accordent (delta proche de 0).
--
-- Sortie :
--   tile_key, channel_id, site_name, distance_m,
--   tomtom_speed_kmh, gl_speed_kmh, delta_kmh, ratio_diff,
--   status ('ok'|'drift'|'no_data'), fetched_at
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW gold.v_coherence_tomtom_vs_grandlyon AS
WITH tomtom_recent AS (
    -- Dernier snapshot TomTom par tuile, dernière heure
    SELECT DISTINCT ON (tile_key)
        tile_key,
        lat  AS tt_lat,
        lon  AS tt_lon,
        current_speed_kmh,
        free_flow_speed_kmh,
        ratio AS tt_ratio,
        confidence,
        fetched_at
    FROM bronze.tomtom_traffic
    WHERE fetched_at >= NOW() - INTERVAL '1 hour'
    ORDER BY tile_key, fetched_at DESC
),
gl_recent AS (
    -- Capteurs Grand Lyon qui ont un speed dans la dernière heure
    SELECT DISTINCT ON (cr.channel_id)
        cr.channel_id,
        cr.site_name,
        cr.lat,
        cr.lon,
        cr.geom,
        -- Vitesse GL : on prend gold.traffic_features_live.speed_kmh
        -- (dernière valeur < 1h). NULL si pas de mesure récente.
        tfl.speed_kmh AS gl_speed_kmh
    FROM gold.channels_ref cr
    LEFT JOIN gold.traffic_features_live tfl
      ON tfl.channel_id = cr.channel_id
     AND tfl.computed_at >= NOW() - INTERVAL '1 hour'
    WHERE cr.lat IS NOT NULL AND cr.lon IS NOT NULL
),
pairs AS (
    -- Cross join spatial : pour chaque tuile TomTom, on prend les
    -- capteurs GL dans un rayon de 200 m (distance haversine en m).
    SELECT
        t.tile_key,
        g.channel_id,
        g.site_name,
        -- Distance haversine entre centroïde tuile TomTom et capteur GL
        -- (Point 4326, formula spheroid [[X,Y],...] pour mètres).
        ST_DistanceSphere(
            ST_SetSRID(ST_MakePoint(t.tt_lon, t.tt_lat), 4326),
            g.geom
        ) AS distance_m,
        t.current_speed_kmh AS tomtom_speed_kmh,
        t.free_flow_speed_kmh,
        t.tt_ratio,
        t.confidence,
        g.gl_speed_kmh,
        t.fetched_at
    FROM tomtom_recent t
    JOIN gl_recent g
      ON ST_DWithin(
            ST_SetSRID(ST_MakePoint(t.tt_lon, t.tt_lat), 4326)::geography,
            g.geom::geography,
            200  -- 200 mètres
         )
)
SELECT
    tile_key,
    channel_id,
    site_name,
    ROUND(distance_m::numeric, 1)            AS distance_m,
    ROUND(tomtom_speed_kmh::numeric, 1)     AS tomtom_speed_kmh,
    ROUND(gl_speed_kmh::numeric, 1)         AS gl_speed_kmh,
    ROUND((tomtom_speed_kmh - gl_speed_kmh)::numeric, 1) AS delta_kmh,
    CASE
        WHEN gl_speed_kmh IS NULL THEN NULL
        WHEN tomtom_speed_kmh = 0 THEN NULL
        ELSE ROUND(((tomtom_speed_kmh - gl_speed_kmh) / tomtom_speed_kmh)::numeric, 3)
    END AS ratio_diff,
    t.confidence AS tomtom_confidence,
    fetched_at,
    CASE
        WHEN gl_speed_kmh IS NULL          THEN 'no_data'
        WHEN ABS(tomtom_speed_kmh - gl_speed_kmh) <= 10  THEN 'ok'
        WHEN ABS(tomtom_speed_kmh - gl_speed_kmh) <= 20  THEN 'minor_drift'
        ELSE 'drift'
    END AS status
FROM pairs t;

COMMENT ON VIEW gold.v_coherence_tomtom_vs_grandlyon IS
    'Sprint 13+ (2026-06-18) — Cohérence TomTom (tuiles 0.02°) vs capteurs Grand Lyon '
    '(gold.channels_ref) à moins de 200 m. Pour chaque paire (tile_key, channel_id), '
    'calcule delta_kmh, ratio_diff et status (ok|minor_drift|drift|no_data). '
    'Source widget Pro_TCL "Cohérence sources vitesse".';


-- -----------------------------------------------------------------------------
-- Vue 2 — gold.v_tomtom_gl_drift (capteurs suspects, agrégé)
-- -----------------------------------------------------------------------------
-- Pour chaque capteur GL ayant au moins 1 mesure dans les dernières
-- 24h, calcule le % de paires (avec tuile TomTom proche) où le
-- delta dépasse 20 km/h. Si >= 60% des paires récentes sont en drift,
-- le capteur est suspect → à investiguer (HS, calibration, etc.).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW gold.v_tomtom_gl_drift AS
WITH coherence_24h AS (
    -- Toutes les paires (tile_key, channel_id) sur 24h, dernier snapshot/h
    SELECT
        channel_id,
        site_name,
        COUNT(*)                                          AS n_pairs,
        COUNT(*) FILTER (WHERE status = 'drift')          AS n_drift,
        COUNT(*) FILTER (WHERE status = 'minor_drift')    AS n_minor_drift,
        COUNT(*) FILTER (WHERE status = 'ok')             AS n_ok,
        AVG(ABS(delta_kmh))                               AS avg_abs_delta_kmh,
        MAX(ABS(delta_kmh))                               AS max_abs_delta_kmh
    FROM gold.v_coherence_tomtom_vs_grandlyon
    WHERE fetched_at >= NOW() - INTERVAL '24 hours'
    GROUP BY channel_id, site_name
)
SELECT
    channel_id,
    site_name,
    n_pairs,
    n_ok,
    n_minor_drift,
    n_drift,
    ROUND((n_drift::numeric / NULLIF(n_pairs, 0)), 3) AS drift_ratio,
    ROUND(avg_abs_delta_kmh::numeric, 1)              AS avg_abs_delta_kmh,
    ROUND(max_abs_delta_kmh::numeric, 1)              AS max_abs_delta_kmh,
    CASE
        WHEN n_pairs = 0                          THEN 'no_data'
        WHEN n_drift::float / n_pairs >= 0.60     THEN 'suspect'
        WHEN n_drift::float / n_pairs >= 0.30     THEN 'watch'
        ELSE 'healthy'
    END AS sensor_health
FROM coherence_24h
WHERE n_pairs > 0
ORDER BY n_drift DESC, n_pairs DESC;

COMMENT ON VIEW gold.v_tomtom_gl_drift IS
    'Sprint 13+ (2026-06-18) — Capteurs Grand Lyon suspectés HS : '
    '>= 60% des paires avec tuile TomTom proche en drift (delta > 20 km/h) '
    'sur les dernières 24h. Vue dérivée de gold.v_coherence_tomtom_vs_grandlyon.';


-- =============================================================================
-- Vérification post-migration
-- =============================================================================
-- SELECT COUNT(*) FROM gold.v_coherence_tomtom_vs_grandlyon;
--   → doit être > 0 une fois TomTom et capteurs GL alimentés.
-- SELECT sensor_health, COUNT(*) FROM gold.v_tomtom_gl_drift GROUP BY 1;
--   → distribution healthy / watch / suspect / no_data.
