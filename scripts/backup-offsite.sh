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
# Cron : systemd timer lyonflow-backup.timer (active 2026-06-22 — Sprint 22 ops cleanup VPS).
# Units versionnees dans deploy/systemd/ + Makefile cible install-systemd.
# Setup destination offsite : sudo bash scripts/rclone-setup.sh
#
# Sprint 26 (2026-09-22) — durcissement apres incident du 2026-09-22 :
#   - Preflight : la destination (rclone ou ssh) est testee AVANT de lancer
#     pg_dump. Avant ce fix, un rclone casse faisait mourir le pipe mais le
#     pg_dump lance via `docker exec` survivait ~1 h dans le container
#     (orphelin, AccessShareLock sur toutes les tables → REFRESH MV et
#     migrations bloques, IO sature).
#   - Trap EXIT : termine le backend pg_dump (application_name
#     lyonflow-backup) si le script sort en erreur.
#   - Purge automatique des anciens backups sur la destination, bornee par
#     la taille du disque cible :
#       BACKUP_RETENTION_DAYS   (defaut 14)  : supprime les backups plus vieux
#       BACKUP_KEEP_MIN         (defaut 2)   : garde toujours les N plus recents
#       BACKUP_MAX_TOTAL_GB     (defaut auto): plafond cumule. Si absent, derive
#                                de `rclone about` : BACKUP_MAX_QUOTA_PCT (defaut
#                                30) % du quota total de la destination
#                                (fallback 10 Go si quota inconnu / mode SSH :
#                                df du repertoire distant).
#     Ordre : les plus vieux partent en premier, jamais sous BACKUP_KEEP_MIN.
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
    echo "ERREUR : pas de destination offsite definie."
    echo "   Regle : JAMAIS de backup persistant sur le VPS (full 100%)."
    echo "   Options :"
    echo "     1. Google Drive : GDRIVE_BACKUP_DEST=backups/lyonflow"
    echo "     2. SSH serveur : OFFSITE_SSH=user@host:~/lyonflow"
    echo "   Setup rclone one-time (VPS) : rclone config  # interactive"
    exit 1
fi

BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_KEEP_MIN="${BACKUP_KEEP_MIN:-2}"
BACKUP_MAX_QUOTA_PCT="${BACKUP_MAX_QUOTA_PCT:-30}"
RCLONE_REMOTE="gdrive:${GDRIVE_BACKUP_DEST:-}"
PG_APP_NAME="lyonflow-backup"

# -----------------------------------------------------------------------------
# Preflight destination (Sprint 26) — AVANT pg_dump, sinon pg_dump orphelin
# -----------------------------------------------------------------------------
echo "==[ 0/5 Preflight destination ]=="
if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
    if ! command -v rclone &>/dev/null; then
        echo "ERREUR : rclone non installe (curl https://rclone.org/install.sh | sudo bash)"
        exit 1
    fi
    # Config rclone illisible = typiquement reecrite par un `sudo rclone` (refresh
    # du token OAuth → fichier root:ubuntu 600). Incident 2026-09-24.
    if [ -n "${RCLONE_CONFIG:-}" ] && [ ! -r "$RCLONE_CONFIG" ]; then
        echo "ERREUR : $RCLONE_CONFIG illisible par $(id -un) (proprietaire : $(stat -c %U "$RCLONE_CONFIG" 2>/dev/null))."
        echo "   Cause probable : rclone lance avec sudo. Fix : sudo chown ubuntu:ubuntu $RCLONE_CONFIG"
        exit 1
    fi
    # mkdir idempotent : cree le dossier si absent, echoue si remote/OAuth KO
    if ! rclone mkdir "$RCLONE_REMOTE" 2>&1 | sed 's/^/   rclone: /'; then
        echo "ERREUR : destination '$RCLONE_REMOTE' inaccessible (config rclone / OAuth ?)."
        echo "   Verifier : rclone lsd gdrive:   (RCLONE_CONFIG=${RCLONE_CONFIG:-~/.config/rclone/rclone.conf})"
        exit 1
    fi
    # rclone mkdir ne renvoie pas toujours un code d'erreur via le pipe sed : re-test explicite
    if ! rclone lsd "$RCLONE_REMOTE" >/dev/null 2>&1; then
        echo "ERREUR : destination '$RCLONE_REMOTE' inaccessible (config rclone / OAuth ?)."
        exit 1
    fi
    echo "   OK : $RCLONE_REMOTE accessible"
elif [ -n "${OFFSITE_SSH:-}" ]; then
    SSH_HOST="${OFFSITE_SSH%%:*}"
    SSH_DIR="${OFFSITE_SSH#*:}"
    if ! ssh -o BatchMode=yes -o ConnectTimeout=15 "$SSH_HOST" "mkdir -p '$SSH_DIR'"; then
        echo "ERREUR : serveur SSH '$SSH_HOST' inaccessible ou repertoire '$SSH_DIR' non creable."
        exit 1
    fi
    echo "   OK : $OFFSITE_SSH accessible"
fi

# Trap : si le pipe casse (rclone/ssh), le pg_dump lance par `docker exec`
# survit dans le container. On le termine par son application_name.
cleanup_pg_dump() {
    local rc=$?
    if [ "$rc" -ne 0 ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
        docker exec lyonflow-postgres psql -U "${POSTGRES_USER:-lyonflow}" -d "${POSTGRES_DB:-lyonflow}" -tAc \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='${PG_APP_NAME}'" \
            >/dev/null 2>&1 || true
        echo "Backup en erreur (rc=$rc) : backend pg_dump '${PG_APP_NAME}' termine."
    fi
    exit "$rc"
}
trap cleanup_pg_dump EXIT

# -----------------------------------------------------------------------------
# Verification espace disque VPS (regle de bon sens)
# -----------------------------------------------------------------------------
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 90 ]; then
    echo "VPS disk a ${DISK_USAGE}% (regle : on ne devrait pas en etre la)"
    echo "   Mais le backup stream ne touche pas le disque, on continue."
fi

# -----------------------------------------------------------------------------
# 1. Build pg_dump en stream (dans un pipe, jamais sur disque)
# -----------------------------------------------------------------------------
echo "==[ 1/5 Stream pg_dump depuis Docker ]=="
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
    PG_DUMP_CMD="docker exec -e PGAPPNAME=${PG_APP_NAME} lyonflow-postgres pg_dump -U ${POSTGRES_USER:-lyonflow} -d ${POSTGRES_DB:-lyonflow} -Fc"
else
    echo "Container lyonflow-postgres pas accessible"
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. Pipe : pg_dump | gzip | gpg | rclone rcat (ou ssh cat)
# -----------------------------------------------------------------------------
echo "==[ 2/5 Compression gzip ]=="
echo "==[ 3/5 Chiffrement gpg (optionnel) ]=="
GPG_RECIPIENT="${GPG_RECIPIENT:-patrice.noel.duclos@gmail.com}"
if [ "${BACKUP_NO_ENCRYPT:-0}" = "1" ]; then
    echo "BACKUP_NO_ENCRYPT=1 : backup non chiffre (voulu explicitement)"
    GPG_CMD="cat"
    FINAL_NAME="$COMPRESSED"
elif command -v gpg &>/dev/null; then
    GPG_CMD="gpg --batch --yes --compress-algo=zlib --encrypt --recipient $GPG_RECIPIENT"
    FINAL_NAME="$ENCRYPTED"
else
    echo "gpg non installe, backup non chiffre (OK si offsite = serveur prive)"
    GPG_CMD="cat"
    FINAL_NAME="$COMPRESSED"
fi

# -----------------------------------------------------------------------------
# 3. Envoi offsite (Google Drive via rclone OU SSH)
# -----------------------------------------------------------------------------
echo "==[ 4/5 Envoi offsite ]=="
START_TIME=$(date +%s)

if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
    # Mode Google Drive via rclone
    if ! command -v rclone &>/dev/null; then
        echo "rclone non installe. Installation one-time :"
        echo "   curl https://rclone.org/install.sh | sudo bash"
        echo "   rclone config  # setup Google Drive OAuth"
        exit 1
    fi
    # Sprint 26 (2026-09-25) : backup du 25/09 refusé en fin d'upload par Google
    # (403 rateLimitExceeded, quota par minute du client OAuth partagé de rclone).
    # Blocs de 128 Mo (defaut 8 Mo) : ~30 requetes au lieu de ~490 pour 3,8 Go,
    # chaque bloc est bufferise en RAM donc re-essayable (--low-level-retries).
    # Sous systemd (pas de TTY), --progress ecrit une ligne toutes les 500 ms
    # dans journald et noie l'erreur dans l'alerte Telegram : stats sur 1 ligne / 5 min.
    if [ -t 1 ]; then RCLONE_STATS=(--progress); else RCLONE_STATS=(--stats 5m --stats-one-line); fi
    $PG_DUMP_CMD | gzip | $GPG_CMD | rclone rcat "gdrive:${GDRIVE_BACKUP_DEST}/${FINAL_NAME}" \
        --drive-chunk-size 128M --low-level-retries 20 "${RCLONE_STATS[@]}"
    DEST_LOG="Google Drive: gdrive:${GDRIVE_BACKUP_DEST}/${FINAL_NAME}"
elif [ -n "${OFFSITE_SSH:-}" ]; then
    # Mode SSH serveur backup
    $PG_DUMP_CMD | gzip | $GPG_CMD | ssh "$OFFSITE_SSH" "cat > '$FINAL_NAME'"
    DEST_LOG="SSH: $OFFSITE_SSH/$FINAL_NAME"
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# -----------------------------------------------------------------------------
# 5. Purge automatique des anciens backups (Sprint 26)
# -----------------------------------------------------------------------------
echo "==[ 5/5 Purge anciens backups ]=="
GB=$((1024 * 1024 * 1024))

# Plafond cumule en octets : BACKUP_MAX_TOTAL_GB explicite, sinon % du quota
# total de la destination, sinon 10 Go.
resolve_cap_bytes() {
    if [ -n "${BACKUP_MAX_TOTAL_GB:-}" ]; then
        echo $(( BACKUP_MAX_TOTAL_GB * GB )); return
    fi
    local total=""
    if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
        total=$(rclone about "gdrive:" --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("total") or "")' 2>/dev/null || true)
    elif [ -n "${OFFSITE_SSH:-}" ]; then
        total=$(ssh -o BatchMode=yes "$SSH_HOST" "df -B1 --output=size '$SSH_DIR' | tail -1" 2>/dev/null | tr -d ' ' || true)
    fi
    if [ -n "$total" ] && [ "$total" -gt 0 ] 2>/dev/null; then
        echo $(( total * BACKUP_MAX_QUOTA_PCT / 100 ))
    else
        echo $(( 10 * GB ))
    fi
}
CAP_BYTES=$(resolve_cap_bytes)

# Liste "epoch|size|name" triee du plus recent au plus vieux
list_backups() {
    if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
        rclone lsjson "$RCLONE_REMOTE" --files-only 2>/dev/null | python3 -c '
import sys, json, datetime
rows = []
for f in json.load(sys.stdin):
    if not f["Name"].startswith("lyonflow_"):
        continue
    ts = datetime.datetime.fromisoformat(f["ModTime"].replace("Z", "+00:00")).timestamp()
    rows.append((int(ts), int(f["Size"]), f["Name"]))
for r in sorted(rows, reverse=True):
    print("%d|%d|%s" % r)'
    else
        ssh -o BatchMode=yes "$SSH_HOST" "cd '$SSH_DIR' && find . -maxdepth 1 -name 'lyonflow_*' -printf '%T@|%s|%f\n'" 2>/dev/null \
            | awk -F'|' '{printf "%d|%d|%s\n", $1, $2, $3}' | sort -t'|' -k1,1nr
    fi
}
delete_backup() {
    if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
        rclone deletefile "${RCLONE_REMOTE}/$1"
    else
        ssh -o BatchMode=yes "$SSH_HOST" "rm -f '$SSH_DIR/$1'"
    fi
}

NOW_EPOCH=$(date +%s)
CUTOFF_EPOCH=$(( NOW_EPOCH - BACKUP_RETENTION_DAYS * 86400 ))
BACKUPS=$(list_backups)
TOTAL_BYTES=0
N_TOTAL=0
while IFS='|' read -r ts size name; do
    [ -z "$name" ] && continue
    TOTAL_BYTES=$(( TOTAL_BYTES + size )); N_TOTAL=$(( N_TOTAL + 1 ))
done <<< "$BACKUPS"
echo "   ${N_TOTAL} backup(s), $(( TOTAL_BYTES / 1024 / 1024 )) Mo cumules, plafond $(( CAP_BYTES / 1024 / 1024 )) Mo, retention ${BACKUP_RETENTION_DAYS} j, keep_min ${BACKUP_KEEP_MIN}"

# Parcours du plus vieux au plus recent : on supprime tant que (trop vieux OU
# au-dessus du plafond) ET qu'il reste plus de BACKUP_KEEP_MIN backups.
N_KEPT=$N_TOTAL
N_DELETED=0
while IFS='|' read -r ts size name; do
    [ -z "$name" ] && continue
    [ "$N_KEPT" -le "$BACKUP_KEEP_MIN" ] && break
    if [ "$ts" -lt "$CUTOFF_EPOCH" ] || [ "$TOTAL_BYTES" -gt "$CAP_BYTES" ]; then
        reason="trop vieux"; [ "$ts" -ge "$CUTOFF_EPOCH" ] && reason="plafond taille"
        if delete_backup "$name"; then
            echo "   supprime : $name ($(( size / 1024 / 1024 )) Mo, $reason)"
            TOTAL_BYTES=$(( TOTAL_BYTES - size )); N_KEPT=$(( N_KEPT - 1 )); N_DELETED=$(( N_DELETED + 1 ))
        else
            echo "   WARN : suppression echouee pour $name"
        fi
    fi
done <<< "$(echo "$BACKUPS" | sort -t'|' -k1,1n)"
echo "   purge : ${N_DELETED} supprime(s), ${N_KEPT} conserve(s), $(( TOTAL_BYTES / 1024 / 1024 )) Mo restants"
if [ "$TOTAL_BYTES" -gt "$CAP_BYTES" ]; then
    echo "   WARN : toujours au-dessus du plafond apres purge (keep_min=${BACKUP_KEEP_MIN} protege les derniers backups)."
    echo "          Augmenter le quota destination ou baisser BACKUP_KEEP_MIN."
fi
DB_SIZE=$(docker exec lyonflow-postgres psql -U "${POSTGRES_USER:-lyonflow}" -d "${POSTGRES_DB:-lyonflow}" -tAc \
    "SELECT pg_size_pretty(pg_database_size(current_database()))" 2>/dev/null || echo "?")
if [ "$GPG_CMD" = "cat" ]; then DECRYPT_HINT=""; else DECRYPT_HINT=" | gpg -d"; fi

echo
echo "Backup termine en ${DURATION}s"
echo "   Destination : $DEST_LOG"
echo "   DB source   : ${POSTGRES_USER:-lyonflow}@${POSTGRES_DB:-lyonflow} (${DB_SIZE})"
echo "   Methode     : stream pipe (RIEN ecrit sur VPS)"
echo
echo "Pour restaurer :"
if [ -n "${GDRIVE_BACKUP_DEST:-}" ]; then
    echo "   rclone cat 'gdrive:${GDRIVE_BACKUP_DEST}/$FINAL_NAME' | gunzip${DECRYPT_HINT} | pg_restore -U lyonflow -d lyonflow"
else
    echo "   ssh $SSH_HOST cat '$SSH_DIR/$FINAL_NAME' | gunzip${DECRYPT_HINT} | pg_restore -U lyonflow -d lyonflow"
fi
echo
echo "REGLE RESPECTEE : aucun backup persistant sur le VPS."
