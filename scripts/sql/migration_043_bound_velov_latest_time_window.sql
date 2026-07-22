-- Migration 043 — Borner latest_velov dans le temps (2026-07-03)
--
-- Pourquoi cette migration existe :
-- Migration 042 a corrigé le mismatch d'index (fetched_at → measurement_time)
-- mais EXPLAIN a révélé que le DISTINCT ON scanne quand même TOUTE la table
-- silver.velov_clean via idx_silver_velov_station_time (index scan, rows=3.3M)
-- car il n'y a aucune borne temporelle : Postgres ne peut pas savoir que la
-- "dernière mesure par station" se trouve forcément dans les dernières
-- minutes. Mesuré : EXPLAIN ANALYZE timeout à 8s (canceling statement due to
-- statement timeout) — toujours trop lent pour un widget interactif.
--
-- Fix : même pattern que migration_041 (gold.mv_sensor_saturation) — borner
-- la CTE à une fenêtre récente. Vélo'v GBFS ingère */5min (cf. CLAUDE.md),
-- fenêtre 15 min = 3x la cadence, marge de sécurité si un run est en retard.
-- Utilise idx_velov_clean_measurement_time (déjà existant) pour un vrai
-- Index Scan borné (quelques milliers de lignes) au lieu du scan complet.
-- Aucune perte fonctionnelle : la dernière mesure d'une station active est
-- toujours dans les 15 dernières minutes.

CREATE OR REPLACE VIEW referentiel.v_lieux_velov_smart AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
      AND v.measurement_time >= NOW() - INTERVAL '15 minutes'
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
    'Migration 042 : dédup sur measurement_time (index). Migration 043 '
    '(2026-07-03) : latest_velov borné aux 15 dernières minutes (idx_velov_clean_'
    'measurement_time) — sans borne, scan complet de silver.velov_clean (3.3M '
    'lignes, timeout mesuré >8s). Cadence ingestion */5min, marge x3.';


CREATE OR REPLACE VIEW referentiel.v_velov_neighbors AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
      AND v.measurement_time >= NOW() - INTERVAL '15 minutes'
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
    'Sprint VPS-6 — Maillage des bornes Vélov voisines (< 200m). '
    'Migration 043 (2026-07-03) : latest_velov borné aux 15 dernières minutes '
    '(même fix que v_lieux_velov_smart — scan complet sinon).';
