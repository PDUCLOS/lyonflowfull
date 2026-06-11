-- =============================================================================
-- LyonFlowFull — Vues matérialisées KPIs lignes TCL + Heatmap OTP (Sprint 7)
-- =============================================================================
-- Sprint 7 (post-Sprint VPS-6, 2026-06-11) — Débloque les pages Pro TCL :
--   * Pro_2_Heatmap_OTP.py : heatmap OTP ligne × heure
--   * Pro_4_Simulateur.py : simulation ajout/retrait bus
--
-- Vue matérialisée = données pré-calculées + index. Refresh par
-- ``DAG refresh_lieux_calendrier`` quotidien 5h (Sprint 7) ou
-- ad-hoc après évolution de gold.bus_delay_segments.
--
-- Définitions KPI :
--   * OTP (On-Time Performance) = % de snapshots avec retard < 2 min
--     (= avg_delay_seconds < 120s). Standard TCL/SNCF.
--   * retard_moyen_s = avg(avg_delay_seconds) sur la fenêtre
--   * frequence_min = 60 / n_observations_par_heure (moyenne véhicules/h)
--   * charge = n_observations / n_observations_max_attendu (%)
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : KPIs par ligne TCL
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_line_kpis_live CASCADE;

CREATE MATERIALIZED VIEW gold.mv_line_kpis_live AS
WITH per_line AS (
    SELECT
        line_ref,
        COUNT(*) AS n_obs_total,
        COUNT(DISTINCT date) AS n_days,
        -- OTP = % de snapshots avec retard < 2 min
        ROUND(
            100.0 * SUM(CASE WHEN avg_delay_seconds < 120 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
            1
        ) AS otp_pct,
        -- Retard moyen
        ROUND(AVG(avg_delay_seconds)::numeric, 1) AS retard_moyen_s,
        -- Fréquence : véhicules observés par heure (moyenne)
        ROUND(
            (SUM(n_observations)::numeric / NULLIF(COUNT(DISTINCT (date::text || '-' || hour::text)), 0)),
            1
        ) AS freq_vehicules_par_h,
        -- Charge = intensité d'observations (proxy)
        ROUND((SUM(n_observations)::numeric / NULLIF(COUNT(*), 0)) * 100.0, 1) AS charge_pct
    FROM gold.bus_delay_segments
    GROUP BY line_ref
)
SELECT
    pl.line_ref,
    pl.n_obs_total,
    pl.n_days,
    pl.otp_pct,
    pl.retard_moyen_s,
    pl.freq_vehicules_par_h,
    pl.charge_pct,
    -- Catégorisation auto (synchronisée avec Sprint VPS-5 load_tcl_lines)
    CASE
        WHEN pl.line_ref LIKE 'T%' THEN 'tram'
        WHEN pl.line_ref LIKE 'M%' THEN 'metro'
        WHEN pl.line_ref LIKE 'C%' THEN 'bus'
        ELSE 'bus'
    END AS mode,
    -- Catégorisation OTP
    CASE
        WHEN pl.otp_pct >= 90 THEN 'excellent'
        WHEN pl.otp_pct >= 75 THEN 'bon'
        WHEN pl.otp_pct >= 60 THEN 'moyen'
        ELSE 'mediocre'
    END AS otp_status
FROM per_line pl
ORDER BY pl.line_ref;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_line_kpis_line_ref
    ON gold.mv_line_kpis_live (line_ref);

COMMENT ON MATERIALIZED VIEW gold.mv_line_kpis_live IS
    'Sprint 7 (2026-06-11) — KPIs par ligne TCL : OTP (%), retard moyen (s), '
    'fréquence (véhicules/h), charge (%). Calculé depuis gold.bus_delay_segments. '
    'Refresh par DAG refresh_lieux_calendrier quotidien 5h.';


-- -----------------------------------------------------------------------------
-- Vue matérialisée : Heatmap OTP (ligne × date × heure)
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_otp_heatmap CASCADE;

CREATE MATERIALIZED VIEW gold.mv_otp_heatmap AS
SELECT
    line_ref AS line_id,
    date,
    hour,
    ROUND(
        100.0 * SUM(CASE WHEN avg_delay_seconds < 120 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        1
    ) AS otp_pct,
    ROUND(AVG(avg_delay_seconds)::numeric, 1) AS avg_delay_s,
    SUM(n_observations) AS n_obs
FROM gold.bus_delay_segments
GROUP BY line_ref, date, hour
ORDER BY line_ref, date, hour;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_otp_heatmap_line_date_hour
    ON gold.mv_otp_heatmap (line_id, date, hour);

CREATE INDEX IF NOT EXISTS idx_mv_otp_heatmap_date
    ON gold.mv_otp_heatmap (date DESC);

COMMENT ON MATERIALIZED VIEW gold.mv_otp_heatmap IS
    'Sprint 7 (2026-06-11) — Heatmap OTP par ligne × date × heure. '
    'Calculé depuis gold.bus_delay_segments. Sert la page Pro_2_Heatmap_OTP.py.';


-- -----------------------------------------------------------------------------
-- Stats refresh (informatif, idempotent)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n_lignes INTEGER;
    n_heat INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_lignes FROM gold.mv_line_kpis_live;
    SELECT COUNT(*) INTO n_heat FROM gold.mv_otp_heatmap;
    RAISE NOTICE 'mv_line_kpis_live : % lignes', n_lignes;
    RAISE NOTICE 'mv_otp_heatmap : % (ligne,date,hour) triplets', n_heat;
END $$;
