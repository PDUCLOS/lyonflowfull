#!/usr/bin/env bash
# Backup ad-hoc PostgreSQL (en plus du CronJob automatique).
# Usage : ./scripts/backup-pg.sh [namespace] [output_dir]

set -euo pipefail
NS="${1:-lyonflow}"
OUT_DIR="${2:-./backups}"

mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
FILE="${OUT_DIR}/lyonflow_${TS}.sql.gz"

echo "▶ Dump depuis postgres pod (ns: ${NS})"
kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    --format=plain --no-owner --no-privileges
' | gzip -9 > "$FILE"

echo "✅ Backup : $FILE ($(du -h "$FILE" | cut -f1))"
