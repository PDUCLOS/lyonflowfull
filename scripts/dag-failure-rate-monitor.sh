#!/bin/bash
# dag-failure-rate-monitor.sh — Sprint 25+ (2026-08-29)
# Exécuter DIRECTEMENT sur le VPS via cron (pas via SSH).
#
# Complète vps-watchdog.sh : celui-ci ne regarde que le DERNIER run de 3 DAGs
# (via healthcheck-vps.sh) — un DAG peut donc afficher "success" alors qu'il
# a échoué 90% du temps sur la journée (cas réel constaté 2026-08-29 :
# refresh_osm_traffic_costs à 91% d'échec sur 24h, jamais détecté car son
# dernier run avait réussi). Ce script calcule le taux d'échec sur 24h par
# DAG (tous les DAGs, pas une liste figée) et alerte Telegram uniquement au
# franchissement du seuil — pas à chaque cycle — pour éviter le bruit.
#
# Cron (toutes les 30 min) :
#   */30 * * * * /opt/lyonflow/scripts/dag-failure-rate-monitor.sh >> /var/log/lyonflow-dag-monitor.log 2>&1
#
# Sprint 26 (2026-09-22) — hystérésis : un DAG entre en alerte à
# >= FAIL_RATE_THRESHOLD et n'en sort qu'à < RECOVER_THRESHOLD. Avant ce fix,
# un DAG oscillant pile sur le seuil (refresh_osm_traffic_costs à 19/95 =
# 20,0 %) produisait alerte / recovery / alerte à chaque cycle de 30 min.
#
# 2026-10-03 — DAGs peu fréquents : MIN_RUNS écarte les DAGs quotidiens ou
# hebdomadaires du calcul de taux (bruit statistique), si bien que
# refresh_lieux_calendrier a échoué 101 jours de suite sans une alerte. Règle
# complémentaire : un DAG non suspendu sous MIN_RUNS runs/24h entre en alerte
# quand ses STREAK_FAILS derniers runs (8 jours) ont échoué, et en sort au
# premier succès. Même état / même hystérésis d'envoi que les taux.
#
# Credentials Telegram réutilisées depuis /opt/lyonflow/.watchdog.env :
#   TELEGRAM_BOT_TOKEN=xxxx
#   TELEGRAM_CHAT_ID=xxxx

set -uo pipefail

COMPOSE_DIR="/opt/lyonflow"
ENV_FILE="$COMPOSE_DIR/.watchdog.env"
STATE_FILE="$COMPOSE_DIR/.dag-failure-monitor.state"
WINDOW_HOURS=24
FAIL_RATE_THRESHOLD=20   # % d'échec sur la fenêtre pour déclencher l'alerte
RECOVER_THRESHOLD=15     # % sous lequel un DAG en alerte est considéré rétabli (hystérésis)
MIN_RUNS=5               # ignore les DAGs avec trop peu de runs (bruit statistique)
STREAK_FAILS=2           # DAGs peu fréquents : N derniers runs en échec = alerte

[ -f "$ENV_FILE" ] && source "$ENV_FILE"

telegram_send() {
    local msg="$1"
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
        echo "[dag-monitor] TELEGRAM_BOT_TOKEN/CHAT_ID absent — alerte non envoyée : $msg"
        return 0
    fi
    curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$msg" >/dev/null
}

# dag_id|ok|ko|total|rate_pct, un par ligne. statement_timeout large (60s) :
# ce script n'est pas sensible à la latence (cron 30min), autant attendre
# plutôt qu'échouer sous charge concurrente (cf. Sprint 25+ audit — requête
# similaire déjà vue en timeout à 5-30s pendant des rafales de REFRESH MV).
rows=$(docker exec lyonflow-postgres psql -U lyonflow -d airflow -tA -F'|' -c "
    SET statement_timeout='60s';
    SELECT dag_id,
        count(*) FILTER (WHERE state='success') AS ok,
        count(*) FILTER (WHERE state='failed') AS ko,
        count(*) AS total,
        round(100.0 * count(*) FILTER (WHERE state='failed') / count(*), 1) AS rate
    FROM dag_run
    WHERE execution_date > now() - interval '${WINDOW_HOURS} hours'
        AND state IN ('success','failed')
    GROUP BY dag_id
    HAVING count(*) >= ${MIN_RUNS}
    ORDER BY rate DESC;
" 2>&1)

if [ $? -ne 0 ]; then
    echo "[dag-monitor] $(date -Is) — requête échouée, abandon ce cycle : $rows"
    exit 1
fi

# DAGs peu fréquents (< MIN_RUNS runs/24h, non suspendus) dont les
# STREAK_FAILS derniers runs sur 8 jours ont tous échoué : dag_id|n_failed
streaks=$(docker exec lyonflow-postgres psql -U lyonflow -d airflow -tA -F'|' -c "
    SET statement_timeout='60s';
    WITH frequent AS (
        SELECT dag_id FROM dag_run
        WHERE execution_date > now() - interval '${WINDOW_HOURS} hours'
            AND state IN ('success','failed')
        GROUP BY dag_id HAVING count(*) >= ${MIN_RUNS}
    ),
    runs AS (
        SELECT r.dag_id, r.state,
            row_number() OVER (PARTITION BY r.dag_id ORDER BY r.execution_date DESC) AS rn
        FROM dag_run r JOIN dag d ON d.dag_id = r.dag_id AND NOT d.is_paused
        WHERE r.execution_date > now() - interval '8 days'
            AND r.state IN ('success','failed')
            AND r.dag_id NOT IN (SELECT dag_id FROM frequent)
    )
    SELECT dag_id, count(*) FROM runs
    WHERE rn <= ${STREAK_FAILS}
    GROUP BY dag_id
    HAVING count(*) FILTER (WHERE state = 'failed') = ${STREAK_FAILS};
" 2>&1)

if [ $? -ne 0 ]; then
    echo "[dag-monitor] $(date -Is) — requête streaks échouée, abandon ce cycle : $streaks"
    exit 1
fi
# grep '|' : psql affiche aussi « SET » (écho du statement_timeout), à ne pas prendre pour un DAG
streak_dags=$(echo "$streaks" | grep '|' | cut -d'|' -f1 || true)

# DAGs déjà en alerte au cycle précédent (un dag_id par ligne)
previously_alerting=""
[ -f "$STATE_FILE" ] && previously_alerting=$(cat "$STATE_FILE")

# DAGs au-dessus du seuil d'entrée ce cycle (+ DAGs peu fréquents en échec répété)
above_threshold=$(echo "$rows" | awk -F'|' -v t="$FAIL_RATE_THRESHOLD" '$5+0 >= t {print $1}')
[ -n "$streak_dags" ] && above_threshold+=$'\n'"$streak_dags"

# Hystérésis : un DAG déjà en alerte reste en alerte tant qu'il est
# >= RECOVER_THRESHOLD (même s'il est repassé sous FAIL_RATE_THRESHOLD)
still_above_recover=$(echo "$rows" | awk -F'|' -v r="$RECOVER_THRESHOLD" '$5+0 >= r {print $1}')
while IFS= read -r dag; do
    [ -z "$dag" ] && continue
    if grep -qxF "$dag" <<< "$still_above_recover" && ! grep -qxF "$dag" <<< "$above_threshold"; then
        above_threshold+=$'\n'"$dag"
    fi
done <<< "$previously_alerting"

# Nouvelles entrées en alerte (présentes maintenant, absentes avant)
new_alerts=""
while IFS= read -r dag; do
    [ -z "$dag" ] && continue
    if ! grep -qxF "$dag" <<< "$previously_alerting"; then
        if grep -qxF "$dag" <<< "$streak_dags"; then
            new_alerts+="🔴 ${dag} : ${STREAK_FAILS} derniers runs en échec (DAG peu fréquent)"$'\n'
            continue
        fi
        line=$(echo "$rows" | awk -F'|' -v d="$dag" '$1==d')
        ok=$(echo "$line" | cut -d'|' -f2); ko=$(echo "$line" | cut -d'|' -f3)
        total=$(echo "$line" | cut -d'|' -f4); rate=$(echo "$line" | cut -d'|' -f5)
        new_alerts+="🔴 ${dag} : ${rate}% échec (${ko}/${total} runs, ${WINDOW_HOURS}h)"$'\n'
    fi
done <<< "$above_threshold"

# Entrées qui étaient en alerte et sont repassées sous le seuil (repêche aussi
# les DAGs qui ont carrément disparu du résultat, ex: plus assez de runs)
recovered=""
while IFS= read -r dag; do
    [ -z "$dag" ] && continue
    if ! grep -qxF "$dag" <<< "$above_threshold"; then
        recovered+="🟢 ${dag} : revenu à la normale (sous ${RECOVER_THRESHOLD}% d'échec ou dernier run réussi)"$'\n'
    fi
done <<< "$previously_alerting"

if [ -n "$new_alerts" ]; then
    telegram_send "LyonFlow VPS — nouveau(x) DAG(s) en échec répété :
${new_alerts}"
    echo "[dag-monitor] $(date -Is) — alerte envoyée :"$'\n'"$new_alerts"
fi

if [ -n "$recovered" ]; then
    telegram_send "LyonFlow VPS — DAG(s) revenu(s) à la normale :
${recovered}"
    echo "[dag-monitor] $(date -Is) — recovery :"$'\n'"$recovered"
fi

if [ -z "$new_alerts" ] && [ -z "$recovered" ]; then
    echo "[dag-monitor] $(date -Is) — rien à signaler ($(echo "$above_threshold" | grep -c .) DAG(s) au-dessus du seuil, sans changement)"
fi

echo "$above_threshold" | grep . > "$STATE_FILE" || true
