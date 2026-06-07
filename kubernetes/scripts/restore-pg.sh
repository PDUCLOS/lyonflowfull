#!/usr/bin/env bash
# Restore PostgreSQL depuis un dump local.
# Usage : ./scripts/restore-pg.sh path/to/backup.sql.gz [namespace]
#
# ⚠️  ÉCRASE la base existante. Confirmer en passant CONFIRM=yes.

set -euo pipefail
BACKUP="${1:-}"
NS="${2:-lyonflow}"

if [ -z "$BACKUP" ] || [ ! -f "$BACKUP" ]; then
  echo "❌ Backup file manquant ou introuvable : $BACKUP" >&2
  exit 1
fi
if [ "${CONFIRM:-no}" != "yes" ]; then
  echo "⚠️  Cette opération ÉCRASE la base ${NS}/lyonflow." >&2
  echo "    Relancer avec : CONFIRM=yes $0 $@" >&2
  exit 1
fi

echo "▶ Restore $BACKUP → ${NS}/postgres"
gunzip -c "$BACKUP" | kubectl -n "$NS" exec -i statefulset/postgres -- bash -c '
  PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --single-transaction
'
echo "✅ Restore terminé"
