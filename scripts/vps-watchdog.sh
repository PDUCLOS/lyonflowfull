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
#
# 2026-09-30 — distinction panne / lenteur. Restarts + alertes chaque nuit à
# 03:10-03:15 (28, 29, 30 sept, et déjà 2-10 sept) pendant la charge DB de
# 03:00 (maintenance, purge_bronze, pg_dump du backup). Un timeout de requête
# signale une DB lente, pas un service tombé : `docker compose up -d` ne
# change rien à des containers déjà démarrés, le restart était inutile et
# l'alerte du bruit. Désormais :
#   - échec "dur" (container arrêté, PG muet, endpoint HTTP KO) → comportement
#     historique : restart + alerte après FAIL_THRESHOLD cycles ;
#   - échec limité à des timeouts de requête → pas de restart, alerte unique
#     seulement si la lenteur dure SLOW_THRESHOLD cycles.
# Le détail des checks en échec est écrit dans le log du watchdog (le log du
# healthcheck est écrasé toutes les 5 min, impossible de diagnostiquer avant).

set -uo pipefail

COMPOSE_DIR="/opt/lyonflow"
HEALTHCHECK="$COMPOSE_DIR/scripts/healthcheck-vps.sh"
STATE_FILE="$COMPOSE_DIR/.watchdog.state"
ENV_FILE="$COMPOSE_DIR/.watchdog.env"
ALERT_COOLDOWN=1800  # 30min entre deux alertes tant que le stack reste down
FAIL_THRESHOLD=2     # cycles consécutifs (5min chacun) avant restart+alerte
SLOW_THRESHOLD=9     # cycles de lenteur seule (~45 min) avant alerte, sans restart

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
slow_streak=0
if [ -f "$STATE_FILE" ]; then
    was_down=$(sed -n '1p' "$STATE_FILE")
    last_alert_ts=$(sed -n '2p' "$STATE_FILE")
    fail_streak=$(sed -n '3p' "$STATE_FILE")
    slow_streak=$(sed -n '4p' "$STATE_FILE")
fi
was_down=${was_down:-0}
last_alert_ts=${last_alert_ts:-0}
fail_streak=${fail_streak:-0}
slow_streak=${slow_streak:-0}

save_state() {  # was_down last_alert_ts fail_streak slow_streak
    printf '%s\n%s\n%s\n%s\n' "$1" "$2" "$3" "$4" > "$STATE_FILE"
}

echo "[watchdog] $(date -Is) — run healthcheck"
"$HEALTHCHECK" >/tmp/watchdog-healthcheck.log 2>&1
rc=$?

if [ $rc -eq 0 ]; then
    if [ "$was_down" = "1" ]; then
        telegram_send "🟢 LyonFlow VPS : healthcheck de nouveau OK ($(date '+%Y-%m-%d %H:%M:%S %Z'))."
    fi
    save_state 0 0 0 0
    exit 0
fi

# Checks en échec, sans les codes couleur, gardés dans le log du watchdog.
failed_checks=$(sed 's/\x1b\[[0-9;]*m//g' /tmp/watchdog-healthcheck.log | grep '^FAIL ' || true)
echo "$failed_checks" | sed 's/^/[watchdog]   /'
hard_failures=$(echo "$failed_checks" | grep -v 'statement timeout' | grep -c . || true)

if [ "$hard_failures" -eq 0 ] && [ -n "$failed_checks" ]; then
    slow_streak=$((slow_streak + 1))
    echo "[watchdog] lenteur DB seule (timeouts) — slow_streak=$slow_streak/$SLOW_THRESHOLD, pas de restart"
    if [ "$slow_streak" -eq "$SLOW_THRESHOLD" ]; then
        telegram_send "🟠 LyonFlow VPS : base lente depuis ~$((slow_streak * 5)) min (requêtes du healthcheck en timeout), services up, pas de restart.
$failed_checks"
    fi
    save_state "$was_down" "$last_alert_ts" 0 "$slow_streak"
    exit 1
fi

fail_streak=$((fail_streak + 1))
echo "[watchdog] healthcheck FAILED (rc=$rc) — fail_streak=$fail_streak/$FAIL_THRESHOLD"

if [ "$fail_streak" -lt "$FAIL_THRESHOLD" ]; then
    echo "[watchdog] sous le seuil — pas d'action, probable blip transitoire"
    save_state "$was_down" "$last_alert_ts" "$fail_streak" 0
    exit 1
fi

echo "[watchdog] seuil atteint — tentative restart"
if [ "$was_down" = "0" ]; then
    telegram_send "🔴 LyonFlow VPS : healthcheck FAILED $fail_streak cycles consécutifs ($(date '+%Y-%m-%d %H:%M:%S %Z')). Tentative de restart auto...
$failed_checks"
fi

cd "$COMPOSE_DIR" && docker compose up -d >/tmp/watchdog-restart.log 2>&1
sleep 45

"$HEALTHCHECK" >/tmp/watchdog-healthcheck2.log 2>&1
rc2=$?

if [ $rc2 -eq 0 ]; then
    telegram_send "🟢 LyonFlow VPS : restart auto réussi, stack de nouveau OK."
    save_state 0 0 0 0
    exit 0
fi

if [ $((now_ts - last_alert_ts)) -ge $ALERT_COOLDOWN ]; then
    detail=$(sed 's/\x1b\[[0-9;]*m//g' /tmp/watchdog-healthcheck2.log | grep '^FAIL ' || tail -20 /tmp/watchdog-healthcheck2.log)
    telegram_send "🔴 LyonFlow VPS : restart auto ÉCHOUÉ, intervention manuelle requise.
$detail"
    save_state 1 "$now_ts" "$fail_streak" 0
else
    save_state 1 "$last_alert_ts" "$fail_streak" 0
fi
exit 1
