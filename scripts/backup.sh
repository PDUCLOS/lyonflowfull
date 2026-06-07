#!/usr/bin/env bash
# =============================================================================
# LyonFlowFull — Backup PostgreSQL + MinIO
# =============================================================================
# Cron quotidien recommandé : 0 3 * * * (3h du matin)
# Rétention : 7j local, envoi S3/MinIO distant optionnel
# =============================================================================

set -euo pipefail

# Config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="lyonflow_${TIMESTAMP}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Charger .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*" >&2; }

# -----------------------------------------------------------------------------
# Préparation
# -----------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"
log "Début backup LyonFlowFull → ${BACKUP_DIR}/${BACKUP_NAME}"

# -----------------------------------------------------------------------------
# 1. PostgreSQL
# -----------------------------------------------------------------------------
log "Backup PostgreSQL..."
DB_DUMP="${BACKUP_DIR}/${BACKUP_NAME}_postgres.dump"

# Détecter si on est en local ou via Docker
if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
    # Via Docker
    docker exec lyonflow-postgres \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
        -f "/tmp/${BACKUP_NAME}_postgres.dump"
    docker cp "lyonflow-postgres:/tmp/${BACKUP_NAME}_postgres.dump" "${DB_DUMP}"
    docker exec lyonflow-postgres rm "/tmp/${BACKUP_NAME}_postgres.dump"
else
    # Local direct
    PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
        -h "${POSTGRES_HOST:-localhost}" \
        -p "${POSTGRES_PORT:-5432}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -Fc \
        -f "${DB_DUMP}"
fi

if [ -f "${DB_DUMP}" ]; then
    DB_SIZE=$(du -h "${DB_DUMP}" | cut -f1)
    log "✅ PostgreSQL dumpé : ${DB_DUMP} (${DB_SIZE})"
else
    err "❌ Échec dump PostgreSQL"
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. MinIO (optionnel — seulement si configuré)
# -----------------------------------------------------------------------------
if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-minio'; then
    log "Backup MinIO..."
    MINIO_BACKUP_DIR="${BACKUP_DIR}/${BACKUP_NAME}_minio"

    docker run --rm \
        -v "${MINIO_BACKUP_DIR}:/backup" \
        -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@lyonflow-minio:9000" \
        --network lyonflow_default \
        minio/mc mirror --quiet local/lyonflow-bronze /backup/lyonflow-bronze 2>&1 | head -3

    if [ -d "${MINIO_BACKUP_DIR}" ]; then
        log "✅ MinIO mirroré : ${MINIO_BACKUP_DIR}"
    else
        warn "⚠️  MinIO backup partiel ou échoué"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Purge anciens backups
# -----------------------------------------------------------------------------
log "Purge backups > ${RETENTION_DAYS}j..."
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -name "lyonflow_*" -mtime +${RETENTION_DAYS} -print -delete 2>/dev/null | wc -l)
log "✅ ${DELETED} ancien(s) backup(s) supprimé(s)"

# -----------------------------------------------------------------------------
# 4. Résumé
# -----------------------------------------------------------------------------
log "✅ Backup terminé : ${BACKUP_NAME}"
ls -lah "${BACKUP_DIR}/${BACKUP_NAME}"* 2>/dev/null | head -10
