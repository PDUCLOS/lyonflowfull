#!/bin/bash
# =============================================================================
# scripts/backup-offsite.sh — Backup PostgreSQL -> OFFSITE (Google Drive)
# =============================================================================
# REGLE STRICTE : JAMAIS de backup persistant sur le VPS (51.83.159.224).
# Le VPS est full a 100% (96G/96G), tout backup local est impossible ET interdit.
# Ce script stream pg_dump -> gzip -> chiffrement -> offsite (Google Drive ou
# serveur SSH), sans rien ecrire sur le disque VPS.
#
# Strategie :
#   1. pg_dump en stream (pas de fichier temp)
#   2. gzip (compression ~5x)
#   3. gpg chiffrement (optionnel, recommande pour Google Drive)
#   4. Envoi :
#      a) Si GDRIVE_BACKUP_DEST defini : rclone rcat gdrive:DEST (Google Drive)
#      b) Sinon, si OFFSITE_SSH defini : ssh user@host 'cat > backup.dump.gz.gpg'
#      c) Sinon : ERREUR (pas de backup local autorise)
#
# Usage :
#   source .deploy.env
#   GDRIVE_BACKUP_DEST=lyonflow bash scripts/backup-offsite.sh
#   OU
#   OFFSITE_SSH=user@backup.example.com:~/lyonflow bash scripts/backup-offsite.sh
#
# Folder Google Drive dedie : backups/lyonflow (ID: 1TO-4OwTlFr5s3v9-apu1MbA5jZ-yfNDR)
# Configure rclone avec root_folder_id=1TO-4OwTlFr5s3v9-apu1MbA5jZ-yfNDR
# pour que tous les chemins soient relatifs a ce folder.
#
# Cron : systemd timer lyonflow-backup.timer (deja en place Sprint VPS-2)
# =============================================================================

set -euo pipefail

TIMESTAMP=$(date -u +%Y%m%d_%H%M%SZ)
BACKUP_NAME="lyonflow_${TIMESTAMP}_postgres.dump"
COMPRESSED="${BACKUP_NAME}.gz"
ENCRYPTED="${COMPRESSED}.gpg"

# -----------------------------------------------------------------------------
# Sanity checks
# -----------------------------------------------------------------------------
if [ -z "${GDRIVE_BACKUP_DEST:-}" ] && [ -z "${OFFSITE_SSH:-}" ]; then
    echo "❌ ERREUR : pas de destination offsite definie."
    echo "   Regle : JAMAIS de backup persistant sur le VPS (full 100%)."
    echo "   Options :"
    echo "     1. Google Drive : GDRIVE_BACKUP_DEST=backups/lyonflow"
    echo "     2. SSH serveur : OFFSITE_SSH=user@host:~/lyonflow"
    echo "   Setup rclone one-time (VPS) : rclone config  # interactive"
    exit 1
fi

# -----------------------------------------------------------------------------
# Verification espace disque VPS (regle de bon sens)
# -----------------------------------------------------------------------------
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 90 ]; then
    echo "⚠️  VPS disk a ${DISK_USAGE}% (regle : on ne devrait pas en etre la)"
    echo "   Mais le backup stream ne touche pas le disque, on continue."
fi

# -----------------------------------------------------------------------------
# 1. Build pg_dump en stream (dans un pipe, jamais sur disque)
# -----------------------------------------------------------------------------
echo "==[ 1/4 Stream pg_dump depuis Docker ]=="
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
    PG_DUMP_CMD="docker exec lyonflow-postgres pg_dump -U ${POSTGRES_USER:-lyonflow} -d ${POSTGRES_DB:-lyonflow} -Fc"
else
    echo "❌ Container lyonflow-postgres pas accessible"
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. Pipe : pg_dump | gzip | gpg | rclone rcat (ou ssh cat)
# -----------------------------------------------------------------------------
echo "==[ 2/4 Compression gzip ]=="
echo "==[ 3/4 Chiffrement gpg (optionnel) ]=="
GPG_RECIPIENT="${GPG_RECIPIENT:-patrice.noel.duclos@gmail.com}"
if command -v gpg &>/dev/null; then
    GPG_CMD="gpg --batch --yes --compress-algo=zlib --encrypt --recipient $GPG_RECIPIENT"
    FINAL_NAME="$ENCRYPTED"
else
    echo "⚠️  gpg non installe, backup non chiffre (OK si offsite = serveur prive)"
    GPG_CMD="cat"
    FINAL_NAME="$COMPRESSED"
fi

# -----------------------------------------------------------------------------
# 3. Envoi offsite (Google Drive via rclone OU SSH)
# -----------------------------------------------------------------------------
echo "==[ 4/4 Envoi offsite ]=="
START_TIME=$(date +%s)

if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
    # Mode Google Drive via rclone
    if ! command -v rclone &>/dev/null; then
        echo "❌ rclone non installe. Installation one-time :"
        echo "   curl https://rclone.org/install.sh | sudo bash"
        echo "   rclone config  # setup Google Drive OAuth"
        exit 1
    fi
    $PG_DUMP_CMD | gzip | $GPG_CMD | rclone rcat "gdrive:${GDRIVE_BACKUP_DEST}/${FINAL_NAME}" --progress
    DEST_LOG="Google Drive: gdrive:${GDRIVE_BACKUP_DEST}/${FINAL_NAME}"
elif [ -n "${OFFSITE_SSH:-}" ]; then
    # Mode SSH serveur backup
    $PG_DUMP_CMD | gzip | $GPG_CMD | ssh "$OFFSITE_SSH" "cat > '$FINAL_NAME'"
    DEST_LOG="SSH: $OFFSITE_SSH/$FINAL_NAME"
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
SIZE_HUMAN=$(du -h /opt/lyonflow/data 2>/dev/null | tail -1 | awk '{print $1}' || echo "?")

echo
echo "✅ Backup termine en ${DURATION}s"
echo "   Destination : $DEST_LOG"
echo "   DB source   : ${POSTGRES_USER:-lyonflow}@lyonflow (taille ~18 GB)"
echo "   Methode     : stream pipe (RIEN ecrit sur VPS)"
echo
echo "Pour restaurer :"
echo "   ssh user@backup-host"
echo "   rclone cat 'gdrive:${GDRIVE_BACKUP_DEST:-}/$FINAL_NAME' | gunzip | gpg -d | pg_restore -U lyonflow -d lyonflow"
echo
echo "REGLE RESPECTEE : aucun backup persistant sur le VPS."
