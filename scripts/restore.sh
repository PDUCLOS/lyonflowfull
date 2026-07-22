#!/usr/bin/env bash
# =============================================================================
# LyonFlow — Restore PostgreSQL + MinIO depuis backup
# =============================================================================
# Usage : ./scripts/restore.sh /path/to/backup/lyonflow_20260606_030000
# =============================================================================

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <BACKUP_PATH>"
    echo "Exemple: $0 backups/lyonflow_20260606_030000"
    exit 1
fi

BACKUP_PATH="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Charger .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Couleurs
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

err() { echo -e "${RED}[ERR]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }

# Vérifications
if [ ! -e "${BACKUP_PATH}" ]; then
    err "Backup introuvable : ${BACKUP_PATH}"
    exit 1
fi

echo "ATTENTION : ce script va ÉCRASER la base de données actuelle."
echo "Backup à restaurer : ${BACKUP_PATH}"
read -p "Confirmez avec 'yes' (ou 'no' pour annuler) : " confirm
if [ "${confirm}" != "yes" ]; then
    echo "Annulé."
    exit 0
fi

# -----------------------------------------------------------------------------
# 1. PostgreSQL
# -----------------------------------------------------------------------------
DB_DUMP="${BACKUP_PATH}_postgres.dump"
if [ ! -f "${DB_DUMP}" ]; then
    err "Dump PostgreSQL introuvable : ${DB_DUMP}"
    exit 1
fi

echo "Restauration PostgreSQL..."

if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
    # Via Docker
    docker cp "${DB_DUMP}" "lyonflow-postgres:/tmp/restore.dump"
    docker exec lyonflow-postgres \
        pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --clean --if-exists --no-owner --role="${POSTGRES_USER}" \
        "/tmp/restore.dump"
    docker exec lyonflow-postgres rm "/tmp/restore.dump"
else
    PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
        -h "${POSTGRES_HOST:-localhost}" \
        -p "${POSTGRES_PORT:-5432}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        --clean --if-exists --no-owner \
        "${DB_DUMP}"
fi

ok "PostgreSQL restauré"

# -----------------------------------------------------------------------------
# 2. MinIO (si backup présent)
# -----------------------------------------------------------------------------
MINIO_BACKUP_DIR="${BACKUP_PATH}_minio"
if [ -d "${MINIO_BACKUP_DIR}" ]; then
    echo "Restauration MinIO..."
    if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-minio'; then
        docker run --rm \
            -v "${MINIO_BACKUP_DIR}:/backup" \
            -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@lyonflow-minio:9000" \
            --network lyonflow_default \
            minio/mc mirror --overwrite --quiet /backup/lyonflow-bronze local/lyonflow-bronze 2>&1 | head -3
    fi
    ok "MinIO restauré"
else
    warn "Pas de backup MinIO trouvé pour ${BACKUP_PATH}"
fi

ok "Restauration terminée"
