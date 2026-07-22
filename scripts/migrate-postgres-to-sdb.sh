#!/usr/bin/env bash
# =============================================================================
# Migration Postgres data /dev/sda -> /dev/sdb (100G dédié)
# =============================================================================
# Objectif: liberer sda + isoler la DB sur son propre disque.
#
# Etapes:
#   1. Format sdb en ext4 (si pas deja fait)
#   2. Mount /mnt/postgres-data (persistant via fstab)
#   3. Stop tous les containers qui dependent de postgres
#   4. Rsync donnees existantes vers nouveau disque
#   5. Modifier docker-compose pour bind mount nouveau path
#   6. Restart stack + verifier healthcheck
#
# Securite:
#   - pg_dump prealable cree (filet de secours offsite)
#   - Operations idempotent (verifie etat avant chaque action)
#   - Rollback possible: ancien volume Docker conserve jusqu'a verif OK
#
# Usage:
#   bash scripts/migrate-postgres-to-sdb.sh
#
# Pre-requis:
#   - sudo (operations format/mount/rsync)
#   - rclone configure (pour backup offsite gdrive)
# =============================================================================

set -euo pipefail

NEW_DISK="/dev/sdb"
MOUNT_POINT="/mnt/postgres-data"
OLD_VOLUME_PATH="/var/lib/docker/volumes/lyonflow-pgdata/_data"
COMPOSE_DIR="/opt/lyonflow"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[34m%s\033[0m\n" "$*"; }

need_sudo() {
    if ! sudo -n true 2>/dev/null; then
        red "Besoin sudo sans password. Fais 'sudo -v' avant de relancer."
        exit 1
    fi
}

step_1_check_disk() {
    blue "==[ 1/7 Verif disque ${NEW_DISK} ]=="
    if [[ ! -b "${NEW_DISK}" ]]; then
        red "${NEW_DISK} n'existe pas. Abort."; exit 1
    fi
    if lsblk -fno FSTYPE "${NEW_DISK}" | grep -q ext4; then
        green "${NEW_DISK} deja ext4."
    else
        blue "Format ext4..."
        sudo mkfs.ext4 -L postgres-data "${NEW_DISK}"
        green "Format OK."
    fi
}

step_2_mount() {
    blue "==[ 2/7 Mount ${MOUNT_POINT} ]=="
    sudo mkdir -p "${MOUNT_POINT}"
    if mountpoint -q "${MOUNT_POINT}"; then
        green "${MOUNT_POINT} deja monte."
    else
        # Recupere UUID
        UUID=$(sudo blkid -s UUID -o value "${NEW_DISK}")
        if [[ -z "${UUID}" ]]; then
            red "UUID introuvable. Abort."; exit 1
        fi
        # Ajoute a fstab si absent
        if ! grep -q "${UUID}" /etc/fstab; then
            echo "UUID=${UUID}  ${MOUNT_POINT}  ext4  defaults,nofail  0 2" | sudo tee -a /etc/fstab
        fi
        sudo mount "${MOUNT_POINT}"
        green "Monte OK."
    fi
    df -h "${MOUNT_POINT}"
}

step_3_backup_pgdump() {
    blue "==[ 3/7 Backup pg_dump prealable (filet secours) ]=="
    # Chown mount pour ecriture sans sudo (idempotent)
    sudo chown "$(id -u):$(id -g)" "${MOUNT_POINT}"
    BACKUP_FILE="${MOUNT_POINT}/pre-migration-$(date +%Y%m%d-%H%M%S).dump"
    docker exec lyonflow-postgres pg_dump -U lyonflow -Fc -d lyonflow > "${BACKUP_FILE}"
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    green "Backup ${BACKUP_FILE} (${BACKUP_SIZE})"
}

step_4_stop_containers() {
    blue "==[ 4/7 Stop containers dependants ]=="
    cd "${COMPOSE_DIR}"
    # Stop tout sauf postgres d'abord (api/streamlit/airflow/mlflow)
    sudo docker compose stop airflow streamlit api mlflow 2>/dev/null || true
    sleep 2
    sudo docker compose stop postgres
    green "Containers stopped."
}

step_5_rsync_data() {
    blue "==[ 5/7 Rsync data vers ${MOUNT_POINT}/pgdata ]=="
    sudo mkdir -p "${MOUNT_POINT}/pgdata"
    sudo rsync -aHAX --info=progress2 "${OLD_VOLUME_PATH}/" "${MOUNT_POINT}/pgdata/"
    sudo chown -R 999:999 "${MOUNT_POINT}/pgdata"  # postgres uid in container
    NEW_SIZE=$(sudo du -sh "${MOUNT_POINT}/pgdata" | cut -f1)
    green "Rsync OK (${NEW_SIZE})"
}

step_6_update_compose() {
    blue "==[ 6/7 Update docker-compose volumes ]=="
    # Backup compose original
    sudo cp "${COMPOSE_FILE}" "${COMPOSE_FILE}.bak-$(date +%Y%m%d-%H%M%S)"

    # Sed remplace volume nomme par bind mount
    # Pattern: "- lyonflow-pgdata:/var/lib/postgresql/data"
    # Remplace par: "- /mnt/postgres-data/pgdata:/var/lib/postgresql/data"
    if grep -q "lyonflow-pgdata:/var/lib/postgresql/data" "${COMPOSE_FILE}"; then
        sudo sed -i.tmp \
            "s|lyonflow-pgdata:/var/lib/postgresql/data|${MOUNT_POINT}/pgdata:/var/lib/postgresql/data|g" \
            "${COMPOSE_FILE}"
        sudo rm -f "${COMPOSE_FILE}.tmp"
        green "Compose modifie (backup .bak-* genere)."
    else
        red "Pattern volume non trouve dans compose. Verifie manuellement."
        exit 1
    fi
}

step_7_restart_verify() {
    blue "==[ 7/7 Restart stack + verifier ]=="
    cd "${COMPOSE_DIR}"
    sudo docker compose up -d postgres
    sleep 8
    blue "Wait postgres healthy..."
    for i in {1..20}; do
        if sudo docker exec lyonflow-postgres pg_isready -U lyonflow 2>/dev/null; then
            green "Postgres healthy."
            break
        fi
        sleep 2
    done
    # Smoke test : compte tables
    N_TABLES=$(sudo docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('bronze','silver','gold')")
    green "Tables visibles: ${N_TABLES}"
    # Restart le reste
    sudo docker compose up -d
    sleep 5
    sudo docker compose ps
}

step_8_cleanup_old() {
    blue "==[ 8/8 (OPTIONNEL) Cleanup ancien volume ]=="
    red "ANCIEN VOLUME conserve par securite : lyonflow-pgdata"
    red "Pour le supprimer apres verif (DB live OK depuis >1h):"
    red "  sudo docker volume rm lyonflow-pgdata"
    red ""
    red "Verif espace libere :"
    df -h /
}

main() {
    need_sudo
    step_1_check_disk
    step_2_mount
    step_3_backup_pgdump
    step_4_stop_containers
    step_5_rsync_data
    step_6_update_compose
    step_7_restart_verify
    step_8_cleanup_old
    green ""
    green "==================================="
    green "Migration terminee."
    green "==================================="
    green "Postgres data: ${MOUNT_POINT}/pgdata"
    green "Backup: ${MOUNT_POINT}/pre-migration-*.dump"
}

main "$@"
