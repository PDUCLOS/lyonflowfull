#!/bin/bash
# backup-failed-alert.sh — Sprint 26 (2026-09-22)
# Appelé par systemd via OnFailure= de lyonflow-backup.service
# (unit deploy/systemd/lyonflow-backup-failed.service).
# Envoie une alerte Telegram avec les dernières lignes du journal du backup.
#
# Contexte : le backup offsite est resté silencieusement cassé du 2026-07-22
# au 2026-09-22 (timer désactivé + config rclone invalide) sans qu'aucune
# alerte ne remonte. Credentials Telegram : /opt/lyonflow/.watchdog.env.

set -uo pipefail

ENV_FILE="/opt/lyonflow/.watchdog.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    echo "[backup-alert] TELEGRAM_BOT_TOKEN/CHAT_ID absent — alerte non envoyée"
    exit 0
fi

detail=$(journalctl -u lyonflow-backup.service -n 15 --no-pager -o cat 2>/dev/null | tail -8)
msg="🔴 LyonFlow VPS : backup offsite ÉCHOUÉ ($(date '+%Y-%m-%d %H:%M %Z')).
Voir : journalctl -u lyonflow-backup.service
${detail}"

curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${msg}" >/dev/null
echo "[backup-alert] alerte Telegram envoyée"
