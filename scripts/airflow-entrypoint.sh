#!/bin/bash
# =============================================================================
# airflow-entrypoint.sh — Fix permissions puis lance Airflow
# =============================================================================
# Problème : après chaque rsync/deploy, ./logs/airflow appartient à root.
# Le container Airflow tourne en UID 50000, crash sur PermissionError.
#
# Solution : ce script tourne en root au boot, fix les permissions,
# puis exec en user airflow (UID 50000) pour lancer le service.
# =============================================================================

set -e

AIRFLOW_UID=${AIRFLOW_UID:-50000}
AIRFLOW_GID=${AIRFLOW_GID:-0}

# Fix permissions sur les répertoires montés
for dir in /opt/airflow/logs /opt/airflow/data; do
    if [ -d "$dir" ]; then
        chown -R "${AIRFLOW_UID}:${AIRFLOW_GID}" "$dir" 2>/dev/null || true
    fi
done

# Créer le répertoire logs s'il n'existe pas
mkdir -p /opt/airflow/logs
chown "${AIRFLOW_UID}:${AIRFLOW_GID}" /opt/airflow/logs

# Exec en user airflow
exec gosu airflow airflow "$@"
