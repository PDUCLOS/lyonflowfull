-- Migration 045 — Conseil sécurité Vélov : pollution + canicule (2026-07-05)
--
-- Pourquoi cette migration existe :
-- bronze.air_quality est ingéré depuis Sprint 8 mais ses valeurs (european_aqi,
-- pm10, pm2_5...) ne sont JAMAIS lues en dehors du monitoring de fraîcheur de
-- source (gold.v_source_health). Aucun garde-fou n'existe pour déconseiller
-- le vélo/la marche en cas de pic de pollution ou de canicule — l'État peut
-- déconseiller le sport en extérieur dans ces cas, LyonFlow ne peut pas
-- recommander Vélov sans avertir l'usager. Décision (brainstorming
-- 2026-07-05) : avertir mais laisser le choix (pas de blocage dur du mode).
--
-- Crée :
--   1. bronze.vigilance_meteo — nouvelle source (API publique Opendatasoft,
--      miroir gratuit sans clé de la vigilance météo-france départementale,
--      dataset "weatherref-france-vigilance-meteo-departement"). Département
--      69 (Rhône) uniquement, phénomène "canicule" uniquement.
--   2. silver.air_quality_clean — dédup de bronze.air_quality (même pattern
--      que silver.meteo_hourly), colonnes limitées à ce que le collecteur
--      Open-Meteo AQ récupère réellement (pas de sulphur_dioxide, jamais
--      demandé dans les params `hourly` du collecteur).
--   3. gold.v_velov_safety_advisory — vue unique consommée par tous les
--      widgets (weather_widget, velov_trip, velov_widget) : évite de
--      dupliquer les seuils AQI/canicule en Python à 3 endroits différents.
--
-- Seuils retenus :
--   european_aqi >= 5 (Very Poor) OU couleur_canicule = 'rouge'  -> severe
--   european_aqi >= 4 (Poor)      OU couleur_canicule = 'orange' -> warning
--   Aucune donnée récente disponible des deux côtés                -> unknown
--   (fail-loud : on ne prétend jamais "ok" sans donnée réelle)
--   Sinon                                                          -> ok
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + CREATE OR REPLACE VIEW.
-- =============================================================================

CREATE TABLE IF NOT EXISTS bronze.vigilance_meteo (
    id                  BIGSERIAL PRIMARY KEY,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    departement         TEXT NOT NULL,               -- '69' (Rhône, fixe)
    couleur_canicule    TEXT NOT NULL,                -- vert | jaune | orange | rouge
    echeance            TEXT NOT NULL,                -- 'J' (aujourd'hui) | 'J1' (demain)
    begin_time          TIMESTAMPTZ,
    end_time            TIMESTAMPTZ,
    bulletin_date       TIMESTAMPTZ,                  -- product_datetime de l'API
    raw_data            JSONB,
    CONSTRAINT vigilance_meteo_uniq UNIQUE (departement, echeance, begin_time, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_vigilance_meteo_dept_fetched
    ON bronze.vigilance_meteo (departement, fetched_at DESC);

COMMENT ON TABLE bronze.vigilance_meteo IS
    'Vigilance météo-france département 69 (Rhône), phénomène canicule uniquement. '
    'Source : API publique Opendatasoft (miroir gratuit sans clé, dataset '
    'weatherref-france-vigilance-meteo-departement). Ingestion */6h.';

-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.air_quality_clean (
    measurement_time    TIMESTAMPTZ NOT NULL PRIMARY KEY,
    european_aqi        INTEGER,                      -- indice européen 1-6
    pm10                REAL,
    pm2_5               REAL,
    nitrogen_dioxide    REAL,
    ozone               REAL,
    carbon_monoxide     REAL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.air_quality_clean IS
    'Dédup de bronze.air_quality par measurement_time (même pattern que '
    'silver.meteo_hourly). european_aqi = seule colonne utilisée pour le '
    'gating sécurité Vélov (gold.v_velov_safety_advisory).';

-- -----------------------------------------------------------------------------

DROP VIEW IF EXISTS gold.v_velov_safety_advisory;

CREATE VIEW gold.v_velov_safety_advisory AS
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
        WHEN a.european_aqi >= 5 OR v.couleur_canicule = 'rouge' THEN 'severe'
        WHEN a.european_aqi >= 4 OR v.couleur_canicule = 'orange' THEN 'warning'
        ELSE 'ok'
    END AS status,
    CASE
        WHEN a.european_aqi IS NULL AND v.couleur_canicule IS NULL
            THEN 'Données qualité de l''air et vigilance indisponibles'
        WHEN a.european_aqi >= 5 AND v.couleur_canicule = 'rouge'
            THEN 'Pollution très mauvaise (indice ' || a.european_aqi || '/6) et vigilance canicule rouge'
        WHEN a.european_aqi >= 5
            THEN 'Pollution très mauvaise (indice européen ' || a.european_aqi || '/6)'
        WHEN v.couleur_canicule = 'rouge'
            THEN 'Vigilance canicule rouge (Rhône)'
        WHEN a.european_aqi >= 4
            THEN 'Pollution dégradée (indice européen ' || a.european_aqi || '/6)'
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
    'Sprint 2026-07-05 — Conseil sécurité unique (AQI + vigilance canicule) '
    'consommé par weather_widget/velov_trip/velov_widget. status: ok|warning|'
    'severe|unknown. "unknown" si aucune des deux sources n''a de donnée '
    'récente (fail-loud, jamais de faux "ok").';
