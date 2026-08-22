-- Migration 047 — Postgres connection health (Sprint 25, 2026-08-22)
--
-- Pourquoi cette migration existe :
-- Le 2026-08-22, le VPS a enchaîné 51 healthcheck FAIL en 5 jours à cause
-- d'une fuite de connexions TCP côté Postgres (14 backends fantômes d'un
-- container détruit, IPs 172.18.0.5/6/.7, jamais refermés). Cause racine :
-- `tcp_keepalives_idle` = 0 (= défaut OS = 7200s = 2h) → un client mort
-- n'est détecté qu'au bout de 2 h. Le `idle_in_transaction_session_timeout`
-- par défaut = 0 (jamais tué). Effet : à 93 % de RAM (3.7 GiB / 4 GiB), le
-- `vps-watchdog.sh` restartait le stack toutes les ~1 h pour libérer la
-- mémoire → Patrice recevait des alertes Telegram en boucle.
--
-- Cette migration :
--   1. Durcit `idle_in_transaction_session_timeout` à 2 min (SIGHUP-reloadable,
--      donc pas de restart PG requis).
--   2. Crée la vue `gold.v_connection_health` qui agrège `pg_stat_activity`
--      par `application_name` + `client_addr` pour spotter les outliers en
--      un SELECT.
--   3. Note explicite : `tcp_keepalives_idle` NE PEUT PAS être set via
--      ALTER SYSTEM en PG 16 (param `postmaster` context). C'est passé via
--      `command:` dans docker-compose.yml (voir patch du 2026-08-22).
--
-- Idempotence : la migration est rejouable (ALTER SYSTEM est idempotent, la
-- vue utilise CREATE OR REPLACE).
--
-- Vérification après application :
--   SELECT * FROM pg_file_settings WHERE name = 'tcp_keepalives_idle';
--   -- applied = t, setting = 60
--   SELECT * FROM pg_settings WHERE name = 'idle_in_transaction_session_timeout';
--   -- setting = 120000 (2 min en ms)
--   SELECT * FROM gold.v_connection_health ORDER BY backend_count DESC LIMIT 10;
--   -- doit lister les clients avec leur nombre de connexions

-- =============================================================================
-- 1. Durcir idle_in_transaction_session_timeout (2 min)
-- =============================================================================
-- Contexte `user` (SIGHUP-reloadable). Pas besoin de restart PG.
-- Effet : toute transaction idle > 2 min est tuée automatiquement par PG,
-- ce qui libère les locks et la mémoire backend.
ALTER SYSTEM SET idle_in_transaction_session_timeout = '2min';

-- Recharger la conf (SIGHUP)
SELECT pg_reload_conf();

-- =============================================================================
-- 2. Vue gold.v_connection_health — monitoring des connexions par app/client
-- =============================================================================
-- Permet de spotter en un SELECT quel service ouvre trop de connexions ou a
-- des connexions zombies. À câbler dans le healthcheck (Sprint suivant).
--
-- Colonnes :
--   * application_name : identifiant du service (vide = client qui n'a pas
--     set application_name → suspect si beaucoup de connexions)
--   * client_addr : IP source (si connexion TCP ; NULL = socket unix local)
--   * state : active / idle / idle in transaction / ...
--   * backend_count : nombre de backends dans ce groupe
--   * oldest_backend_age : age du backend le plus ancien (interval)
--   * oldest_state_change : age du plus ancien state change
--   * total_memory_mb_est : estimation mémoire (basée sur 150 MB/backend,
--     valeur empirique Sprint 25) — à affiner avec pg_buffercache plus tard.
CREATE OR REPLACE VIEW gold.v_connection_health AS
SELECT
    COALESCE(NULLIF(application_name, ''), '<empty>') AS application_name,
    COALESCE(client_addr::text, 'local')              AS client_addr,
    state,
    count(*)                                          AS backend_count,
    MIN(backend_start)                                AS oldest_backend_start,
    MAX(backend_start)                                AS newest_backend_start,
    NOW() - MIN(backend_start)                        AS oldest_backend_age,
    NOW() - MIN(state_change)                         AS oldest_state_change,
    ROUND(count(*) * 150.0 / 1024.0, 2)               AS total_memory_mb_est,
    -- Flags d'alerte
    (count(*) > 5)                                    AS too_many_backends,
    (NOW() - MIN(state_change) > INTERVAL '1 hour'
     AND state LIKE 'idle%')                          AS stale_idle_alert
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()  -- exclure la session courante (psql)
GROUP BY 1, 2, 3
ORDER BY backend_count DESC;

COMMENT ON VIEW gold.v_connection_health IS
    'Sprint 25 (2026-08-22) — Vue de monitoring des connexions PG. '
    'Agrège pg_stat_activity par application_name + client_addr + state. '
    'Permet de spotter les services qui ouvrent trop de connexions ou qui '
    'laissent des backends zombies. Câbler dans le healthcheck-vps.sh.';

-- =============================================================================
-- 3. Grant select sur la vue (au user dashboard via search_path déjà OK)
-- =============================================================================
-- gold.v_connection_health est dans le search_path par défaut (cf.
-- src/db/connection.py raw_connection options), donc accessible aux
-- requêtes user `lyonflow`. Pas de GRANT explicite nécessaire.

-- =============================================================================
-- Vérification immédiate (commenté pour ne pas crasher la migration)
-- =============================================================================
-- SELECT * FROM gold.v_connection_health ORDER BY backend_count DESC LIMIT 5;
-- SELECT name, setting FROM pg_settings WHERE name = 'idle_in_transaction_session_timeout';
