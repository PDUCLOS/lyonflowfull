-- =============================================================================
-- Migration 048 — Débloat osm.ways + retrait index cost/reverse_cost (Sprint 26, 2026-09-22)
-- =============================================================================
-- Pourquoi cette migration existe :
-- Le DAG refresh_osm_traffic_costs (UPDATE de ~39k arêtes toutes les 15 min)
-- échouait 20 % du temps en `statement_timeout` (240 s), et le
-- dag-failure-rate-monitor.sh envoyait une alerte Telegram toutes les 30 min
-- (flapping pile sur le seuil 20 %).
--
-- Mesures VPS 2026-09-22 (pgstattuple_approx / pg_stat_user_indexes) :
--   - osm.ways : 101 555 lignes, heap 1 561 Mo, 98 % d'espace libre, 2 % de
--     tuples vivants. Attendu : ~30-50 Mo.
--   - idx_ways_cost : 316 Mo, densité feuilles 1 %, idx_scan = 0.
--   - idx_ways_reverse_cost : 152 Mo, idx_scan = 0.
--   - ways_the_geom_idx (GIST) : 435 Mo. Attendu : ~15 Mo.
--   - n_tup_upd cumulés : 48 M.
--
-- Cause racine : la migration 029 a créé des B-tree sur `cost` et
-- `reverse_cost` en supposant que pgr_dijkstra ferait des lookups par coût.
-- Faux : pgr_dijkstra charge le résultat de
--   'SELECT gid, source, target, cost, reverse_cost FROM osm.ways WHERE cost > 0'
-- en mémoire et exécute Dijkstra côté C++ (cf. osm.route_car). Les stats
-- confirment : 0 scan depuis la création. En revanche, `cost` étant une
-- colonne indexée, chaque UPDATE devient non-HOT → nouvelle version de ligne
-- dans le heap + entrée dans les 3 index à chaque cycle → bloat exponentiel.
-- La partie SELECT de osm.refresh_traffic_costs() prend 7 s ; les ~190 s
-- restants sont l'UPDATE dans 2,4 Go de vide.
--
-- Cette migration :
--   1. Supprime les 2 index morts (CONCURRENTLY, pas de lock table).
--   2. Baisse le fillfactor à 50 pour laisser de la place aux updates HOT
--      (plus aucune colonne mise à jour n'est indexée après l'étape 1).
--   3. VACUUM FULL osm.ways : réécrit la table et reconstruit tous les index
--      restants (pkey, source, target, GIST geom). Lock ACCESS EXCLUSIVE
--      ~1 min ; le routing voiture (osm.route_car / pgr_ksp) est indisponible
--      pendant ce temps. lock_timeout 90 s : si le DAG tient encore un lock,
--      la migration échoue proprement (--force 48 pour rejouer) plutôt que de
--      bloquer la file d'attente Postgres.
--
-- Résultat attendu : DAG refresh_osm_traffic_costs < 15 s, plus de timeout.
-- Rollback : CREATE INDEX CONCURRENTLY (cf. migration 029) — déconseillé.
--
-- Convention apply-migrations.sh : autocommit psql, chaque statement est sa
-- propre transaction (obligatoire pour CONCURRENTLY et VACUUM FULL).
-- Idempotence : IF EXISTS partout, VACUUM FULL rejouable.
-- =============================================================================

\echo '>> 048.1 DROP index morts cost / reverse_cost'
DROP INDEX CONCURRENTLY IF EXISTS osm.idx_ways_cost;
DROP INDEX CONCURRENTLY IF EXISTS osm.idx_ways_reverse_cost;

\echo '>> 048.2 fillfactor 50 (updates HOT)'
ALTER TABLE osm.ways SET (fillfactor = 50);

\echo '>> 048.3 VACUUM FULL osm.ways (lock exclusif ~1 min)'
SET lock_timeout = '90s';
SET statement_timeout = '900s';
VACUUM (FULL, ANALYZE) osm.ways;

\echo '>> 048.4 Tailles après migration'
SELECT
    pg_size_pretty(pg_relation_size('osm.ways')) AS heap,
    pg_size_pretty(pg_indexes_size('osm.ways')) AS indexes,
    (SELECT count(*) FROM osm.ways) AS rows;
