#!/bin/bash
# Healthcheck VPS — Sprint 15+ (2026-06-19)
# Exécuter DIRECTEMENT sur le VPS (pas via SSH).
# Exit code 0 = tout OK, 1 = problème détecté.
#
# Sprint 15+ (2026-06-19) — alignement schéma v0.7.1 :
# - silver.trafic_boucles_clean : fetched_at → silver_updated_at
#   (fetched_at n'existe que sur bronze, pas sur silver)
# - gold.trafic_predictions : computed_at → calculated_at
#   (renommé Sprint 15+ lors du refocus H+1h)
# - MLflow : port 5000 → 5001 (mapping docker-compose: 5001:5000)
# - Services retirés de la liste : redis, prometheus, airflow-worker
#   (cf. docker-compose.yml : LocalExecutor + monitoring dormant)

set -uo pipefail

COMPOSE_DIR="/opt/lyonflow"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok=0
warn=0
fail=0

check() {
    local label="$1"
    local result
    result=$(eval "$2" 2>&1)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        echo -e "${GREEN}✓${NC} $label: $result"
        ((ok++))
    else
        echo -e "${RED}✗${NC} $label: FAILED ($result)"
        ((fail++))
    fi
}

check_warn() {
    local label="$1"
    local result
    result=$(eval "$2" 2>&1)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        echo -e "${GREEN}✓${NC} $label: $result"
        ((ok++))
    else
        echo -e "${YELLOW}⚠${NC} $label: $result"
        ((warn++))
    fi
}

# psql avec statement_timeout (Sprint 15+) — évite les hangs sous charge DB.
# Usage : psql_query "<sql>" [timeout]   (défaut 15s)
# SET statement_timeout est session-level, OK en psql -c (chaque appel = nouvelle session).
psql_query() {
    local query="$1"
    local timeout="${2:-15s}"
    docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \
        "SET statement_timeout='${timeout}'; ${query}" 2>&1 | tail -1
}

echo "=== LyonFlow VPS Healthcheck (Sprint 15+) ==="
echo ""

# 1. Containers (docker ps, pas docker compose exec)
echo "--- Containers ---"
# Sprint 15+ — retiré : redis (LocalExecutor), prometheus (config cassée),
# airflow-worker (LocalExecutor n'en a pas besoin).
for svc in postgres minio mlflow api streamlit airflow airflow-scheduler nginx grafana alertmanager; do
    status=$(docker ps --format '{{.Status}}' --filter "name=lyonflow-$svc" 2>/dev/null | head -1)
    if [ -n "$status" ]; then
        echo -e "${GREEN}✓${NC} $svc: $status"
        ((ok++))
    else
        echo -e "${RED}✗${NC} $svc: NOT RUNNING"
        ((fail++))
    fi
done

# 2. Disque
echo ""
echo "--- Disque ---"
check "sda1 (OS+code)" "df / | tail -1 | awk '{print \$5, \"used,\", \$4/1024/1024, \"Go free\"}' | awk '{printf \"%s %s %.1f %s\", \$1, \$2, \$3, \$4}'"
check_warn "postgres-data" "df /mnt/postgres-data 2>/dev/null | tail -1 | awk '{print \$5, \"used,\", \$4/1024/1024, \"Go free\"}' | awk '{printf \"%s %s %.1f %s\", \$1, \$2, \$3, \$4}'"

# 3. CPU/RAM
echo ""
echo "--- Load / RAM ---"
check "load 1min" "uptime | awk -F'load average:' '{print \$2}' | awk -F',' '{print \$1}'"
check "mem available" "free -h | grep Mem | awk '{print \$7, \"available\"}'"

# 4. DB & tables critiques
# Chaque requête psql passe par psql_query() qui :
# - applique SET statement_timeout='15s' (fail fast sous charge)
# - drop la ligne "SET" via tail -1
echo ""
echo "--- DB Health ---"
check "PG responsive" "docker exec lyonflow-postgres pg_isready -U lyonflow 2>&1 | head -1"

check "dim_spatial lat/lon" "psql_query \"SELECT count(*) || '/' || count(lat) || ' lat OK' FROM gold.dim_spatial_grid_mapping\""

# Sprint 15+ — velov_clean: on utilise measurement_time (indexé via
# idx_velov_clean_measurement_time), PAS fetched_at (pas d'index → full scan).
check "velov_clean 1h" 'psql_query "SELECT count(*) FROM silver.velov_clean WHERE measurement_time > NOW() - INTERVAL '\''1 hour'\''"'

# Sprint 15+ — silver.trafic_boucles_clean n'a PAS fetched_at (colonne Bronze only).
# On utilise measurement_time (indexé via idx_silver_boucles_fetched) qui
# reflète la fraîcheur des mesures. silver_updated_at existe aussi mais
# n'est pas indexé → full scan sur 28 GB = timeout.
check "trafic_boucles 1h" 'psql_query "SELECT count(*) FROM silver.trafic_boucles_clean WHERE measurement_time > NOW() - INTERVAL '\''1 hour'\''"'

check "tcl_vehicles 1h" 'psql_query "SELECT count(*) FROM silver.tcl_vehicles_clean WHERE measurement_time > NOW() - INTERVAL '\''1 hour'\''"'

# 5. Gold tables
echo ""
echo "--- Gold Layer ---"
check "traffic_features_live 1h" 'psql_query "SELECT count(*) FROM gold.traffic_features_live WHERE fetched_at > NOW() - INTERVAL '\''1 hour'\''"'

check "tcl_vehicle_realtime 1h" 'psql_query "SELECT count(*) FROM gold.tcl_vehicle_realtime WHERE recorded_at > NOW() - INTERVAL '\''1 hour'\''"'

# Sprint 15+ — gold.trafic_predictions utilise calculated_at (PAS computed_at).
# Renommé lors du refocus H+1h pour éviter la confusion avec predicted_at.
check "trafic_predictions 2h" 'psql_query "SELECT count(*) FROM gold.trafic_predictions WHERE calculated_at > NOW() - INTERVAL '\''2 hours'\''"'

check "infra_bottlenecks" 'psql_query "SELECT count(*) FROM gold.infrastructure_bottlenecks"'

check "bus_delay_segments" 'psql_query "SELECT count(*) FROM gold.bus_delay_segments"'

# 6. Vues matérialisées
echo ""
echo "--- Materialized Views ---"
check_warn "mv_line_kpis_live" 'psql_query "SELECT count(*) FROM gold.mv_line_kpis_live"'

check_warn "mv_otp_heatmap" 'psql_query "SELECT count(*) FROM gold.mv_otp_heatmap"'

check_warn "mv_multimodal_grid" 'psql_query "SELECT count(*) FROM gold.mv_multimodal_grid" 2>/dev/null || echo "migration 017 pas appliquee"'

check_warn "mv_bus_traffic_spatial" 'psql_query "SELECT count(*) FROM gold.mv_bus_traffic_spatial" 2>/dev/null || echo "migration 018 pas appliquee"'

# 60s pour fn_network_health_score (jointures multiples sur les couches Gold).
# WARN, pas FAIL : sous forte charge, la requête peut timeout — c'est informatif,
# pas critique pour la santé du pipeline.
check_warn "fn_network_health_score" "psql_query \"SELECT score || ' (' || diagnosis || ')' FROM gold.fn_network_health_score()\" 60s 2>/dev/null || echo 'timeout sous charge'"

# 7. Endpoints HTTP
echo ""
echo "--- Endpoints HTTP ---"
check "Streamlit 8501" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8501/_stcore/health 2>/dev/null"
check "API 8000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null"
check "Grafana 3000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:3000/api/health 2>/dev/null"
# Sprint 15+ — MLflow mappé 127.0.0.1:5001→5000 (cf. docker-compose.yml).
# Le check direct sur 5000 ne fonctionne que DEPUIS le container MLflow.
check "MLflow 5001" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:5001/health 2>/dev/null"

# 8. Airflow DAGs derniers runs (Sprint 15+ — fix: --limit n'existe pas sur list-runs)
# Format plain : colonnes whitespace-separated (header en ligne 1, runs en-dessous).
# La dernière run (la plus récente) est en ligne 2 ; state = colonne 3.
echo ""
echo "--- Airflow DAGs (last run state) ---"
check_warn "collect_bronze" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d collect_bronze -o plain 2>/dev/null | sed -n '2p' | awk '{print \$3}'"
check_warn "transform_silver_to_gold" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d transform_silver_to_gold -o plain 2>/dev/null | sed -n '2p' | awk '{print \$3}'"
check_warn "dag_inference_xgboost" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d dag_inference_xgboost -o plain 2>/dev/null | sed -n '2p' | awk '{print \$3}'"

# Résumé
echo ""
echo "=== Résumé ==="
echo -e "${GREEN}OK: $ok${NC} | ${YELLOW}WARN: $warn${NC} | ${RED}FAIL: $fail${NC}"
total=$((ok + warn + fail))
echo "Total: $total checks"

if [ $fail -gt 0 ]; then
    echo -e "${RED}HEALTHCHECK FAILED — investiguer les erreurs ci-dessus${NC}"
    exit 1
fi
if [ $warn -gt 0 ]; then
    echo -e "${YELLOW}HEALTHCHECK OK avec warnings${NC}"
    exit 0
fi
echo -e "${GREEN}HEALTHCHECK OK${NC}"
exit 0
