#!/usr/bin/env bash
# pg-audit.sh — Point santé / perf PostgreSQL LyonFlow (lecture seule).
# Usage VPS : bash scripts/pg-audit.sh
set -uo pipefail
PG="docker exec lyonflow-postgres psql -U ${POSTGRES_USER:-lyonflow} -d ${POSTGRES_DB:-lyonflow} -P pager=off"
line(){ printf '\n========== %s ==========\n' "$1"; }

line "1. CONFIG MÉMOIRE EFFECTIVE (defaults non tunés = problème)"
$PG -c "SELECT name, setting, unit FROM pg_settings
        WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem',
                       'effective_cache_size','max_parallel_workers_per_gather',
                       'random_page_cost','max_connections');"

line "2. TOP 15 TABLES PAR TAILLE (+ croissance gold)"
$PG -c "SELECT schemaname||'.'||relname AS table,
               pg_size_pretty(pg_total_relation_size(relid)) AS total,
               n_live_tup AS rows
        FROM pg_stat_user_tables
        ORDER BY pg_total_relation_size(relid) DESC LIMIT 15;"

line "3. BLOAT / DEAD TUPLES (autovacuum à la traîne ?)"
$PG -c "SELECT schemaname||'.'||relname AS table, n_live_tup, n_dead_tup,
               round(100*n_dead_tup/GREATEST(n_live_tup,1),1) AS pct_dead,
               last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 10000
        ORDER BY n_dead_tup DESC LIMIT 15;"

line "4. CACHE HIT RATIO (doit être > 99% ; sinon shared_buffers trop petit)"
$PG -c "SELECT round(100.0*sum(heap_blks_hit)/GREATEST(sum(heap_blks_hit)+sum(heap_blks_read),1),2) AS cache_hit_pct
        FROM pg_statio_user_tables;"

line "5. INDEX INUTILISÉS (idx_scan=0 = poids mort en écriture)"
$PG -c "SELECT schemaname||'.'||relname AS table, indexrelname AS idx,
               pg_size_pretty(pg_relation_size(indexrelid)) AS size, idx_scan
        FROM pg_stat_user_indexes
        WHERE idx_scan = 0 AND pg_relation_size(indexrelid) > 1000000
        ORDER BY pg_relation_size(indexrelid) DESC LIMIT 20;"

line "6. SEQ SCANS sur grosses tables (index manquant ?)"
$PG -c "SELECT schemaname||'.'||relname AS table, seq_scan, idx_scan,
               n_live_tup AS rows
        FROM pg_stat_user_tables
        WHERE seq_scan > idx_scan AND n_live_tup > 100000
        ORDER BY seq_scan DESC LIMIT 15;"

line "7. REQUÊTES LONGUES EN COURS (> 1 min)"
$PG -c "SELECT pid, state, round(extract(epoch FROM now()-query_start)/60,1) AS min,
               left(query,70) AS query
        FROM pg_stat_activity
        WHERE state!='idle' AND now()-query_start > interval '1 min'
        ORDER BY query_start;"

line "8. ÉTAT VUES MATÉRIALISÉES (peuplées ?)"
$PG -c "SELECT schemaname||'.'||matviewname AS mv, ispopulated,
               pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) AS size
        FROM pg_matviews WHERE schemaname='gold' ORDER BY matviewname;"

line "9. RÉTENTION gold (croissance non bornée ?)"
$PG -c "SELECT 'traffic_features_live' AS t,
               count(*) AS rows,
               min(fetched_at) AS oldest,
               round(extract(epoch FROM max(fetched_at)-min(fetched_at))/86400,1) AS days_span
        FROM gold.traffic_features_live;"

echo
echo "LECTURE :"
echo " - §1 work_mem=4MB (défaut) → tri/hash sur disque pour les GROUP BY lourds."
echo " - §2/§9 si traffic_features_live > ~2M rows et days_span > 3 → pas de rétention."
echo " - §4 cache_hit < 99% → shared_buffers (défaut 128MB) trop petit."
echo " - §5 index idx_scan=0 → candidats DROP (allègent les INSERT */10)."
