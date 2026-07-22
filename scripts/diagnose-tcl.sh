#!/bin/bash
# Diagnostic TCL SIRI Lite — Sprint 23+
# Exécuter sur le VPS via SSH : ssh root@51.83.159.224 'bash -s' < scripts/diagnose-tcl.sh
#
# Vérifie chaque maillon du pipeline TCL :
# 1. Variables d'env (auth API Grand Lyon)
# 2. Connectivité API SIRI Lite (curl direct)
# 3. DAG collect_bronze / task collect_tclsirilite (dernier run + état)
# 4. Table bronze.tcl_vehicles (dernière ligne, format, n_records)
# 5. Table silver.tcl_vehicles_clean (vide ou pas, fraîcheur)
# 6. Table gold.tcl_vehicle_realtime (idem)
#
# Exit codes : 0 = tout OK · 1 = auth manquante · 2 = API inaccessible · 3 = bronze vide · 4 = silver vide

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok=0
warn=0
fail=0
exit_code=0

header() {
    echo ""
    echo -e "${BLUE}=========== $1 ===========${NC}"
}

ok_msg() {
 echo -e " ${GREEN}${NC} $1"
    ((ok++))
}

warn_msg() {
 echo -e " ${YELLOW}${NC} $1"
    ((warn++))
}

fail_msg() {
 echo -e " ${RED}${NC} $1"
    ((fail++))
}

psql_query() {
    docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \
        "SET statement_timeout='15s'; $1" 2>&1 | tail -1
}

# =============================================================================
# 1. Variables d'env dans le container airflow
# =============================================================================
header "1/6 — Variables d'env (auth API Grand Lyon)"
USER_VAL=$(docker exec lyonflow-airflow-scheduler printenv GRANDLYON_USERNAME 2>/dev/null || echo "")
PASS_VAL=$(docker exec lyonflow-airflow-scheduler printenv GRANDLYON_PASSWORD 2>/dev/null || echo "")
ALT_USER=$(docker exec lyonflow-airflow-scheduler printenv API_LOGIN 2>/dev/null || echo "")
ALT_PASS=$(docker exec lyonflow-airflow-scheduler printenv API_PASSWORD 2>/dev/null || echo "")

if [ -n "$USER_VAL" ] && [ -n "$PASS_VAL" ]; then
    ok_msg "GRANDLYON_USERNAME + GRANDLYON_PASSWORD set (user='$USER_VAL')"
elif [ -n "$ALT_USER" ] && [ -n "$ALT_PASS" ]; then
    ok_msg "API_LOGIN + API_PASSWORD set (fallback)"
else
    fail_msg "Auth API Grand Lyon NON configurée → 401/403 garanti"
    echo "    → Fix : ajouter dans .env VPS + restart containers :"
    echo "      GRANDLYON_USERNAME=<user>"
    echo "      GRANDLYON_PASSWORD=<password>"
    exit_code=1
fi

# =============================================================================
# 2. Connectivité API SIRI Lite (curl direct avec auth)
# =============================================================================
header "2/6 — Test API SIRI Lite 2.0 (curl)"
URL="https://data.grandlyon.com/siri-lite/2.0/vehicle-monitoring.json"

# Build curl command with auth
if [ -n "$USER_VAL" ] && [ -n "$PASS_VAL" ]; then
    AUTH_ARGS="-u $USER_VAL:$PASS_VAL"
elif [ -n "$ALT_USER" ] && [ -n "$ALT_PASS" ]; then
    AUTH_ARGS="-u $ALT_USER:$ALT_PASS"
else
    AUTH_ARGS=""
fi

CURL_OUT=$(curl -s -o /tmp/siri_response.json -w "HTTP=%{http_code} bytes=%{size_download} time=%{time_total}s" \
    --max-time 30 $AUTH_ARGS "$URL" 2>&1 || echo "CURL_ERROR")
echo "  $CURL_OUT"

HTTP_CODE=$(echo "$CURL_OUT" | grep -oP 'HTTP=\K[0-9]+' || echo "0")

if [ "$HTTP_CODE" = "200" ]; then
    ok_msg "API SIRI Lite répond 200 OK"
    SIZE=$(wc -c < /tmp/siri_response.json)
    N_ACT=$(python3 -c "
import json
try:
    with open('/tmp/siri_response.json') as f:
        data = json.load(f)
    acts = data.get('Siri', {}).get('ServiceDelivery', {}).get('VehicleMonitoringDelivery', [{}])[0].get('VehicleActivity', [])
    print(len(acts))
except Exception as e:
    print(f'PARSE_ERROR: {e}')
" 2>/dev/null)
    if [ -n "$N_ACT" ] && [ "$N_ACT" -gt 0 ] 2>/dev/null; then
        ok_msg "Format SIRI 2.0 OK · $N_ACT VehicleActivity dans la réponse ($SIZE bytes)"
    else
        fail_msg "Format SIRI inattendu — $N_ACT VehicleActivity, voir /tmp/siri_response.json"
        echo "    → Inspecter : head -c 2000 /tmp/siri_response.json"
        exit_code=2
    fi
elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ]; then
    fail_msg "API SIRI Lite → $HTTP_CODE (auth refusée)"
    echo "    → Régénérer identifiants sur data.grandlyon.com (portail Grand Lyon)"
    exit_code=2
elif [ "$HTTP_CODE" = "404" ]; then
    fail_msg "API SIRI Lite → 404 (URL obsolète ?)"
    echo "    → Vérifier sur https://data.grandlyon.com/chercher?q=siri+lite"
    exit_code=2
elif [ "$HTTP_CODE" = "0" ]; then
    fail_msg "Curl impossible (réseau, DNS, timeout)"
    exit_code=2
else
    fail_msg "API SIRI Lite → HTTP $HTTP_CODE (inattendu)"
    exit_code=2
fi

# =============================================================================
# 3. DAG collect_bronze — task collect_tclsirilite
# =============================================================================
header "3/6 — Airflow DAG collect_bronze / task collect_tclsirilite"
DAG_STATE=$(docker exec lyonflow-airflow-scheduler airflow dags list-runs -d collect_bronze -o plain 2>/dev/null | sed -n '2p' | awk '{print $3}')
if [ "$DAG_STATE" = "success" ]; then
    ok_msg "DAG collect_bronze : dernier run = success"
elif [ "$DAG_STATE" = "running" ]; then
    ok_msg "DAG collect_bronze : en cours d'exécution"
elif [ "$DAG_STATE" = "failed" ]; then
    fail_msg "DAG collect_bronze : dernier run = FAILED"
    echo "    → Voir logs : docker logs lyonflow-airflow-scheduler --tail 200 | grep -i tcl"
    exit_code=3
elif [ -z "$DAG_STATE" ]; then
    fail_msg "DAG collect_bronze : aucun run trouvé"
else
    warn_msg "DAG collect_bronze : état = $DAG_STATE"
fi

# Détail task TCL
TASK_LIST=$(docker exec lyonflow-airflow-scheduler airflow tasks list-runs -d collect_bronze -t collect_tclsirilite --limit 1 -o plain 2>/dev/null | tail -1)
echo "  Task collect_tclsirilite : $TASK_LIST"

# =============================================================================
# 4. Table bronze.tcl_vehicles (dernière ligne + format)
# =============================================================================
header "4/6 — bronze.tcl_vehicles"
LAST_FETCH=$(psql_query "SELECT MAX(fetched_at) FROM bronze.tcl_vehicles")
N_TOTAL=$(psql_query "SELECT COUNT(*) FROM bronze.tcl_vehicles")
N_1H=$(psql_query "SELECT COUNT(*) FROM bronze.tcl_vehicles WHERE fetched_at > NOW() - INTERVAL '1 hour'")

if [ -z "$LAST_FETCH" ] || [ "$LAST_FETCH" = "" ]; then
    fail_msg "bronze.tcl_vehicles VIDE — collecteur n'insère jamais rien"
    exit_code=3
else
    AGE=$(psql_query "SELECT EXTRACT(EPOCH FROM NOW() - MAX(fetched_at))::int FROM bronze.tcl_vehicles")
    if [ "$AGE" -lt 600 ]; then
        ok_msg "bronze.tcl_vehicles dernière ligne = $LAST_FETCH (il y a ${AGE}s)"
    elif [ "$AGE" -lt 3600 ]; then
        warn_msg "bronze.tcl_vehicles dernière ligne = $LAST_FETCH (il y a ${AGE}s = $(($AGE/60))min)"
    else
        fail_msg "bronze.tcl_vehicles dernière ligne = $LAST_FETCH (il y a ${AGE}s = $(($AGE/3600))h)"
    fi
fi
echo "    Total : $N_TOTAL lignes | Dernière heure : $N_1H"

# Vérif format SIRI 2.0 sur la dernière ligne
if [ -n "$LAST_FETCH" ] && [ "$LAST_FETCH" != "" ]; then
    FORMAT_CHECK=$(psql_query "
        SELECT CASE
            WHEN raw_data->'Siri'->'ServiceDelivery'->'VehicleMonitoringDelivery'->0->'VehicleActivity' IS NOT NULL
            THEN 'SIRI_2.0_OK'
            ELSE 'FORMAT_INATTENDU'
        END
        FROM bronze.tcl_vehicles ORDER BY fetched_at DESC LIMIT 1
    ")
    if [ "$FORMAT_CHECK" = "SIRI_2.0_OK" ]; then
        N_VEH=$(psql_query "
            SELECT jsonb_array_length(raw_data->'Siri'->'ServiceDelivery'->'VehicleMonitoringDelivery'->0->'VehicleActivity')
            FROM bronze.tcl_vehicles ORDER BY fetched_at DESC LIMIT 1
        ")
        ok_msg "Format raw_data = SIRI 2.0 ($N_VEH VehicleActivity dans dernière ligne)"
    else
        fail_msg "Format raw_data INATTENDU ($FORMAT_CHECK) — code de parsing ne match plus"
        echo "    → Récupérer la ligne pour debug :"
        echo "      psql -c \"SELECT raw_data FROM bronze.tcl_vehicles ORDER BY fetched_at DESC LIMIT 1\""
        exit_code=3
    fi
fi

# =============================================================================
# 5. Table silver.tcl_vehicles_clean
# =============================================================================
header "5/6 — silver.tcl_vehicles_clean"
SILVER_LAST=$(psql_query "SELECT MAX(measurement_time) FROM silver.tcl_vehicles_clean")
SILVER_N_1H=$(psql_query "SELECT COUNT(*) FROM silver.tcl_vehicles_clean WHERE measurement_time > NOW() - INTERVAL '1 hour'")
SILVER_N_TOTAL=$(psql_query "SELECT COUNT(*) FROM silver.tcl_vehicles_clean")

if [ -z "$SILVER_LAST" ] || [ "$SILVER_LAST" = "" ]; then
    fail_msg "silver.tcl_vehicles_clean VIDE — transform bronze→silverbroke"
    exit_code=4
else
    SILVER_AGE=$(psql_query "SELECT EXTRACT(EPOCH FROM NOW() - MAX(measurement_time))::int FROM silver.tcl_vehicles_clean")
    if [ "$SILVER_AGE" -lt 900 ]; then
        ok_msg "silver.tcl_vehicles_clean dernière mesure = $SILVER_LAST (il y a ${SILVER_AGE}s)"
    elif [ "$SILVER_AGE" -lt 3600 ]; then
        warn_msg "silver.tcl_vehicles_clean dernière mesure = $SILVER_LAST (il y a $(($SILVER_AGE/60))min)"
    else
        fail_msg "silver.tcl_vehicles_clean dernière mesure = $SILVER_LAST (il y a $(($SILVER_AGE/3600))h)"
        exit_code=4
    fi
fi
echo "    Total : $SILVER_N_TOTAL lignes | Dernière heure : $SILVER_N_1H"

# =============================================================================
# 6. Table gold.tcl_vehicle_realtime
# =============================================================================
header "6/6 — gold.tcl_vehicle_realtime"
GOLD_LAST=$(psql_query "SELECT MAX(recorded_at) FROM gold.tcl_vehicle_realtime")
GOLD_N_1H=$(psql_query "SELECT COUNT(*) FROM gold.tcl_vehicle_realtime WHERE recorded_at > NOW() - INTERVAL '1 hour'")
GOLD_N_TOTAL=$(psql_query "SELECT COUNT(*) FROM gold.tcl_vehicle_realtime")

if [ -z "$GOLD_LAST" ] || [ "$GOLD_LAST" = "" ]; then
    fail_msg "gold.tcl_vehicle_realtime VIDE — le widget Pro_2 (Vue Réseau) ne peut rien afficher"
else
    GOLD_AGE=$(psql_query "SELECT EXTRACT(EPOCH FROM NOW() - MAX(recorded_at))::int FROM gold.tcl_vehicle_realtime")
    if [ "$GOLD_AGE" -lt 900 ]; then
        ok_msg "gold.tcl_vehicle_realtime dernière mesure = $GOLD_LAST (il y a ${GOLD_AGE}s)"
    elif [ "$GOLD_AGE" -lt 3600 ]; then
        warn_msg "gold.tcl_vehicle_realtime dernière mesure = $GOLD_LAST (il y a $(($GOLD_AGE/60))min)"
    else
        fail_msg "gold.tcl_vehicle_realtime dernière mesure = $GOLD_LAST (il y a $(($GOLD_AGE/3600))h)"
    fi
fi
echo "    Total : $GOLD_N_TOTAL lignes | Dernière heure : $GOLD_N_1H"

# =============================================================================
# Résumé + recommandations
# =============================================================================
echo ""
echo -e "${BLUE}=========== RÉSUMÉ ===========${NC}"
echo -e "  ${GREEN}OK${NC} : $ok"
echo -e "  ${YELLOW}WARN${NC} : $warn"
echo -e "  ${RED}FAIL${NC} : $fail"
echo ""

if [ $fail -eq 0 ]; then
    echo -e "${GREEN}DIAGNOSTIC OK${NC} — pipeline TCL fonctionnel"
    exit 0
fi

echo "Pistes à explorer dans l'ordre :"
echo ""
echo "1. AUTH (le plus fréquent) — vérifier identifiants sur data.grandlyon.com"
echo "   → .env VPS doit contenir : GRANDLYON_USERNAME=xxx GRANDLYON_PASSWORD=xxx"
echo "   → restart : docker compose restart airflow-scheduler"
echo ""
echo "2. URL obsolète — vérifier sur https://data.grandlyon.com/chercher?q=siri+lite"
echo "   → Si URL changée, mettre à jour TCL_SIRI_LITE_URL dans .env"
echo ""
echo "3. Format API changé — voir /tmp/siri_response.json (étape 2)"
echo "   → Si structure différente, mettre à jour src/transformation/bronze_to_silver.py"
echo ""
echo "4. DAG pause — vérifier UI Airflow ou :"
echo "   → docker exec lyonflow-airflow-scheduler airflow dags unpause collect_bronze"
echo ""
echo "5. Logs Airflow task TCL :"
echo "   → docker logs lyonflow-airflow-scheduler --tail 500 | grep -i 'tcl\\|siri\\|collect_tcl'"
echo ""
exit $exit_code