#!/usr/bin/env bash
# Migration data VPS PostgreSQL → K8s Postgres.
#
# Usage : ./scripts/migrate-vps.sh user@vps-host
#
# Pre-requis : ssh agent + kubectl pointe sur le cluster cible.
#
# Etapes :
#   1. Dump VPS (format custom -Fc)
#   2. Transfert local
#   3. Copy → pod K8s
#   4. Restore (pg_restore, drop avant si CONFIRM=yes)
#   5. Checksums gold tables (verif integrite)

set -euo pipefail

VPS="${1:-}"
[ -z "$VPS" ] && { echo "Usage: $0 user@host" >&2; exit 1; }

NS="lyonflow"
WORK_DIR="$(mktemp -d -t lyonflow-migrate.XXXXXX)"
DUMP_FILE="$WORK_DIR/lyonflow_vps_$(date -u +%Y%m%d_%H%M%S).dump"

log() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

# 1. Dump VPS
log "Dump VPS depuis $VPS (format custom)"
ssh "$VPS" "sudo -u postgres pg_dump -Fc lyonflow" > "$DUMP_FILE"
echo "   Taille dump : $(du -h "$DUMP_FILE" | cut -f1)"

# 2. Checksum VPS gold tables (avant transfert)
log "Checksum VPS gold.*"
ssh "$VPS" "sudo -u postgres psql -d lyonflow -t -c \"
  SELECT 'gold.traffic_features_live', COUNT(*), MD5(string_agg(channel_id::text, ',' ORDER BY measurement_time)) FROM gold.traffic_features_live;
  SELECT 'gold.velov_features',        COUNT(*), MD5(string_agg(station_id::text, ',' ORDER BY measurement_time)) FROM gold.velov_features;
  SELECT 'gold.bus_delay_segments',    COUNT(*), '' FROM gold.bus_delay_segments;
\"" | tee "$WORK_DIR/checksum-vps.txt"

# 3. Copy → pod K8s
log "Transfert vers postgres-0"
kubectl -n "$NS" cp "$DUMP_FILE" postgres-0:/tmp/lyonflow.dump

# 4. Restore
if [ "${CONFIRM:-no}" != "yes" ]; then
  log "Dry-run terminé. Pour appliquer le restore : CONFIRM=yes $0 $VPS"
  exit 0
fi
log "Restore (DROP + restore) dans pod K8s"
kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
  set -euo pipefail
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    --clean --if-exists --no-owner --no-privileges \
    --jobs=4 /tmp/lyonflow.dump
  rm -f /tmp/lyonflow.dump
'

# 5. Checksum K8s gold tables (post-restore)
log "Checksum K8s gold.*"
kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "
    SELECT '"'"'gold.traffic_features_live'"'"', COUNT(*), MD5(string_agg(channel_id::text, '"'"','"'"' ORDER BY measurement_time)) FROM gold.traffic_features_live;
    SELECT '"'"'gold.velov_features'"'"',        COUNT(*), MD5(string_agg(station_id::text, '"'"','"'"' ORDER BY measurement_time)) FROM gold.velov_features;
    SELECT '"'"'gold.bus_delay_segments'"'"',    COUNT(*), '"'"''"'"' FROM gold.bus_delay_segments;
  "
' | tee "$WORK_DIR/checksum-k8s.txt"

log "Diff checksums :"
diff "$WORK_DIR/checksum-vps.txt" "$WORK_DIR/checksum-k8s.txt" && echo "✅ Identique" || echo "⚠️  Difference detectee"

log "Done. Logs disponibles dans $WORK_DIR"
