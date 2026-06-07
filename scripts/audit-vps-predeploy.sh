#!/bin/bash
# =============================================================================
# scripts/audit-vps-predeploy.sh — Audit securise VPS LyonFlowFull
# =============================================================================
# A executer AVANT tout deploy sur le VPS (51.83.159.224).
# Fait dans l'ordre :
#   1. Backup PostgreSQL (filet de sécurité #1)
#   2. Snapshot volume Docker (filet de sécurité #2, point-in-time)
#   3. Audit volumes + bind mount
#   4. Audit DBs (liste complete)
#   5. Audit tables (compte par table bronze/silver/gold)
#   6. Verifie integrite du backup (taille + md5 + pg_restore --list)
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
# 1/6 — BACKUP PostgreSQL (filet de securite #1)
# -----------------------------------------------------------------------------
echo "===[ 1/6 BACKUP PostgreSQL ]==="
$SSH 'cd /opt/lyonflow && ./scripts/backup.sh 2>&1 | tail -5'
BACKUP_FILE=$($SSH 'ls -t /opt/lyonflow/backups/lyonflow_*_postgres.dump 2>/dev/null | head -1')
if [ -z "$BACKUP_FILE" ]; then
    echo "❌ Aucun backup trouve. Arret."
    exit 1
fi
echo "Dernier backup : $BACKUP_FILE"
$SSH "ls -lah $BACKUP_FILE"
$SSH "md5sum $BACKUP_FILE"
echo

# -----------------------------------------------------------------------------
# 2/6 — SNAPSHOT volume Docker (filet de securite #2, point-in-time)
# -----------------------------------------------------------------------------
echo "===[ 2/6 SNAPSHOT volume Docker (tar.gz du volume postgres) ]==="
SNAPSHOT_NAME="snapshot_volume_$(date +%Y%m%d_%H%M%S).tar.gz"
$SSH "docker run --rm \
    -v lyonflow_postgres_data:/data:ro \
    -v /opt/lyonflow/backups:/backup \
    alpine tar czf /backup/$SNAPSHOT_NAME -C /data . 2>&1 | tail -3"
$SSH "ls -lah /opt/lyonflow/backups/$SNAPSHOT_NAME"
echo

# -----------------------------------------------------------------------------
# 3/6 — AUDIT volumes + bind mount
# -----------------------------------------------------------------------------
echo "===[ 3/6 AUDIT volumes Docker + bind mount ]==="
$SSH 'docker volume ls | grep -i postgres || echo "Pas de volume postgres (bind mount only?)"'
echo
$SSH "docker volume inspect \$(docker volume ls -q | grep postgres) --format '{{.Name}}: {{.Mountpoint}} ({{.Driver}})' 2>/dev/null || echo 'Pas de volume postgres'"
echo
$SSH 'ls -lah /opt/lyonflow/postgres_data 2>/dev/null | head -10 || echo "Pas de bind mount /opt/lyonflow/postgres_data"'
$SSH 'du -sh /opt/lyonflow/postgres_data 2>/dev/null || echo "N/A"'
echo

# -----------------------------------------------------------------------------
# 4/6 — AUDIT DBs (avec user lyonflow, DB lyonflow)
# -----------------------------------------------------------------------------
echo "===[ 4/6 DBs PostgreSQL ]==="
$SSH 'docker exec lyonflow-postgres psql -U lyonflow -l 2>&1' || {
    echo "⚠️  Echec. Verifier que le container tourne :"
    $SSH 'docker ps | grep postgres'
    exit 1
}
echo

# -----------------------------------------------------------------------------
# 5/6 — AUDIT tables (compte par table bronze/silver/gold)
# -----------------------------------------------------------------------------
echo "===[ 5/6 Tables bronze/silver/gold (n_live_tup) ]==="
$SSH 'docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables WHERE schemaname IN ('"'"'bronze'"'"', '"'"'silver'"'"', '"'"'gold'"'"') ORDER BY schemaname, n_live_tup DESC"' || {
    echo "⚠️  Si la DB s'appelle 'trafficlyon' (legacy), remplacer lyonflow par trafficlyon"
}
echo

# -----------------------------------------------------------------------------
# 6/6 — VERIFICATION INTEGRITE backup
# -----------------------------------------------------------------------------
echo "===[ 6/6 Verification integrite backup ]==="
echo "Taille du dump :"
$SSH "du -h $BACKUP_FILE"
echo
echo "MD5 (a conserver pour comparaison future) :"
$SSH "md5sum $BACKUP_FILE"
echo
echo "Test lecture dump (pg_restore --list, 10 premieres entrees) :"
$SSH "pg_restore --list $BACKUP_FILE 2>&1 | head -10"
echo

# -----------------------------------------------------------------------------
# RESUME
# -----------------------------------------------------------------------------
echo "================================================================="
echo " RESUME AUDIT"
echo "================================================================="
echo "Backup PostgreSQL       : $BACKUP_FILE"
echo "Snapshot volume Docker  : /opt/lyonflow/backups/$SNAPSHOT_NAME"
echo "================================================================="
echo
echo "Si tout est OK ci-dessus : tu peux deploy en securite."
echo "Si KO : investiguer AVANT de toucher au VPS."
