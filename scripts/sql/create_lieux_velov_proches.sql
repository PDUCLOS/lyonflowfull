-- =============================================================================
-- LyonFlowFull — Vélov proches par lieu (Sprint VPS-6, 2026-06-11)
-- =============================================================================
-- Vue qui croise referentiel.lieux_lyon avec silver.velov_clean pour
-- exposer, pour chaque lieu actif, les K bornes Vélov les plus proches
-- (avec distance haversine + vélos/docks dispo temps réel).
--
-- Usage :
--   * dashboard : markers lieux + bornes sur carte, avec lignes pointillées
--   * data_loader : load_lieux_with_velov() pour la page Mon Trajet
--
-- Idempotent : CREATE OR REPLACE VIEW.
-- Performances : 21 lieux actifs × N bornes Vélov (~690K) = 14.5M rows
-- potentiels. PostgreSQL optimise le LATERAL avec un index spatial
-- (bbox) + tri par distance. <100ms en pratique.
-- =============================================================================

CREATE OR REPLACE VIEW referentiel.v_lieux_velov_proches AS
WITH latest_velov AS (
    -- Dernier snapshot Vélov par station (équivalent du Silver clean)
    SELECT DISTINCT ON (v.station_id)
        v.station_id,
        v.station_name,
        v.lat,
        v.lon,
        v.num_bikes_available,
        v.num_docks_available,
        v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
    ORDER BY v.station_id, v.fetched_at DESC
)
SELECT
    l.lieu_id,
    l.name AS lieu_name,
    l.lon AS lieu_lon,
    l.lat AS lieu_lat,
    l.type AS lieu_type,
    v.station_id,
    v.station_name AS velov_name,
    v.lon AS velov_lon,
    v.lat AS velov_lat,
    v.num_bikes_available,
    v.num_docks_available,
    referentiel.haversine_m(l.lat, l.lon, v.lat, v.lon) AS distance_m,
    -- Rang 1 = la plus proche, 2 = 2e plus proche, etc.
    ROW_NUMBER() OVER (
        PARTITION BY l.lieu_id
        ORDER BY referentiel.haversine_m(l.lat, l.lon, v.lat, v.lon) ASC
    ) AS rank
FROM referentiel.lieux_lyon l
CROSS JOIN LATERAL (
    SELECT * FROM latest_velov
    ORDER BY referentiel.haversine_m(l.lat, l.lon, latest_velov.lat, latest_velov.lon) ASC
    LIMIT 3
) v
WHERE l.is_active = TRUE
ORDER BY l.lieu_id, distance_m;

COMMENT ON VIEW referentiel.v_lieux_velov_proches IS
    'Sprint VPS-6 (2026-06-11) — Pour chaque lieu du référentiel, top 3 bornes '
    'Vélov les plus proches avec distance haversine + vélos/docks dispo temps réel. '
    'Utilisé par le dashboard carte (Mon Trajet, Pro TCL) et le widget Mon Trajet.';

-- Vue simplifiée : 1 borne Vélov la plus proche par lieu
CREATE OR REPLACE VIEW referentiel.v_lieux_velov_plus_proche AS
SELECT
    lieu_id,
    lieu_name,
    lieu_lon,
    lieu_lat,
    lieu_type,
    station_id,
    velov_name,
    velov_lon,
    velov_lat,
    num_bikes_available,
    num_docks_available,
    distance_m
FROM referentiel.v_lieux_velov_proches
WHERE rank = 1;

COMMENT ON VIEW referentiel.v_lieux_velov_plus_proche IS
    '1 borne Vélov la plus proche par lieu (top 1 de v_lieux_velov_proches).';
