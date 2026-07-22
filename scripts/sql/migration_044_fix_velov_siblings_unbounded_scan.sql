-- Migration 044 — Fix siblings du bug 042/043 sur silver.velov_clean (2026-07-03)
--
-- Pourquoi cette migration existe :
-- Audit complet de la persona Usager (post migration 042/043) a trouvé 2
-- fonctions/vues soeurs avec exactement le même bug : dédup silver.velov_clean
-- (3.3M+ lignes) via DISTINCT ON ... ORDER BY fetched_at DESC (colonne sans
-- index adapté, aucune borne temporelle) → scan complet à chaque appel.
--
-- 1) referentiel.nearest_velov_stations() — appelée directement depuis
--    Usager_1_Mon_Trajet.py (recherche stations proches destination) et
--    depuis src/routing/pathfinder_multimodal.py (_nearest_velov_station /
--    _nearest_velov_stations_pair).
-- 2) referentiel.v_lieux_velov_proches (+ v_lieux_velov_plus_proche qui en
--    dépend) — backend de la carte lieux/vélov (Mon Trajet, Pro TCL).
--
-- Fix identique à 043 : ORDER BY measurement_time DESC (matche
-- idx_velov_clean_measurement_time / idx_silver_velov_station_time) +
-- borne 15 min (cadence ingestion */5min, x3 marge). Sémantique inchangée.

CREATE OR REPLACE FUNCTION referentiel.nearest_velov_stations(
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    k INTEGER DEFAULT 3,
    min_bikes INTEGER DEFAULT 0,
    min_docks INTEGER DEFAULT 0
) RETURNS TABLE (
    station_id          TEXT,
    station_name        TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    distance_m          DOUBLE PRECISION,
    is_active           BOOLEAN
)
LANGUAGE SQL
STABLE
AS $$
    WITH latest AS (
        -- Dernier snapshot par station (migration 044 : borné 15 min,
        -- dédup sur measurement_time — même fix que 043).
        SELECT DISTINCT ON (v.station_id)
            v.station_id, v.station_name, v.lat, v.lon,
            v.num_bikes_available, v.num_docks_available, v.is_active
        FROM silver.velov_clean v
        WHERE v.is_active = TRUE
          AND v.measurement_time >= NOW() - INTERVAL '15 minutes'
        ORDER BY v.station_id, v.measurement_time DESC
    )
    SELECT
        l.station_id, l.station_name, l.lat, l.lon,
        l.num_bikes_available, l.num_docks_available,
        referentiel.haversine_m($1, $2, l.lat, l.lon) AS distance_m,
        l.is_active
    FROM latest l
    WHERE l.num_bikes_available >= $4
      AND l.num_docks_available >= $5
    ORDER BY distance_m ASC
    LIMIT $3;
$$;

COMMENT ON FUNCTION referentiel.nearest_velov_stations IS
    'K plus proches stations Vélov avec dispo temps réel (silver.velov_clean, '
    'dernier snapshot). Filtres min_bikes/min_docks. Triées par distance haversine. '
    'Migration 044 (2026-07-03) : latest_velov borné 15 min sur measurement_time '
    '(fix scan complet 3.3M lignes, même bug que 042/043).';


CREATE OR REPLACE VIEW referentiel.v_lieux_velov_proches AS
WITH latest_velov AS (
    -- Dernier snapshot Vélov par station (migration 044 : borné 15 min).
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
      AND v.measurement_time >= NOW() - INTERVAL '15 minutes'
    ORDER BY v.station_id, v.measurement_time DESC
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
    'Utilisé par le dashboard carte (Mon Trajet, Pro TCL) et le widget Mon Trajet. '
    'Migration 044 (2026-07-03) : latest_velov borné 15 min (fix scan complet, '
    'même bug que 042/043).';

-- v_lieux_velov_plus_proche hérite automatiquement du fix (SELECT * FROM
-- v_lieux_velov_proches WHERE rank = 1) — pas de CREATE OR REPLACE nécessaire.
