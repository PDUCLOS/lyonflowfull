-- =============================================================================
-- LyonFlowFull — Maillage des bornes Vélov (Sprint VPS-6, 2026-06-11)
-- =============================================================================
-- Vue qui croise referentiel.lieux_lyon avec silver.velov_clean pour
-- proposer, pour chaque lieu, la meilleure borne Vélov disponible avec
-- son maillage de voisines (bornes à < 200m les unes des autres).
--
-- Logique :
--   * get_smart_velov_for_lieu : top K bornes triées par score composite
--     (distance + vélos dispo + docks dispo)
--   * get_velov_neighbors : pour une borne, renvoie les K voisines
--     (distance < 200m) avec dispo temps réel
--
-- Idempotent : CREATE OR REPLACE VIEW.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue : top K bornes Vélov par lieu, scorées par disponibilité
-- -----------------------------------------------------------------------------
-- score :
--   * Si vélos = 0 (aller impossible) → -10000
--   * Si docks = 0 (retour impossible) → -5000
--   * Sinon : -distance_m (le plus proche gagne)
-- On limite au top 3 par lieu, ordonnées par score DESC (meilleur d'abord).
CREATE OR REPLACE VIEW referentiel.v_lieux_velov_smart AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
    ORDER BY v.station_id, v.fetched_at DESC
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
        -- Score composite
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
    'Utilisé par Mon Trajet pour proposer une alternative si la borne #1 est pleine.';


-- -----------------------------------------------------------------------------
-- Vue : voisines d'une borne Vélov (maillage local < 200m)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW referentiel.v_velov_neighbors AS
WITH latest_velov AS (
    SELECT DISTINCT ON (v.station_id)
        v.station_id, v.station_name, v.lat, v.lon,
        v.num_bikes_available, v.num_docks_available, v.is_active
    FROM silver.velov_clean v
    WHERE v.is_active = TRUE
      AND v.num_bikes_available IS NOT NULL
      AND v.num_docks_available IS NOT NULL
    ORDER BY v.station_id, v.fetched_at DESC
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
  ON a.station_id < b.station_id  -- éviter doublons
 AND referentiel.haversine_m(a.lat, a.lon, b.lat, b.lon) < 200
ORDER BY a.station_id, distance_m;

COMMENT ON VIEW referentiel.v_velov_neighbors IS
    'Sprint VPS-6 — Maillage des bornes Vélov voisines (< 200m). Lyon a ~458 '
    'stations, ~10-20k paires voisines. Utilisé pour le rendu carte "grappe" '
    'et pour suggérer des alternatives à pied en cas de borne pleine/vide.';
