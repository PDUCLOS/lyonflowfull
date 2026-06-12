#!/bin/bash
# Healthcheck post-redémarrage VPS - Sprint 8+4 (2026-06-12)
# Vérifie que tous les piliers sont up après un restart Docker.
# Exit code 0 = tout OK, 1 = problème détecté.

set -uo pipefail

VPS_USER="ubuntu"
VPS_HOST="51.83.159.224"
SSH_KEY="$HOME/.ssh/lyonflow_deploy"
SSH_OPTS="-i $SSH_KEY -o IdentitiesOnly=yes -o ConnectTimeout=10"

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok=0
warn=0
fail=0

ssh_run() {
    ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "$1" 2>&1
}

check() {
    local label="$1"
    local cmd="$2"
    local result
    result=$(ssh_run "$cmd")
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        echo -e "${GREEN}✓${NC} $label: $result"
        ((ok++))
    else
        echo -e "${RED}✗${NC} $label: FAILED ($result)"
        ((fail++))
    fi
}

echo "=== LyonFlow VPS Healthcheck (Sprint 8+4) ==="
echo ""

# 1. Containers
echo "--- Containers ---"
for svc in postgres streamlit airflow-scheduler airflow-worker api mlflow grafana prometheus; do
    status=$(ssh_run "docker ps --format '{{.Status}}' --filter name=$svc 2>/dev/null | head -1")
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
echo "--- Disque sda1 (/opt) ---"
check "sda1 %used" "df /opt | tail -1 | awk '{print \$5}'"
check "free (Go)" "df /opt | tail -1 | awk '{print int(\$4/1024/1024)}'"

# 3. CPU/RAM
echo ""
echo "--- Load / RAM ---"
check "load 1min" "uptime | awk -F'load average:' '{print \$2}' | awk -F',' '{print \$1}'"
check "mem free" "free -h | grep Mem | awk '{print \$7}'"

# 4. DB & tables critiques (via psql direct dans le container)
echo ""
echo "--- DB Health ---"
check "PG responsive" "cd /opt/lyonflow && docker compose exec -T postgres pg_isready -U lyonflow 2>&1 | head -1"

# dim_spatial lat/lon (via Python pour éviter quoting SQL)
check "dim_spatial lat/lon" "cd /opt/lyonflow && docker compose exec -T postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) || '/' || count(lat) || ' lat OK' FROM gold.dim_spatial_grid_mapping\""

# Counts 1h (silver)
check "velov_clean 1h" "cd /opt/lyonflow && docker compose exec -T postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.velov_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'\""
# Sprint 8+4 : trafics_boucles_clean et tcl_vehicles_clean ont silver_updated_at
# (pas transformed_at — c'était l'ancien nom de colonne, renommé en Sprint 5).
check "trafic_boucles 1h" "cd /opt/lyonflow && docker compose exec -T postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.trafic_boucles_clean WHERE silver_updated_at > NOW() - INTERVAL '1 hour'\""
check "tcl_vehicles 1h" "cd /opt/lyonflow && docker compose exec -T postgres psql -U lyonflow -d lyonflow -tAc \"SELECT count(*) FROM silver.tcl_vehicles_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'\""

# 5. Endpoints HTTP
echo ""
echo "--- Endpoints HTTP ---"
check "Streamlit 8501" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8501/_stcore/health 2>/dev/null"
check "API 8000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null"
check "Grafana 3000" "curl -sk -o /dev/null -w '%{http_code}' http://localhost:3000/api/health 2>/dev/null"

# Résumé
echo ""
echo "=== Résumé ==="
echo -e "${GREEN}OK: $ok${NC} | ${YELLOW}WARN: $warn${NC} | ${RED}FAIL: $fail${NC}"

if [ $fail -gt 0 ]; then
    echo -e "${RED}⚠️  Healthcheck FAILED - investiguer les ✗ ci-dessus${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Healthcheck OK${NC}"
exit 0
