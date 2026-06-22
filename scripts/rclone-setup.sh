#!/usr/bin/env bash
# =============================================================================
# scripts/rclone-setup.sh — Configuration rclone pour backup offsite
# =============================================================================
# Aide interactive pour configurer rclone sur le VPS, requis par
# scripts/backup-offsite.sh (cf. lyonflow-backup.service).
#
# Deux modes supportés :
#   1. Google Drive via OAuth (recommandé compte Gmail perso)
#   2. Google Drive via Service Account (automation, sans OAuth)
#
# Usage :
#   sudo bash scripts/rclone-setup.sh
#
# Prérequis : rclone installé (sinon ce script l'install).
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()   { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*"; }
prompt() {
    local var_name="$1"; local prompt_text="$2"; local default="${3:-}"
    local reply
    if [ -n "$default" ]; then
        read -r -p "$prompt_text [$default]: " reply
        reply="${reply:-$default}"
    else
        read -r -p "$prompt_text: " reply
    fi
    eval "$var_name='$reply'"
}

# -----------------------------------------------------------------------------
# 0. Vérif root + install rclone si nécessaire
# -----------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    err "Ce script doit être lancé en root (sudo)."
    exit 1
fi

if ! command -v rclone &>/dev/null; then
    warn "rclone non installé. Installation..."
    curl -sSf https://rclone.org/install.sh | bash
    log "rclone installé : $(rclone version | head -1)"
fi

# -----------------------------------------------------------------------------
# 1. Choix du mode
# -----------------------------------------------------------------------------
echo
echo "=============================================================================="
echo " Configuration rclone pour LyonFlowFull backup offsite"
echo "=============================================================================="
echo
echo "Modes disponibles :"
echo "  1) Google Drive via OAuth           (recommandé compte Gmail perso)"
echo "  2) Google Drive via Service Account  (automation, JSON key GCP)"
echo "  3) Quitter"
echo
prompt CHOICE "Votre choix" "1"

RCLONE_CONF="/root/.config/rclone/rclone.conf"
mkdir -p "$(dirname "$RCLONE_CONF")"
touch "$RCLONE_CONF"
chmod 600 "$RCLONE_CONF"

case "$CHOICE" in
    # -------------------------------------------------------------------------
    # Mode 1 : OAuth interactif
    # -------------------------------------------------------------------------
    1)
        echo
        log "Mode OAuth sélectionné."
        echo
        echo "rclone va ouvrir un navigateur pour l'authentification Google."
        echo "Si le VPS n'a pas de navigateur (cas typique), rclone affiche"
        echo "une URL + un code. Ouvrez l'URL dans VOTRE navigateur local,"
        echo "entrez le code, puis revenez ici."
        echo
        read -r -p "Appuyez sur Entrée pour lancer rclone config..."
        rclone config create gdrive drive

        # Test
        log "Test de connexion..."
        rclone lsd gdrive: --max-depth 1 2>&1 | head -5
        log "OK : Google Drive accessible."

        # Dossier destination
        prompt GDRIVE_BACKUP_DEST "Dossier destination sur Google Drive" "backups/lyonflow"
        ;;

    # -------------------------------------------------------------------------
    # Mode 2 : Service Account
    # -------------------------------------------------------------------------
    2)
        echo
        log "Mode Service Account sélectionné."
        echo
        echo "Prérequis :"
        echo "  1. Créer un Service Account dans GCP Console :"
        echo "     https://console.cloud.google.com/iam-admin/serviceaccounts"
        echo "  2. Télécharger la clé JSON"
        echo "  3. Partager le dossier Google Drive cible avec l'email du SA"
        echo "     (ex: lyonflow-backup@mon-projet.iam.gserviceaccount.com)"
        echo

        prompt SA_KEY_PATH "Chemin absolu vers le fichier JSON du Service Account" ""

        if [ ! -f "$SA_KEY_PATH" ]; then
            err "Fichier $SA_KEY_PATH introuvable."
            exit 1
        fi

        # Stocker la clé de manière sécurisée
        SA_KEY_DEST="/root/.config/rclone/sa-key.json"
        cp "$SA_KEY_PATH" "$SA_KEY_DEST"
        chmod 600 "$SA_KEY_DEST"

        # Créer le remote gdrive
        rclone config create gdrive drive service_account_file "$SA_KEY_DEST"

        log "Test de connexion..."
        rclone lsd gdrive: --max-depth 1 2>&1 | head -5
        log "OK : Google Drive accessible via Service Account."

        prompt GDRIVE_BACKUP_DEST "Dossier destination sur Google Drive" "backups/lyonflow"
        ;;

    3)
        log "Annulé."
        exit 0
        ;;

    *)
        err "Choix invalide : $CHOICE"
        exit 1
        ;;
esac

# -----------------------------------------------------------------------------
# 2. Mise à jour .backup-offsite.conf
# -----------------------------------------------------------------------------
CONF_FILE="/opt/lyonflow/.backup-offsite.conf"
if [ ! -f "$CONF_FILE" ]; then
    err "Fichier $CONF_FILE introuvable. Avez-vous installé les systemd units ?"
    err "Lancez : cd /opt/lyonflow && sudo make install-systemd"
    exit 1
fi

chmod 600 "$CONF_FILE"

# Activer GDRIVE_BACKUP_DEST (décommenter ou remplacer)
if grep -qE '^#?\s*GDRIVE_BACKUP_DEST=' "$CONF_FILE"; then
    sed -i "s|^#\?\s*GDRIVE_BACKUP_DEST=.*|GDRIVE_BACKUP_DEST=$GDRIVE_BACKUP_DEST|" "$CONF_FILE"
else
    echo "GDRIVE_BACKUP_DEST=$GDRIVE_BACKUP_DEST" >> "$CONF_FILE"
fi

log "Configuration mise à jour dans $CONF_FILE"
echo
echo "Contenu actuel :"
echo "----------------"
grep -v '^#' "$CONF_FILE" | grep -v '^$' | sed 's/^/  /'
echo

# -----------------------------------------------------------------------------
# 3. Test final : dry-run du backup-offsite
# -----------------------------------------------------------------------------
log "Test du backup-offsite (dry-run via container postgres check)..."
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'lyonflow-postgres'; then
    log "Container lyonflow-postgres détecté, test config..."
    sudo -u ubuntu bash -c "source $CONF_FILE && docker exec lyonflow-postgres pg_dump -U \${POSTGRES_USER:-lyonflow} -d \${POSTGRES_DB:-lyonflow} --schema-only | head -3" 2>&1 | head -3
fi

echo
log "============================================================================="
log " Configuration terminée."
log "============================================================================="
echo
echo "Prochaines étapes :"
echo "  1. Vérifier que le timer tourne :"
echo "     sudo systemctl list-timers | grep lyonflow"
echo "  2. Forcer un run de test :"
echo "     sudo systemctl start lyonflow-backup.service"
echo "  3. Suivre les logs :"
echo "     sudo journalctl -u lyonflow-backup.service -f"
echo
echo "Le backup automatique tournera demain à ~03:00 UTC."
echo
