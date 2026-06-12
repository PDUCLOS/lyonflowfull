-- =============================================================================
-- LyonFlowFull — Cadences observées par ligne × tranche horaire × type de jour
-- =============================================================================
-- Sprint VPS-6 (2026-06-11) — Table calculée automatiquement depuis
-- gold.tcl_vehicle_realtime + bronze.calendrier_scolaire + bronze.jours_feries.
--
-- Vocabulaire :
--   * ``ligne_ref`` : identifiant TCL (T1..T7, M_A..M_D, C_1..C_17, bus 1-100)
--   * ``time_bucket`` : tranche horaire de 1h ('06:00', '07:00', ..., '22:00')
--   * ``day_type`` : 'weekday' (lundi-vendredi hors vacances/férié),
--                     'saturday', 'sunday_holiday' (dimanche + jours fériés),
--                     'vacation' (vacances scolaires Zone A, tout jour de semaine)
--   * ``n_observations`` : nombre de snapshots 5min observés sur la fenêtre (7j)
--   * ``n_vehicles_avg`` : nombre moyen de véhicules vus par snapshot
--   * ``cadence_min_per_vehicle`` : intervalle moyen entre 2 véhicules (min)
--
-- Logique de calcul :
--   Pour chaque (ligne_ref, time_bucket, day_type), on compte le nb de véhicules
--   uniques observés dans les 7 derniers jours, et on en déduit une cadence
--   empirique. Pas d'invention : si la ligne n'a jamais été observée à ce
--   créneau, la ligne n'apparaît pas dans la table.
--
-- Vue de calcul : ``referentiel.v_cadence_observed`` (rafraîchie à la demande)
-- Table matérialisée : ``referentiel.lieux_calendrier`` (remplie par le seed)
-- =============================================================================

-- Vue : observations brutes (ligne × heure × type_jour) sur 7j glissants
CREATE OR REPLACE VIEW referentiel.v_cadence_observed_7d AS
WITH snapshots AS (
    SELECT
        line_ref,
        recorded_at,
        DATE(recorded_at) AS d,
        EXTRACT(HOUR FROM recorded_at) AS h,
        EXTRACT(DOW FROM recorded_at) AS dow -- 0=dim, 1=lun, ..., 6=sam
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at >= NOW() - INTERVAL '7 days'
      AND line_ref IS NOT NULL
),
typed AS (
    SELECT
        s.*,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM bronze.jours_feries jf
                WHERE jf.date_ferie = s.d
            ) OR s.dow = 0 THEN 'sunday_holiday'
            WHEN EXISTS (
                SELECT 1 FROM bronze.calendrier_scolaire cs
                WHERE cs.start_date <= s.d AND cs.end_date >= s.d
                  AND cs.zone = 'A'
            ) AND s.dow BETWEEN 1 AND 5 THEN 'vacation'
            WHEN s.dow = 6 THEN 'saturday'
            ELSE 'weekday'
        END AS day_type
    FROM snapshots s
),
hour_slots AS (
    -- Pour chaque (line_ref, d, h, day_type), on liste les véhicules vus
    -- dans la fenêtre de 1h, via LATERAL.
    SELECT
        t.line_ref,
        t.d,
        t.h,
        t.day_type,
        v.vehicle_ref
    FROM typed t
    CROSS JOIN LATERAL (
        SELECT DISTINCT v2.vehicle_ref
        FROM gold.tcl_vehicle_realtime v2
        WHERE v2.line_ref = t.line_ref
          AND v2.recorded_at >= t.d + t.h * INTERVAL '1 hour'
          AND v2.recorded_at <  t.d + (t.h + 1) * INTERVAL '1 hour'
    ) v
)
SELECT
    line_ref,
    LPAD(h::int::text, 2, '0') || ':00' AS time_bucket,
    day_type,
    -- nb d'observations 1h distinctes (1 par heure/slot de la semaine)
    COUNT(DISTINCT (d::text || '-' || h::text))::int AS n_observations,
    -- nb de véhicules uniques vus sur tous les slots de cette ligne/heure/type_jour
    COUNT(DISTINCT vehicle_ref)::int AS n_vehicles_seen
FROM hour_slots
GROUP BY line_ref, h, day_type;

COMMENT ON VIEW referentiel.v_cadence_observed_7d IS 'Observations brutes (7j glissants) des véhicules TCL par ligne × tranche horaire × type de jour. Base de calcul de la table lieux_calendrier.';


-- Vue finale : cadence estimée (intervalle en minutes entre 2 véhicules)
CREATE OR REPLACE VIEW referentiel.v_cadence_summary AS
SELECT
    line_ref,
    time_bucket,
    day_type,
    n_observations,
    n_vehicles_seen,
    -- Cadence théorique : si on voit N véhicules dans 12 snapshots de 5min (= 1h),
    -- l'intervalle moyen est 60/N minutes. Cas dégénéré N=0 → NULL.
    CASE
        WHEN n_vehicles_seen = 0 THEN NULL
        ELSE ROUND(60.0 / n_vehicles_seen, 1)
    END AS cadence_min_per_vehicle,
    -- Score de confiance : nb d'observations (1 semaine = 7 occurrences attendues
    -- par day_type ; au-dessus de 5 = fiable)
    CASE
        WHEN n_observations >= 5 THEN 'high'
        WHEN n_observations >= 2 THEN 'medium'
        ELSE 'low'
    END AS confidence
FROM referentiel.v_cadence_observed_7d;

COMMENT ON VIEW referentiel.v_cadence_summary IS 'Cadence observée (min/véhicule) par ligne × tranche horaire × type de jour, calculée sur 7j glissants. Confidence = nb d''observations.';


-- Table matérialisée vide — peuplée par le script Python
--   scripts/seed_lieux_calendrier.py
-- Stratégie : on stocke ligne_ref (pas un calcul à la volée) pour que le
-- dashboard puisse lire en O(1) sans refaire l'agrégation à chaque render.
CREATE TABLE IF NOT EXISTS referentiel.lieux_calendrier (
    id                          SERIAL PRIMARY KEY,
    line_ref                    TEXT NOT NULL,
    day_type                    TEXT NOT NULL,           -- weekday, saturday, sunday_holiday, vacation
    time_bucket                 TEXT NOT NULL,           -- '06:00' format
    cadence_min_per_vehicle     DOUBLE PRECISION,        -- NULL si pas observé
    n_observations              INTEGER NOT NULL DEFAULT 0,
    confidence                  TEXT NOT NULL DEFAULT 'low',  -- low|medium|high
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_calendrier_line_day_hour UNIQUE (line_ref, day_type, time_bucket),
    CONSTRAINT ck_calendrier_day_type CHECK (day_type IN ('weekday','saturday','sunday_holiday','vacation'))
);

CREATE INDEX IF NOT EXISTS idx_lieux_calendrier_line ON referentiel.lieux_calendrier (line_ref);
CREATE INDEX IF NOT EXISTS idx_lieux_calendrier_day ON referentiel.lieux_calendrier (day_type, time_bucket);

COMMENT ON TABLE  referentiel.lieux_calendrier IS 'Cadence TCL observée (min/véhicule) par ligne × tranche horaire × type de jour. Peuplée par scripts/seed_lieux_calendrier.py depuis gold.tcl_vehicle_realtime + bronze.calendrier_scolaire + bronze.jours_feries. Recalcul quotidien recommandé (DAG refresh_lieux_calendrier, Sprint 7+).';
COMMENT ON COLUMN referentiel.lieux_calendrier.cadence_min_per_vehicle IS 'Intervalle moyen entre 2 véhicules (min). NULL si pas observé sur 7j.';
COMMENT ON COLUMN referentiel.lieux_calendrier.confidence IS 'Fiabilité : high (>=5 obs) / medium (>=2) / low (<2).';
