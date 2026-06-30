#!/usr/bin/env bash
# healthcheck-gold-stale.sh — diagnostic gold stale (TCL + trafic morts)
# Cause suspecte: dag_transform_silver_to_gold bloqué sur refresh_mv_bus_traffic_spatial
# Usage VPS: bash scripts/healthcheck-gold-stale.sh
set -uo pipefail

PG="docker exec lyonflow-postgres psql -U ${POSTGRES_USER:-lyonflow} -d ${POSTGRES_DB:-lyonflow} -tAc"
SCHED="lyonflow-airflow-scheduler"
WORKER="lyonflow-airflow-worker"

line(){ printf '\n=== %s ===\n' "$1"; }

line "1. FRAICHEUR GOLD (âge en min, <10 attendu)"
$PG "SELECT 'traffic_features_live', round(extract(epoch FROM now()-max(computed_at))/60,1) FROM gold.traffic_features_live;"
$PG "SELECT 'mv_line_kpis_live', count(*) FROM gold.mv_line_kpis_live;"
$PG "SELECT 'mv_bus_traffic_spatial', count(*) FROM gold.mv_bus_traffic_spatial;"

line "2. CASCADE SILVER (sources gold)"
$PG "SELECT 'silver.tcl_clean', count(*), max(fetched_at) FROM silver.tcl_vehicles_clean;"
$PG "SELECT 'silver.boucles_clean', count(*) FROM silver.trafic_boucles_clean;"

line "3. LOCKS / REQUETES LONGUES (>5 min) — le hang REFRESH CONCURRENTLY"
$PG "SELECT pid, state, round(extract(epoch FROM now()-query_start)/60,1) AS min, left(query,80)
     FROM pg_stat_activity
     WHERE state!='idle' AND now()-query_start > interval '5 min'
     ORDER BY query_start;"

line "4. VERROUS BLOQUANTS sur la MV"
$PG "SELECT relation::regclass, mode, granted, pid
     FROM pg_locks WHERE relation::regclass::text LIKE 'gold.mv_bus_traffic_spatial%';"

line "5. AIRFLOW — runs bloques (running > 30 min)"
echo "--- transform_silver_to_gold (chemin critique */10) ---"
docker exec "$SCHED" airflow dags list-runs -d dag_transform_silver_to_gold --state running 2>/dev/null | head -5
echo "--- refresh_heavy_mv (MV lourdes */30, Sprint 24) ---"
docker exec "$SCHED" airflow dags list-runs -d refresh_heavy_mv --state running 2>/dev/null | head -5

line "6. WORKER OOM?"
docker logs "$WORKER" --tail 200 2>&1 | grep -iE "killed|oom|memoryerror" | tail -5 || echo "pas d'OOM recent"

line "VERDICT"
echo "Si étape 3 montre un REFRESH ... mv_bus_traffic_spatial figé > 30 min:"
echo "  -> tuer la requete:  docker exec lyonflow-postgres psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \"SELECT pg_cancel_backend(<PID>);\""
echo "  -> relancer le DAG:  docker exec $SCHED airflow dags trigger refresh_heavy_mv"
echo "     (ou dag_transform_silver_to_gold si la MV lourde n'a pas encore migré — pré-Sprint 24)"
echo "Si silver vide (étape 2) -> problème en amont (collecteur/transform bronze->silver), remonte la chaîne."
