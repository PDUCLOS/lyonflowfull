-- =============================================================================
-- Migration 021 — Sprint 16 Axe B : Data Quality — Monitoring multi-source
-- =============================================================================
-- Date        : 2026-06-20
-- Version     : v0.8.0
-- Branche     : vps
-- Prérequis   : Sprint 8+ (toutes sources Bronze actives)
--               Sprint 13+ (bronze.tomtom_traffic)
--               Sprint 15+ (gold.trafic_predictions)
--
-- Crée :
--   1. gold.v_source_health       — Vue : score santé par source (8 sources Bronze
--                                   + 1 table Gold) avec fraîcheur, records/1h,
--                                   score 0-100, statut lisible.
--   2. gold.v_data_completeness   — Vue : complétude colonnes critiques par
--                                   table Silver (24h glissantes).
--
-- Remplace les 6 checks mono-table de health_checks.py par 2 vues
-- agrégées + check_all_sources() dans le code.
--
-- Pas de refresh : ce sont des VUES (calculées à la volée, pas de MV).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Vue 1 : Santé par source (fraîcheur + score 0-100 + statut)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_source_health AS
WITH source_status AS (
    -- Bronze : fraîcheur par table
    SELECT 'bronze.trafic_boucles' AS source,
           MAX(fetched_at) AS last_update,
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60 AS age_minutes,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour') AS records_1h,
           5 AS expected_interval_min  -- toutes les 5 min
    FROM bronze.trafic_boucles

    UNION ALL
    SELECT 'bronze.velov', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           5
    FROM bronze.velov

    UNION ALL
    SELECT 'bronze.tcl_vehicles', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           5
    FROM bronze.tcl_vehicles

    UNION ALL
    SELECT 'bronze.meteo', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           60
    FROM bronze.meteo

    UNION ALL
    SELECT 'bronze.air_quality', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 day'),
           60
    FROM bronze.air_quality

    UNION ALL
    SELECT 'bronze.chantiers', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 day'),
           1440  -- 1x/jour
    FROM bronze.chantiers

    UNION ALL
    SELECT 'bronze.tomtom_traffic', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           15
    FROM bronze.tomtom_traffic

    UNION ALL
    SELECT 'gold.trafic_predictions', MAX(calculated_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(calculated_at)))/60,
           COUNT(*) FILTER (WHERE calculated_at > NOW() - INTERVAL '2 hours'),
           30
    FROM gold.trafic_predictions
)
SELECT
    source,
    last_update,
    age_minutes,
    records_1h,
    expected_interval_min,
    -- Score 0-100 : 100 = parfait, 0 = mort
    GREATEST(0, LEAST(100,
        CASE
            WHEN age_minutes IS NULL THEN 0
            WHEN age_minutes <= expected_interval_min * 1.5 THEN 100
            WHEN age_minutes <= expected_interval_min * 3   THEN 70
            WHEN age_minutes <= expected_interval_min * 6   THEN 40
            WHEN age_minutes <= expected_interval_min * 12  THEN 15
            ELSE 0
        END
    ))::int AS health_score,
    -- Statut lisible
    CASE
        WHEN age_minutes IS NULL                           THEN 'dead'
        WHEN age_minutes <= expected_interval_min * 1.5    THEN 'healthy'
        WHEN age_minutes <= expected_interval_min * 3      THEN 'delayed'
        WHEN age_minutes <= expected_interval_min * 6      THEN 'stale'
        ELSE 'dead'
    END AS status
FROM source_status
ORDER BY health_score ASC;  -- les plus malades en premier

COMMENT ON VIEW gold.v_source_health IS
    'Sprint 16 Axe B — Score santé par source (8 sources Bronze + Gold predictions).
     age_minutes = minutes depuis la dernière MAJ.
     health_score 0-100 = qualité (100 = parfait, 0 = mort).
     status ∈ {healthy, delayed, stale, dead}.
     Sert aux widgets source_health_monitor (Pro_6) et data_quality_badge (Elu_1),
     et à check_all_sources() dans health_checks.py.';

-- -----------------------------------------------------------------------------
-- Vue 2 : Complétude colonnes critiques par table Silver (24h)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_data_completeness AS
SELECT
    'silver.trafic_boucles_clean' AS source,
    COUNT(*) AS total_rows,
    ROUND(100.0 * COUNT(*) FILTER (WHERE vitesse_kmh IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS speed_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE geom_wgs84 IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS geo_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE channel_id IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS id_pct
FROM silver.trafic_boucles_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours'

UNION ALL
SELECT
    'silver.tcl_vehicles_clean',
    COUNT(*),
    NULL,  -- pas de vitesse
    ROUND(100.0 * COUNT(*) FILTER (WHERE lat IS NOT NULL) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(*) FILTER (WHERE line_ref IS NOT NULL) / NULLIF(COUNT(*), 0), 1)
FROM silver.tcl_vehicles_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours'

UNION ALL
SELECT
    'silver.velov_clean',
    COUNT(*),
    NULL,
    ROUND(100.0 * COUNT(*) FILTER (WHERE lat IS NOT NULL) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(*) FILTER (WHERE station_id IS NOT NULL) / NULLIF(COUNT(*), 0), 1)
FROM silver.velov_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours';

COMMENT ON VIEW gold.v_data_completeness IS
    'Sprint 16 Axe B — Complétude colonnes critiques par table Silver (24h).
     speed_pct, geo_pct, id_pct = % non-NULL sur les colonnes critiques.
     Sert au widget source_health_monitor pour la section "Complétude Silver".';

-- Permissions
GRANT SELECT ON gold.v_source_health TO PUBLIC;
GRANT SELECT ON gold.v_data_completeness TO PUBLIC;
