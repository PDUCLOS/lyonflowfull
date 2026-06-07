#!/usr/bin/env bash
# Seed 7j de donnees Lyon mock dans Postgres K8s (pour demo).
#
# Strategie :
#   1. Si dump pre-genere existe (dumps/demo-seed.dump) → restore
#   2. Sinon → genere via script Python (necessite que pods soient up)
#
# Le dump pre-genere est preferable pour une demo : reproducible,
# rapide (~30s), pas de dependance aux APIs externes.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."
NS="lyonflow"
SEED_DUMP="$ROOT/dumps/demo-seed.dump"

log() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

if [ -f "$SEED_DUMP" ]; then
  log "Dump trouve : $SEED_DUMP"
  kubectl -n "$NS" cp "$SEED_DUMP" postgres-0:/tmp/demo-seed.dump
  kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
    PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
      -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      --no-owner --no-privileges --jobs=2 /tmp/demo-seed.dump
    rm -f /tmp/demo-seed.dump
  '
else
  log "Pas de dump pre-genere. Lancement du seed live (~5 min)"
  log "Trigger DAG Airflow collect_bronze + transform_bronze_to_silver + transform_silver_to_gold"

  # Trigger 7 cycles back-to-back via Airflow CLI dans le pod scheduler
  kubectl -n "$NS" exec -it deploy/airflow-scheduler -- bash -c '
    set -e
    for i in $(seq 1 84); do
      airflow dags trigger collect_bronze
      airflow dags trigger transform_bronze_to_silver
      airflow dags trigger transform_silver_to_gold
      sleep 5
    done
  '
fi

log "Verification volumes seed"
kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "
    SELECT '"'"'bronze'"'"', schemaname, relname, n_live_tup
    FROM pg_stat_user_tables
    WHERE schemaname IN ('"'"'bronze'"'"', '"'"'silver'"'"', '"'"'gold'"'"')
    ORDER BY schemaname, relname;
  "
'
echo "✅ Seed termine"
