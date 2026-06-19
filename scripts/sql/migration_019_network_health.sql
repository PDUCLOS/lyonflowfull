-- Migration 019 — Score de sante reseau temps reel (Axe 5, Sprint 15+)
--
-- Fonction SQL ``gold.fn_network_health_score()`` qui calcule un KPI
-- unique 0-100 pour l'etat global du reseau de mobilite Lyon.
--
-- Formule :
--   score = 100
--     - pct_congestion  * 0.3   (trafic routier)
--     - pct_tcl_delayed * 0.3   (transport en commun)
--     - pct_velov_empty * 0.2   (velov)
--     - meteo_penalty           (meteo defavorable, 0-15 pts)
--
-- Gestion sources indisponibles : si une source n'a aucune donnee
-- recente (< 30 min), son poids est redistribue sur les autres
-- au lieu de compter 0% (faussement "parfait").
--
-- Dependances :
--   * gold.traffic_features_live  (fetched_at, speed_kmh)
--   * gold.tcl_vehicle_realtime   (recorded_at, is_delayed)
--   * silver.velov_clean          (fetched_at, num_bikes_available)
--   * silver.meteo_hourly         (measurement_time, precipitation, temperature_2m)
--
-- Idempotent : DROP + CREATE.

DROP FUNCTION IF EXISTS gold.fn_network_health_score();

CREATE OR REPLACE FUNCTION gold.fn_network_health_score()
RETURNS TABLE (
    score          numeric(5,2),
    pct_congestion numeric(5,2),
    pct_tcl_delayed numeric(5,2),
    pct_velov_empty numeric(5,2),
    meteo_penalty  numeric(5,2),
    traffic_available boolean,
    tcl_available    boolean,
    velov_available  boolean,
    meteo_available  boolean,
    diagnosis      text,
    computed_at    timestamptz
) AS $$
WITH
traffic_raw AS (
    SELECT
        COUNT(*)::int AS n,
        SUM(CASE WHEN speed_kmh < 25 THEN 1 ELSE 0 END)::int AS n_cong
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '30 minutes'
),
traffic AS (
    SELECT
        n > 0 AS available,
        CASE WHEN n > 0
            THEN (n_cong::float / n * 100)::numeric(5,2)
            ELSE NULL
        END AS pct_cong
    FROM traffic_raw
),
tcl_raw AS (
    SELECT
        COUNT(*)::int AS n,
        SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END)::int AS n_del
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '30 minutes'
),
tcl AS (
    SELECT
        n > 0 AS available,
        CASE WHEN n > 0
            THEN (n_del::float / n * 100)::numeric(5,2)
            ELSE NULL
        END AS pct_del
    FROM tcl_raw
),
velov_raw AS (
    SELECT
        COUNT(*)::int AS n,
        SUM(CASE WHEN num_bikes_available = 0 THEN 1 ELSE 0 END)::int AS n_empty
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
),
velov AS (
    SELECT
        n > 0 AS available,
        CASE WHEN n > 0
            THEN (n_empty::float / n * 100)::numeric(5,2)
            ELSE NULL
        END AS pct_empty
    FROM velov_raw
),
meteo AS (
    SELECT
        TRUE AS available,
        CASE
            WHEN precipitation > 5 THEN 15
            WHEN precipitation > 1 THEN 8
            WHEN temperature_2m < 0 THEN 10
            WHEN temperature_2m > 35 THEN 5
            ELSE 0
        END::numeric(5,2) AS penalty
    FROM silver.meteo_hourly
    WHERE measurement_time > NOW() - INTERVAL '2 hours'
    ORDER BY measurement_time DESC
    LIMIT 1
),
meteo_safe AS (
    SELECT
        COALESCE((SELECT available FROM meteo), FALSE) AS available,
        COALESCE((SELECT penalty FROM meteo), 0)::numeric(5,2) AS penalty
),
weights AS (
    SELECT
        CASE WHEN t.available THEN 0.3 ELSE 0 END AS w_traffic,
        CASE WHEN c.available THEN 0.3 ELSE 0 END AS w_tcl,
        CASE WHEN v.available THEN 0.2 ELSE 0 END AS w_velov,
        0.2 AS w_meteo,
        COALESCE(t.pct_cong, 0) AS pct_cong,
        COALESCE(c.pct_del, 0) AS pct_del,
        COALESCE(v.pct_empty, 0) AS pct_empty,
        ms.penalty AS penalty,
        t.available AS t_avail,
        c.available AS c_avail,
        v.available AS v_avail,
        ms.available AS m_avail
    FROM traffic t, tcl c, velov v, meteo_safe ms
),
normalized AS (
    SELECT *,
        CASE WHEN (w_traffic + w_tcl + w_velov + w_meteo) > 0
            THEN 1.0 / (w_traffic + w_tcl + w_velov + w_meteo)
            ELSE 1.0
        END AS scale
    FROM weights
)
SELECT
    GREATEST(0, LEAST(100,
        100
        - pct_cong   * w_traffic * scale
        - pct_del    * w_tcl     * scale
        - pct_empty  * w_velov   * scale
        - penalty    * w_meteo   * scale
    ))::numeric(5,2) AS score,
    pct_cong,
    pct_del,
    pct_empty,
    penalty,
    t_avail,
    c_avail,
    v_avail,
    m_avail,
    CASE
        WHEN GREATEST(0, 100 - pct_cong*w_traffic*scale
             - pct_del*w_tcl*scale - pct_empty*w_velov*scale
             - penalty*w_meteo*scale) > 75 THEN 'healthy'
        WHEN GREATEST(0, 100 - pct_cong*w_traffic*scale
             - pct_del*w_tcl*scale - pct_empty*w_velov*scale
             - penalty*w_meteo*scale) > 50 THEN 'stressed'
        WHEN GREATEST(0, 100 - pct_cong*w_traffic*scale
             - pct_del*w_tcl*scale - pct_empty*w_velov*scale
             - penalty*w_meteo*scale) > 25 THEN 'degraded'
        ELSE 'critical'
    END AS diagnosis,
    NOW() AS computed_at
FROM normalized;
$$ LANGUAGE SQL STABLE;

COMMENT ON FUNCTION gold.fn_network_health_score() IS
    'Score de sante reseau 0-100 temps reel. Axe 5 Sprint 15+ (migration 019). '
    'Poids redistribues si source indisponible.';
