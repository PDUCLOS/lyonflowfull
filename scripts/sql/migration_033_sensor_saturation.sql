-- Migration 033 — Sprint 22+ audit saturation (Patrice)
--
-- Constat : avant cette migration, le dashboard affichait une
-- "vitesse moyenne" calculée par seuils absolus (35/25/15 km/h)
-- sans savoir si les capteurs étaient en panne, à 0, ou avec une
-- variation trop faible (= stuck). La saturation et l'amplitude
-- par capteur n'existaient pas.
--
-- Cette migration crée la vue ``gold.v_sensor_saturation`` qui
-- calcule pour chaque capteur actif sur 7 jours :
--   * v85_7j         : 85e percentile des vitesses mesurées (= vitesse
--                      libre typique, indicateur engineering standard)
--   * vmin_24h       : min sur 24h glissantes
--   * vmax_24h       : max sur 24h glissantes
--   * std_24h        : écart-type sur 24h glissantes
--   * amp_pct        : (vmax_24h - vmin_24h) / v85_7j * 100
--   * sat_now_pct    : vitesse actuelle / v85_7j * 100
--   * status         : 'ok' | 'stale' | 'stuck' | 'no_data'
--
-- Seuils Sprint 22+ (validés par Patrice) :
--   * stuck  : amp_pct < 2 ET std_24h < 1 km/h (variation < 2% sur 24h
--              ET std quasi nul = capteur bloqué)
--   * stale  : pas de mesure dans les 15 dernières minutes
--   * no_data: pas de mesure dans les 7 derniers jours
--
-- Performance : la vue fait un scan des 7 derniers jours sur
-- gold.traffic_features_live (~889k rows, indexé sur channel_id +
-- computed_at). Refresh recommandé toutes les 15 min via
-- ``dags/maintenance/refresh_sensor_saturation.py``.

CREATE OR REPLACE VIEW gold.v_sensor_saturation AS
WITH
    -- Mesures des 7 derniers jours (fenêtre large pour v85)
    measurements_7d AS (
        SELECT
            channel_id,
            speed_kmh,
            computed_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL
          AND speed_kmh > 0  -- cohérent avec _parse_grandlyon_vitesse fix
          AND computed_at >= NOW() - INTERVAL '7 days'
    ),
    -- Mesures des dernières 24h (pour amplitude + std)
    measurements_24h AS (
        SELECT
            channel_id,
            speed_kmh,
            computed_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL
          AND speed_kmh > 0
          AND computed_at >= NOW() - INTERVAL '24 hours'
    ),
    -- Aggrégats 7j par capteur
    agg_7d AS (
        SELECT
            channel_id,
            COUNT(*)                              AS n_obs_7d,
            PERCENTILE_CONT(0.85)
                WITHIN GROUP (ORDER BY speed_kmh)  AS v85_7j,
            MAX(computed_at)                       AS last_7d_at
        FROM measurements_7d
        GROUP BY channel_id
    ),
    -- Aggrégats 24h par capteur
    agg_24h AS (
        SELECT
            channel_id,
            COUNT(*)        AS n_obs_24h,
            MIN(speed_kmh)  AS vmin_24h,
            MAX(speed_kmh)  AS vmax_24h,
            STDDEV(speed_kmh) AS std_24h,
            AVG(speed_kmh)  AS avg_24h,
            MAX(computed_at) AS last_at
        FROM measurements_24h
        GROUP BY channel_id
    ),
    -- Mesure la plus récente (pour sat_now_pct)
    latest AS (
        SELECT DISTINCT ON (channel_id)
            channel_id,
            speed_kmh AS current_speed,
            computed_at AS current_at
        FROM gold.traffic_features_live
        WHERE speed_kmh IS NOT NULL AND speed_kmh > 0
        ORDER BY channel_id, computed_at DESC
    )
SELECT
    a7.channel_id,
    a7.n_obs_7d,
    a7.v85_7j,
    a7.last_7d_at,
    a24.n_obs_24h,
    a24.vmin_24h,
    a24.vmax_24h,
    a24.std_24h,
    a24.avg_24h,
    a24.last_at AS last_24h_at,
    -- Saturation = vitesse actuelle / v85 * 100
    --   > 100% = congestion (trafic plus lent que la vitesse libre)
    --   < 50%  = fluide
    --   ~ 100% = vitesse libre typique
    ROUND(
        (l.current_speed / NULLIF(a7.v85_7j, 0)) * 100,
        1
    )                                                       AS sat_now_pct,
    l.current_speed                                        AS current_speed_kmh,
    -- Amplitude = range 24h / v85_7j * 100
    --   > 50% = variation typique (fluide ↔ bouchon)
    --   < 2%  = suspect (capteur stuck)
    ROUND(
        ((a24.vmax_24h - a24.vmin_24h) / NULLIF(a7.v85_7j, 0)) * 100,
        1
    )                                                       AS amp_pct,
    -- Statut de santé
    CASE
        WHEN a7.n_obs_7d IS NULL OR a7.n_obs_7d = 0
            THEN 'no_data'
        WHEN a24.last_at < NOW() - INTERVAL '15 minutes'
            THEN 'stale'
        WHEN a24.std_24h < 1.0
         AND ((a24.vmax_24h - a24.vmin_24h) / NULLIF(a7.v85_7j, 0)) * 100 < 2.0
            THEN 'stuck'
        ELSE 'ok'
    END                                                     AS status
FROM agg_7d a7
LEFT JOIN agg_24h a24 ON a7.channel_id = a24.channel_id
LEFT JOIN latest l   ON a7.channel_id = l.channel_id;

-- Index implicit via le materialisé si on en fait une table.
-- Pour l'instant c'est une VIEW (pas de coût de stockage).
-- Le widget Pro_6 + Elu_1 liront directement.
COMMENT ON VIEW gold.v_sensor_saturation IS
    'Sprint 22+ : saturation %v85 + amplitude %v85 + status par capteur.
     Refresh : implicite (vue = recalcul à chaque query). Pour de la perf,
     on materialisera Sprint 23+ via dags/maintenance/refresh_sensor_saturation.py.';

-- Pas de grant nécessaire : utilise les grants existants sur
-- gold.traffic_features_live (déjà accessibles par le user lyonflow).
