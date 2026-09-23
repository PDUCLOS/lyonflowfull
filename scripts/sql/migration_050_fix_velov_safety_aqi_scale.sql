-- =============================================================================
-- Migration 050 — Échelle EAQI corrigée dans gold.v_velov_safety_advisory (Sprint 26, 2026-09-23)
-- =============================================================================
-- Pourquoi cette migration existe :
-- La migration 045 supposait que ``silver.air_quality_clean.european_aqi``
-- était un niveau 1-6. Faux : Open-Meteo (src/ingestion/air_quality.py,
-- champ ``european_aqi``) renvoie l'European Air Quality Index sur son
-- échelle numérique 0-100+ :
--     0-20  Good | 20-40 Fair | 40-60 Moderate | 60-80 Poor |
--     80-100 Very poor | >100 Extremely poor
-- Avec les seuils ``>= 5`` (severe) et ``>= 4`` (warning), la vue classait
-- TOUTES les heures en « severe » : mesuré sur le VPS le 2026-09-23,
-- 761 h / 761 h sur 30 jours (AQI réel min 9, moyenne 29, max 64). Le bandeau
-- Usager Vélov (velov_widget / velov_trip / weather_widget) affichait donc
-- « Pollution très mauvaise (indice européen 31/6) » en permanence depuis
-- juillet.
--
-- Cette migration :
--   1. Redéfinit la vue avec les seuils EAQI : warning >= 60 (Poor),
--      severe >= 80 (Very poor). Le libellé indique l'échelle (EAQI 0-100).
--   2. Corrige le commentaire de colonne silver.air_quality_clean.european_aqi.
-- Idempotent : CREATE OR REPLACE VIEW (même liste de colonnes que 045).
-- =============================================================================

CREATE OR REPLACE VIEW gold.v_velov_safety_advisory AS
WITH anchor AS (
    SELECT 1 AS x
),
latest_aqi AS (
    SELECT european_aqi, measurement_time
    FROM silver.air_quality_clean
    WHERE measurement_time >= NOW() - INTERVAL '3 hours'
      AND measurement_time <= NOW() + INTERVAL '1 hour'
    ORDER BY measurement_time DESC
    LIMIT 1
),
latest_vigilance AS (
    SELECT couleur_canicule, bulletin_date
    FROM bronze.vigilance_meteo
    WHERE departement = '69'
      AND echeance = 'J'
      AND fetched_at >= NOW() - INTERVAL '12 hours'
    ORDER BY
        CASE couleur_canicule
            WHEN 'rouge' THEN 4 WHEN 'orange' THEN 3 WHEN 'jaune' THEN 2 ELSE 1
        END DESC,
        fetched_at DESC
    LIMIT 1
)
SELECT
    a.european_aqi,
    v.couleur_canicule,
    CASE
        WHEN a.european_aqi IS NULL AND v.couleur_canicule IS NULL THEN 'unknown'
        WHEN a.european_aqi >= 80 OR v.couleur_canicule = 'rouge' THEN 'severe'
        WHEN a.european_aqi >= 60 OR v.couleur_canicule = 'orange' THEN 'warning'
        ELSE 'ok'
    END AS status,
    CASE
        WHEN a.european_aqi IS NULL AND v.couleur_canicule IS NULL
            THEN 'Données qualité de l''air et vigilance indisponibles'
        WHEN a.european_aqi >= 80 AND v.couleur_canicule = 'rouge'
            THEN 'Pollution très mauvaise (indice européen ' || a.european_aqi || ', EAQI 0-100) et vigilance canicule rouge'
        WHEN a.european_aqi >= 80
            THEN 'Pollution très mauvaise (indice européen ' || a.european_aqi || ', EAQI 0-100)'
        WHEN v.couleur_canicule = 'rouge'
            THEN 'Vigilance canicule rouge (Rhône)'
        WHEN a.european_aqi >= 60
            THEN 'Pollution dégradée (indice européen ' || a.european_aqi || ', EAQI 0-100)'
        WHEN v.couleur_canicule = 'orange'
            THEN 'Vigilance canicule orange (Rhône)'
        ELSE NULL
    END AS reason,
    a.measurement_time AS aqi_measured_at,
    v.bulletin_date AS vigilance_bulletin_at
FROM anchor
LEFT JOIN latest_aqi a ON TRUE
LEFT JOIN latest_vigilance v ON TRUE;

COMMENT ON VIEW gold.v_velov_safety_advisory IS
    'Sprint 2026-07-05, seuils corrigés Sprint 26 (2026-09-23) — Conseil sécurité '
    'unique (EAQI 0-100 Open-Meteo + vigilance canicule) consommé par '
    'weather_widget/velov_trip/velov_widget. status: ok|warning (EAQI >= 60 ou '
    'orange)|severe (EAQI >= 80 ou rouge)|unknown. "unknown" si aucune des deux '
    'sources n''a de donnée récente (fail-loud, jamais de faux "ok").';

COMMENT ON COLUMN silver.air_quality_clean.european_aqi IS
    'European Air Quality Index Open-Meteo, échelle 0-100+ (0-20 good, 20-40 fair, '
    '40-60 moderate, 60-80 poor, 80-100 very poor, >100 extremely poor). '
    'PAS un niveau 1-6 (erreur de la migration 045, corrigée en 050).';
