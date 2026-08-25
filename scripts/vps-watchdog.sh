#!/bin/bash
# vps-watchdog.sh — Sprint 24+ (2026-08-17)
# Exécuter DIRECTEMENT sur le VPS via cron (pas via SSH).
# Wrap healthcheck-vps.sh : si FAIL, tente un restart auto (docker compose up -d),
# puis alerte Telegram si toujours down. Alerte aussi au retour à la normale.
#
# Cron (toutes les 5 min) :
#   */5 * * * * /opt/lyonflow/scripts/vps-watchdog.sh >> /var/log/lyonflow-watchdog.log 2>&1
#
# Credentials Telegram dans /opt/lyonflow/.watchdog.env (chmod 600) :
#   TELEGRAM_BOT_TOKEN=xxxx
#   TELEGRAM_CHAT_ID=xxxx
#
# Sprint 25+ (2026-08-25) — fix faux positifs en rafale : les checks DB du
# healthcheck (statement_timeout 15s) peuvent occasionnellement timeout sous
# charge légitime (transforms bronze/silver/gold concurrents), sans que le
# stack soit down. Avant ce fix, un seul blip suffisait à déclencher restart
# + alerte Telegram immédiate (cf. 6 alertes en ~6h le 2026-08-25 alors que
# tous les DAGs terminaient success). Fix : exige FAIL_THRESHOLD cycles
# consécutifs (donc ~10min soutenus, pas un pic de 15s) avant d'agir.

set -uo pipefail

COMPOSE_DIR="/opt/lyonflow"
HEALTHCHECK="$COMPOSE_DIR/scripts/healthcheck-vps.sh"
STATE_FILE="$COMPOSE_DIR/.watchdog.state"
ENV_FILE="$COMPOSE_DIR/.watchdog.env"
ALERT_COOLDOWN=1800  # 30min entre deux alertes tant que le stack reste down
FAIL_THRESHOLD=2     # cycles consécutifs (5min chacun) avant restart+alerte

[ -f "$ENV_FILE" ] && source "$ENV_FILE"

telegram_send() {
    local msg="$1"
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
        echo "[watchdog] TELEGRAM_BOT_TOKEN/CHAT_ID absent — alerte non envoyée : $msg"
        return 0
    fi
    curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$msg" >/dev/null
}

now_ts=$(date +%s)
was_down=0
last_alert_ts=0
fail_streak=0
if [ -f "$STATE_FILE" ]; then
    was_down=$(sed -n '1p' "$STATE_FILE")
    last_alert_ts=$(sed -n '2p' "$STATE_FILE")
    fail_streak=$(sed -n '3p' "$STATE_FILE")
fi
was_down=${was_down:-0}
last_alert_ts=${last_alert_ts:-0}
fail_streak=${fail_streak:-0}

echo "[watchdog] $(date -Is) — run healthcheck"
"$HEALTHCHECK" >/tmp/watchdog-healthcheck.log 2>&1
rc=$?

if [ $rc -eq 0 ]; then
    if [ "$was_down" = "1" ]; then
        telegram_send "🟢 LyonFlow VPS : healthcheck de nouveau OK ($(date '+%Y-%m-%d %H:%M:%S %Z'))."
    fi
    printf '0\n0\n0\n' > "$STATE_FILE"
    exit 0
fi

fail_streak=$((fail_streak + 1))
echo "[watchdog] healthcheck FAILED (rc=$rc) — fail_streak=$fail_streak/$FAIL_THRESHOLD"

if [ "$fail_streak" -lt "$FAIL_THRESHOLD" ]; then
    echo "[watchdog] sous le seuil — pas d'action, probable blip transitoire (charge DB)"
    printf '%s\n%s\n%s\n' "$was_down" "$last_alert_ts" "$fail_streak" > "$STATE_FILE"
    exit 1
fi

echo "[watchdog] seuil atteint — tentative restart"
if [ "$was_down" = "0" ]; then
    telegram_send "🔴 LyonFlow VPS : healthcheck FAILED $fail_streak cycles consécutifs ($(date '+%Y-%m-%d %H:%M:%S %Z')). Tentative de restart auto..."
fi

cd "$COMPOSE_DIR" && docker compose up -d >/tmp/watchdog-restart.log 2>&1
sleep 45

"$HEALTHCHECK" >/tmp/watchdog-healthcheck2.log 2>&1
rc2=$?

if [ $rc2 -eq 0 ]; then
    telegram_send "🟢 LyonFlow VPS : restart auto réussi, stack de nouveau OK."
    printf '0\n0\n0\n' > "$STATE_FILE"
    exit 0
fi

if [ $((now_ts - last_alert_ts)) -ge $ALERT_COOLDOWN ]; then
    detail=$(tail -20 /tmp/watchdog-healthcheck2.log)
    telegram_send "🔴 LyonFlow VPS : restart auto ÉCHOUÉ, intervention manuelle requise.
$detail"
    printf '1\n%s\n%s\n' "$now_ts" "$fail_streak" > "$STATE_FILE"
else
    printf '1\n%s\n%s\n' "$last_alert_ts" "$fail_streak" > "$STATE_FILE"
fi
exit 1
