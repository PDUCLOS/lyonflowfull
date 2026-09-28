-- =============================================================================
-- Migration 052 — TomTom retiré de gold.v_source_health (2026-09-28)
-- =============================================================================
-- Pourquoi cette migration existe :
-- La clé TomTom est rejetée (HTTP 403) depuis le 2026-09-23 et la collecte
-- est mise de côté (DAG collect_tomtom_traffic en pause). Aucune brique ne
-- dépend plus de TomTom : le modèle XGBoost n'a jamais été entraîné dessus
-- (features 100 % Grand Lyon + météo + calendrier) et l'évaluation H+1h
-- utilise la vitesse Grand Lyon observée (migration 051).
-- Conséquence avant ce fix : bronze.tomtom_traffic compté « dead » dans la
-- santé des sources → « 7/8 sources à jour, score 88/100 » sur les pages
-- Usager et Élu alors que tout fonctionne.
--
-- Cette migration redéfinit la vue à l'identique, sans la branche TomTom.
-- Pour réintégrer TomTom : rejouer la branche retirée (cf. migration 021).
-- Idempotent : CREATE OR REPLACE VIEW (même liste de colonnes).
-- =============================================================================

CREATE OR REPLACE VIEW gold.v_source_health AS
 WITH source_status AS (
         SELECT 'bronze.trafic_boucles'::text AS source,
            max(trafic_boucles.fetched_at) AS last_update,
            EXTRACT(epoch FROM now() - max(trafic_boucles.fetched_at)) / 60::numeric AS age_minutes,
            count(*) FILTER (WHERE trafic_boucles.fetched_at > (now() - '01:00:00'::interval)) AS records_1h,
            5 AS expected_interval_min
           FROM bronze.trafic_boucles
        UNION ALL
         SELECT 'bronze.velov'::text,
            max(velov.fetched_at) AS max,
            EXTRACT(epoch FROM now() - max(velov.fetched_at)) / 60::numeric,
            count(*) FILTER (WHERE velov.fetched_at > (now() - '01:00:00'::interval)) AS count,
            5
           FROM bronze.velov
        UNION ALL
         SELECT 'bronze.tcl_vehicles'::text,
            max(tcl_vehicles.fetched_at) AS max,
            EXTRACT(epoch FROM now() - max(tcl_vehicles.fetched_at)) / 60::numeric,
            count(*) FILTER (WHERE tcl_vehicles.fetched_at > (now() - '01:00:00'::interval)) AS count,
            5
           FROM bronze.tcl_vehicles
        UNION ALL
         SELECT 'bronze.meteo'::text,
            max(meteo.fetched_at) AS max,
            EXTRACT(epoch FROM now() - max(meteo.fetched_at)) / 60::numeric,
            count(*) FILTER (WHERE meteo.fetched_at > (now() - '01:00:00'::interval)) AS count,
            60
           FROM bronze.meteo
        UNION ALL
         SELECT 'bronze.air_quality'::text,
            max(air_quality.fetched_at) AS max,
            EXTRACT(epoch FROM now() - max(air_quality.fetched_at)) / 60::numeric,
            count(*) FILTER (WHERE air_quality.fetched_at > (now() - '1 day'::interval)) AS count,
            60
           FROM bronze.air_quality
        UNION ALL
         SELECT 'bronze.chantiers'::text,
            max(chantiers.fetched_at) AS max,
            EXTRACT(epoch FROM now() - max(chantiers.fetched_at)) / 60::numeric,
            count(*) FILTER (WHERE chantiers.fetched_at > (now() - '1 day'::interval)) AS count,
            1440
           FROM bronze.chantiers
        UNION ALL
         SELECT 'gold.trafic_predictions'::text,
            max(trafic_predictions.calculated_at) AS max,
            EXTRACT(epoch FROM now() - max(trafic_predictions.calculated_at)) / 60::numeric,
            count(*) FILTER (WHERE trafic_predictions.calculated_at > (now() - '02:00:00'::interval)) AS count,
            30
           FROM gold.trafic_predictions
        )
 SELECT source,
    last_update,
    age_minutes,
    records_1h,
    expected_interval_min,
    GREATEST(0, LEAST(100,
        CASE
            WHEN age_minutes IS NULL THEN 0
            WHEN age_minutes <= (expected_interval_min::numeric * 1.5) THEN 100
            WHEN age_minutes <= (expected_interval_min * 3)::numeric THEN 70
            WHEN age_minutes <= (expected_interval_min * 6)::numeric THEN 40
            WHEN age_minutes <= (expected_interval_min * 12)::numeric THEN 15
            ELSE 0
        END)) AS health_score,
        CASE
            WHEN age_minutes IS NULL THEN 'dead'::text
            WHEN age_minutes <= (expected_interval_min::numeric * 1.5) THEN 'healthy'::text
            WHEN age_minutes <= (expected_interval_min * 3)::numeric THEN 'delayed'::text
            WHEN age_minutes <= (expected_interval_min * 6)::numeric THEN 'stale'::text
            ELSE 'dead'::text
        END AS status
   FROM source_status
  ORDER BY (GREATEST(0, LEAST(100,
        CASE
            WHEN age_minutes IS NULL THEN 0
            WHEN age_minutes <= (expected_interval_min::numeric * 1.5) THEN 100
            WHEN age_minutes <= (expected_interval_min * 3)::numeric THEN 70
            WHEN age_minutes <= (expected_interval_min * 6)::numeric THEN 40
            WHEN age_minutes <= (expected_interval_min * 12)::numeric THEN 15
            ELSE 0
        END)));
