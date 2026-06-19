#!/bin/bash
# Healthcheck VPS — Sprint 15+ (2026-06-19)
# Exécuter DIRECTEMENT sur le VPS (pas via SSH).
# Exit code 0 = tout OK, 1 = problème détecté.

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

echo "=== LyonFlowFull VPS Healthcheck (Sprint 15+) ==="
echo ""

# 1. Containers (docker ps, pas docker compose exec)
echo "--- Containers ---"
for svc in postgres redis minio mlflow api streamlit airflow airflow-scheduler airflow-worker nginx grafana prometheus alertmanager; do
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
echo ""
echo "--- DB Health ---"
check "PG responsive" "docker exec lyonflow-postgres pg_isready -U lyonflow 2>&1 | head -1"

check "dim_spatial lat/lon" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) || '/' || count(lat) || ' lat OK' FROM gold.dim_spatial_grid_mapping\""

check "velov_clean 1h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.velov_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'\""

check "trafic_boucles 1h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.trafic_boucles_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'\""

check "tcl_vehicles 1h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.tcl_vehicles_clean WHERE measurement_time > NOW() - INTERVAL '1 hour'\""

# 5. Gold tables
echo ""
echo "--- Gold Layer ---"
check "traffic_features_live 1h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.traffic_features_live WHERE fetched_at > NOW() - INTERVAL '1 hour'\""

check "tcl_vehicle_realtime 1h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.tcl_vehicle_realtime WHERE recorded_at > NOW() - INTERVAL '1 hour'\""

check "trafic_predictions 2h" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.trafic_predictions WHERE computed_at > NOW() - INTERVAL '2 hours'\""

check "infra_bottlenecks" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.infrastructure_bottlenecks\""

check "bus_delay_segments" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.bus_delay_segments\""

# 6. Vues matérialisées
echo ""
echo "--- Materialized Views ---"
check_warn "mv_line_kpis_live" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.mv_line_kpis_live\""

check_warn "mv_otp_heatmap" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.mv_otp_heatmap\""

check_warn "mv_multimodal_grid" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.mv_multimodal_grid\" 2>/dev/null || echo 'migration 017 pas appliquee'"

check_warn "mv_bus_traffic_spatial" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM gold.mv_bus_traffic_spatial\" 2>/dev/null || echo 'migration 018 pas appliquee'"

check_warn "fn_network_health_score" "docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -tAc \"SELECT score || ' (' || diagnosis || ')' FROM gold.fn_network_health_score()\" 2>/dev/null || echo 'migration 019 pas appliquee'"

# 7. Endpoints HTTP
echo ""
echo "--- Endpoints HTTP ---"
check "Streamlit 8501" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8501/_stcore/health 2>/dev/null"
check "API 8000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null"
check "Grafana 3000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:3000/api/health 2>/dev/null"
check "MLflow 5000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:5000/health 2>/dev/null"

# 8. Airflow DAGs derniers runs
echo ""
echo "--- Airflow DAGs (last run) ---"
check_warn "collect_bronze_data" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d collect_bronze_data --limit 1 -o plain 2>/dev/null | tail -1 | awk '{print \$3, \$4}'"
check_warn "transform_silver_to_gold" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d transform_silver_to_gold --limit 1 -o plain 2>/dev/null | tail -1 | awk '{print \$3, \$4}'"
check_warn "dag_inference_xgboost" "docker exec lyonflow-airflow-scheduler airflow dags list-runs -d dag_inference_xgboost --limit 1 -o plain 2>/dev/null | tail -1 | awk '{print \$3, \$4}'"

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
