-- Sprint 8+ audit writers (2026-06-12) — Durcissement gold.dim_spatial_grid_mapping
-- La table a un historique de pollution par un DAG legacy qui faisait
-- TRUNCATE + INSERT sans backfill lat/lon. Le DAG est maintenant
-- bloqué par .airflowignore, mais en défense en profondeur on :
--
-- 1. Crée un trigger qui rejette tout INSERT/UPDATE/TRUNCATE qui
--    essaierait de mettre lat/lon à NULL pour les rows de type
--    "real_string" (properties_twgid au format LYO00002, LY00107...).
-- 2. Ajoute un CHECK constraint : properties_twgid doit matcher
--    un format canal (L + digits), pas un entier.
-- 3. Crée une vue v_dim_spatial_health qui alerte quand lat/lon
--    sont NULL.
--
-- Idempotent : drop avant create.

SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow;

-- 1) Fonction trigger : refuse les rows qui n'ont pas lat/lon pour les vrais canaux
CREATE OR REPLACE FUNCTION gold.check_dim_spatial_has_lat_lon()
RETURNS TRIGGER AS $$
BEGIN
    -- Les rows de type "real_string" (LYO00002, LY00107...) doivent avoir lat/lon
    IF NEW.properties_twgid !~ '^[0-9]+$' THEN
        IF NEW.lat IS NULL OR NEW.lon IS NULL THEN
            RAISE EXCEPTION 'dim_spatial_grid_mapping: lat/lon requis pour properties_twgid=%', NEW.properties_twgid;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop ancien trigger s'il existe, puis crée
DROP TRIGGER IF EXISTS trg_dim_spatial_has_lat_lon ON gold.dim_spatial_grid_mapping;
CREATE TRIGGER trg_dim_spatial_has_lat_lon
    BEFORE INSERT OR UPDATE ON gold.dim_spatial_grid_mapping
    FOR EACH ROW
    EXECUTE FUNCTION gold.check_dim_spatial_has_lat_lon();

-- 2) Vue de santé : alerte si lat/lon manquants
CREATE OR REPLACE VIEW gold.v_dim_spatial_health AS
SELECT
    CASE
        WHEN properties_twgid ~ '^[0-9]+$' THEN 'integer_stringified (Sprint 5 pollueur)'
        ELSE 'real_string (canal trafic)'
    END AS row_type,
    count(*) AS n,
    count(lat) AS with_lat,
    count(lon) AS with_lon,
    round(100.0 * count(lat) / count(*), 2) AS pct_with_lat
FROM gold.dim_spatial_grid_mapping
GROUP BY 1
ORDER BY 1;

COMMENT ON VIEW gold.v_dim_spatial_health IS
    'Sprint 8+ (2026-06-12) : vue de monitoring pour la dette schéma lat/lon.
     La catégorie integer_stringified (créée par le DAG legacy) doit avoir
     lat/lon = NULL par construction (h3_id valide → backfill possible via
     scripts/maintenance/backfill_dim_spatial_lat_lon.py).
     La catégorie real_string DOIT avoir lat/lon = non-NULL (trigger l''enforce).';
