-- Migration 042 — Fix scan complet sur referentiel.v_lieux_velov_smart /
-- referentiel.v_velov_neighbors (2026-07-03)
--
-- Pourquoi cette migration existe :
-- plan_velov_trip() (Mon Trajet, persona Usager) est lent alors que
-- l'algo Vélov est trivial (3 segments, haversine). Root cause : les 2
-- vues source (create_velov_maillage.sql) dédupliquent silver.velov_clean
-- via `DISTINCT ON (station_id) ... ORDER BY station_id, fetched_at DESC`.
-- Or l'unique index dispo est idx_silver_velov_station_time sur
-- (station_id, measurement_time DESC) — colonne `measurement_time`, pas
-- `fetched_at`. Mismatch total : Postgres ne peut pas utiliser l'index
-- pour le DISTINCT ON, il scanne + trie TOUTE la table (PK 438 Mo, table
-- réelle bien plus grosse, alimentée */5min depuis Sprint 1) à chaque
-- requête. Ce scan est déclenché 2x par plan_velov_trip (query lieu
-- origine puis destination, non batchées).
--
-- Fix : ORDER BY measurement_time DESC (au lieu de fetched_at) → même
-- sémantique (dernière mesure connue de la station), mais utilise l'index
-- existant en index-skip-scan. Pas de nouvel index nécessaire.

CREATE OR REPLACE VIEW referentiel.v_lieux_velov_smart AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
    ORDER BY v.station_id, v.measurement_time DESC
),
scored AS (
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
        CASE
            WHEN v.num_bikes_available = 0 THEN -10000.0
            WHEN v.num_docks_available = 0 THEN -5000.0
            ELSE -1.0 * referentiel.haversine_m(l.lat, l.lon, v.lat, v.lon)
        END AS score,
        CASE
            WHEN v.num_bikes_available = 0 THEN 'VIDE'
            WHEN v.num_docks_available = 0 THEN 'PLEINE'
            WHEN v.num_bikes_available < 3 OR v.num_docks_available < 3 THEN 'FAIBLE'
            ELSE 'OK'
        END AS status,
        ROW_NUMBER() OVER (
            PARTITION BY l.lieu_id
            ORDER BY
                CASE
                    WHEN v.num_bikes_available = 0 THEN -10000.0
                    WHEN v.num_docks_available = 0 THEN -5000.0
                    ELSE -1.0 * referentiel.haversine_m(l.lat, l.lon, v.lat, v.lon)
                END DESC
        ) AS rank
    FROM referentiel.lieux_lyon l
    CROSS JOIN LATERAL (
        SELECT * FROM latest_velov
        WHERE referentiel.haversine_m(l.lat, l.lon, latest_velov.lat, latest_velov.lon) < 1500
        ORDER BY referentiel.haversine_m(l.lat, l.lon, latest_velov.lat, latest_velov.lon) ASC
        LIMIT 10
    ) v
    WHERE l.is_active = TRUE
)
SELECT
    lieu_id, lieu_name, lieu_lon, lieu_lat, lieu_type,
    station_id, velov_name, velov_lon, velov_lat,
    num_bikes_available, num_docks_available,
    distance_m, score, status, rank
FROM scored
WHERE rank <= 3
ORDER BY lieu_id, rank;

COMMENT ON VIEW referentiel.v_lieux_velov_smart IS
    'Sprint VPS-6 — Top 3 bornes Vélov par lieu avec score composite (distance + '
    'vélos dispo + docks dispo). Status = VIDE / PLEINE / FAIBLE / OK. '
    'Utilisé par Mon Trajet pour proposer une alternative si la borne #1 est pleine. '
    'Migration 042 (2026-07-03) : dédup ORDER BY measurement_time (au lieu de '
    'fetched_at) pour matcher idx_silver_velov_station_time et éviter le scan complet.';


CREATE OR REPLACE VIEW referentiel.v_velov_neighbors AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
    ORDER BY v.station_id, v.measurement_time DESC
)
SELECT
    a.station_id AS station_id_a,
    a.station_name AS name_a,
    a.num_bikes_available AS bikes_a,
    a.num_docks_available AS docks_a,
    a.lon AS lon_a,
    a.lat AS lat_a,
    b.station_id AS station_id_b,
    b.station_name AS name_b,
    b.num_bikes_available AS bikes_b,
    b.num_docks_available AS docks_b,
    b.lon AS lon_b,
    b.lat AS lat_b,
    referentiel.haversine_m(a.lat, a.lon, b.lat, b.lon) AS distance_m
FROM latest_velov a
JOIN latest_velov b
  ON a.station_id < b.station_id
 AND referentiel.haversine_m(a.lat, a.lon, b.lat, b.lon) < 200
ORDER BY a.station_id, distance_m;

COMMENT ON VIEW referentiel.v_velov_neighbors IS
    'Sprint VPS-6 — Maillage des bornes Vélov voisines (< 200m). Lyon a ~458 '
    'stations, ~10-20k paires voisines. Utilisé pour le rendu carte "grappe" '
    'et pour suggérer des alternatives à pied en cas de borne pleine/vide. '
    'Migration 042 (2026-07-03) : dédup ORDER BY measurement_time (au lieu de '
    'fetched_at) pour matcher idx_silver_velov_station_time et éviter le scan complet.';
