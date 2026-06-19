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
-- Migration 15 (2026-06-19, Sprint 15) — Agrégation par LIGNE PHYSIQUE :
-- retire le suffixe horaire ``_hNN`` du ``line_ref`` (ex
-- ``ActIV:Line::66:SYTRAL_h20`` → ``ActIV:Line::66:SYTRAL``) pour éviter
-- l'explosion de 155+ "lignes" dupliquées dans la heatmap / KPI table.
-- Avant la migration, voir scripts/sql/migration_15_aggregate_line_ref.sql
-- pour la migration forward-only appliquée sur VPS.
--
-- Idempotent : DROP IF EXISTS + CREATE MATERIALIZED VIEW.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Vue matérialisée : KPIs par ligne TCL (agrégation par ligne physique)
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_line_kpis_live CASCADE;

CREATE MATERIALIZED VIEW gold.mv_line_kpis_live AS
WITH per_line AS (
    SELECT
        -- Ligne physique : strip le suffixe _hNN si présent
        CASE
            WHEN line_ref LIKE '%:SYTRAL%'
                THEN SPLIT_PART(line_ref, ':SYTRAL', 1) || ':SYTRAL'
            ELSE line_ref
        END AS line_ref,
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
        -- Charge = intensité d'observations (proxy). n_observations est un
        -- comptage de véhicules par snapshot (souvent > 1), ce qui peut
        -- dépasser 100% si on multiplie par 100 naïvement. On cap à 100
        -- pour respecter le contrat widget ``load_pct: 0..100``.
        -- (BUG-01 audit Pro TCL 2026-06-19 : valeurs aberrantes 675%, 1800%, 3951%)
        LEAST(
            ROUND((SUM(n_observations)::numeric / NULLIF(COUNT(*), 0)) * 100.0, 1),
            100.0
        ) AS charge_pct
    FROM gold.bus_delay_segments
    GROUP BY
        CASE
            WHEN line_ref LIKE '%:SYTRAL%'
                THEN SPLIT_PART(line_ref, ':SYTRAL', 1) || ':SYTRAL'
            ELSE line_ref
        END
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
    -- Note : pour les line_ref ActIV, le mode sera 'bus' (le préfixe
    -- 'ActIV:Line::' ne matche ni 'T%' ni 'M%' ni 'C%'). C'est une
    -- limitation pré-existante de la MV ; le rendu final du mode est
    -- fait côté Python via load_tcl_lines() sur le format court.
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
    'fréquence (véhicules/h), charge (%). '
    'Migration 15 (2026-06-19) : agrégation par ligne PHYSIQUE (sans suffixe _hNN). '
    'Calculé depuis gold.bus_delay_segments. '
    'Refresh par DAG refresh_lieux_calendrier quotidien 5h.';


-- -----------------------------------------------------------------------------
-- Vue matérialisée : Heatmap OTP (ligne physique × date × heure)
-- -----------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS gold.mv_otp_heatmap CASCADE;

CREATE MATERIALIZED VIEW gold.mv_otp_heatmap AS
SELECT
    CASE
        WHEN line_ref LIKE '%:SYTRAL%'
            THEN SPLIT_PART(line_ref, ':SYTRAL', 1) || ':SYTRAL'
        ELSE line_ref
    END AS line_id,
    date,
    hour,
    ROUND(
        100.0 * SUM(CASE WHEN avg_delay_seconds < 120 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        1
    ) AS otp_pct,
    ROUND(AVG(avg_delay_seconds)::numeric, 1) AS avg_delay_s,
    SUM(n_observations) AS n_obs
FROM gold.bus_delay_segments
GROUP BY
    CASE
        WHEN line_ref LIKE '%:SYTRAL%'
            THEN SPLIT_PART(line_ref, ':SYTRAL', 1) || ':SYTRAL'
        ELSE line_ref
    END,
    date,
    hour
ORDER BY line_id, date, hour;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_otp_heatmap_line_date_hour
    ON gold.mv_otp_heatmap (line_id, date, hour);

CREATE INDEX IF NOT EXISTS idx_mv_otp_heatmap_date
    ON gold.mv_otp_heatmap (date DESC);

COMMENT ON MATERIALIZED VIEW gold.mv_otp_heatmap IS
    'Sprint 7 (2026-06-11) — Heatmap OTP par ligne × date × heure. '
    'Migration 15 (2026-06-19) : line_id = ligne PHYSIQUE (sans suffixe _hNN). '
    'Calculé depuis gold.bus_delay_segments. Sert la page Pro_2_Heatmap_OTP.py.';


-- -----------------------------------------------------------------------------
-- Stats refresh (informatif, idempotent)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n_lignes INTEGER;
    n_heat INTEGER;
    n_avec_suffixe INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_lignes FROM gold.mv_line_kpis_live;
    SELECT COUNT(*) INTO n_heat FROM gold.mv_otp_heatmap;
    SELECT COUNT(*) INTO n_avec_suffixe
    FROM gold.mv_line_kpis_live
    WHERE line_ref LIKE '%_h%' AND line_ref LIKE '%:SYTRAL%';
    IF n_avec_suffixe > 0 THEN
        RAISE WARNING 'mv_line_kpis_live contient encore % lignes avec suffixe _hNN !', n_avec_suffixe;
    ELSIF n_lignes > 200 THEN
        RAISE WARNING 'mv_line_kpis_live a % lignes (> 200) — vérifier agrégation', n_lignes;
    ELSE
        RAISE NOTICE 'OK : mv_line_kpis_live : % lignes physiques', n_lignes;
    END IF;
    RAISE NOTICE 'mv_otp_heatmap : % (ligne,date,hour) triplets', n_heat;
END $$;
