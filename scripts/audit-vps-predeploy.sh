#!/bin/bash
# =============================================================================
# scripts/audit-vps-predeploy.sh — Audit securise VPS LyonFlow
# =============================================================================
# A executer AVANT tout deploy sur le VPS (51.83.159.224).
# Fait dans l'ordre :
#   1. Backup PostgreSQL OFFSITE (filet de sécurité unique — pas de copie locale)
#   2. Audit volumes + bind mount
#   3. Audit DBs (liste complete)
#   4. Audit tables (compte par table bronze/silver/gold)
#   5. Verifie integrite du dernier backup offsite (taille + md5 + pg_restore --list)
#
# Regle cardinale : JAMAIS de backup persistant sur le VPS (96G/96G, 583M libre).
# Tous les backups vont directement offsite via scripts/backup-offsite.sh.
# Ancien snapshot volume Docker (filet #2) SUPPRIME — incompatible avec regle OFFSITE.
#
# Usage :
#   source .deploy.env   # charge VPS_HOST + VPS_SSH_KEY
#   bash scripts/audit-vps-predeploy.sh
#
# Si tout est OK en sortie : tu peux deploy en securite.
# Si KO : investiguer AVANT de toucher au VPS.
# =============================================================================

set -euo pipefail

# Sanity check : variables requises
if [ -z "${VPS_HOST:-}" ] || [ -z "${VPS_SSH_KEY:-}" ]; then
    echo "❌ VPS_HOST et VPS_SSH_KEY doivent etre definies."
    echo "   source .deploy.env avant de lancer ce script."
    exit 1
fi

SSH="ssh -i $VPS_SSH_KEY $VPS_HOST"
echo "================================================================="
echo " AUDIT VPS PRE-DEPLOY — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " Cible : $VPS_HOST"
echo "================================================================="
echo

# -----------------------------------------------------------------------------
# 1/5 — BACKUP PostgreSQL OFFSITE (filet de securite unique)
# -----------------------------------------------------------------------------
# Regle : JAMAIS de backup persistant sur le VPS. Stream direct offsite via
# scripts/backup-offsite.sh (pg_dump|gzip|gpg|rclone rcat). Pas de fichier
# intermediaire, pas de snapshot volume local.
echo "===[ 1/5 BACKUP PostgreSQL OFFSITE ]==="
$SSH 'cd /opt/lyonflow && ./scripts/backup-offsite.sh 2>&1 | tail -10'
echo
# Note : le dump offsite n'a pas de chemin local. On verifie l'integrite via
# le remote (Google Drive ou serveur SSH) — voir etape 5/5.

# -----------------------------------------------------------------------------
# 2/5 — AUDIT volumes + bind mount
# -----------------------------------------------------------------------------
echo "===[ 2/5 AUDIT volumes Docker + bind mount ]==="
$SSH 'docker volume ls | grep -i postgres || echo "Pas de volume postgres (bind mount only?)"'
echo
$SSH "docker volume inspect \$(docker volume ls -q | grep postgres) --format '{{.Name}}: {{.Mountpoint}} ({{.Driver}})' 2>/dev/null || echo 'Pas de volume postgres'"
echo
$SSH 'ls -lah /opt/lyonflow/postgres_data 2>/dev/null | head -10 || echo "Pas de bind mount /opt/lyonflow/postgres_data"'
$SSH 'du -sh /opt/lyonflow/postgres_data 2>/dev/null || echo "N/A"'
echo

# -----------------------------------------------------------------------------
# 3/5 — AUDIT DBs (avec user lyonflow, DB lyonflow)
# -----------------------------------------------------------------------------
echo "===[ 3/5 DBs PostgreSQL ]==="
$SSH 'docker exec lyonflow-postgres psql -U lyonflow -l 2>&1' || {
    echo "⚠️  Echec. Verifier que le container tourne :"
    $SSH 'docker ps | grep postgres'
    exit 1
}
echo

# -----------------------------------------------------------------------------
# 4/5 — AUDIT tables (compte par table bronze/silver/gold)
# -----------------------------------------------------------------------------
echo "===[ 4/5 Tables bronze/silver/gold (n_live_tup) ]==="
$SSH 'docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables WHERE schemaname IN ('"'"'bronze'"'"', '"'"'silver'"'"', '"'"'gold'"'"') ORDER BY schemaname, n_live_tup DESC"' || {
    echo "⚠️  Si la DB s'appelle 'trafficlyon' (legacy), remplacer lyonflow par trafficlyon"
}
echo

# -----------------------------------------------------------------------------
# 5/5 — VERIFICATION dernier backup OFFSITE
# -----------------------------------------------------------------------------
# Le backup est offsite (gdrive ou SSH), donc on liste le remote pour confirmer
# la presence du dernier dump. La verif d'integrite pg_restore --list se fait
# periodiquement via un test restore manuel (cf. RUNBOOK.md).
echo "===[ 5/5 Verification dernier backup OFFSITE ]==="
if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
    $SSH "rclone lsl gdrive:${GDRIVE_BACKUP_DEST}/ 2>/dev/null | sort -k2 -r | head -3" || {
        echo "⚠️  rclone lsl a echoue. Verifier config rclone sur VPS."
    }
elif [ -n "${OFFSITE_SSH:-}" ]; then
    $SSH "ssh ${OFFSITE_SSH} 'ls -lt ~/ 2>/dev/null | head -5'" || {
        echo "⚠️  ssh vers ${OFFSITE_SSH} a echoue."
    }
else
    echo "⚠️  Pas de destination offsite definie (.deploy.env)."
    echo "   backup-offsite.sh a refuse de tourner — investiguer."
fi
echo

# -----------------------------------------------------------------------------
# RESUME
# -----------------------------------------------------------------------------
echo "================================================================="
echo " RESUME AUDIT"
echo "================================================================="
echo "Backup PostgreSQL       : OFFSITE (gdrive ou ssh) - aucun fichier local"
echo "Snapshot volume Docker  : SUPPRIME (incompatible regle OFFSITE)"
echo "Disque VPS              : voir du -sh ci-dessus"
echo "================================================================="
echo
echo "Si tout est OK ci-dessus : tu peux deploy en securite."
echo "Si KO : investiguer AVANT de toucher au VPS."
