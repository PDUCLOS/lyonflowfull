#!/bin/bash
# Coherence check — Sprint 13 (2026-06-18)
# Verifie les invariants du code (version, zero-mock, auto-refresh, imports).
# Usage : ./scripts/coherence-check.sh  ou  make coherence-check
# Exit code 0 = tout OK, 1 = probleme detecte.

set -uo pipefail

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
    if [ -z "$result" ]; then
        printf "${GREEN}OK${NC} %s\n" "$label"
        ((ok++))
    else
        printf "${RED}FAIL${NC} %s\n" "$label"
        echo "$result" | head -10 | sed 's/^/    /'
        ((fail++))
    fi
}

check_warn() {
    local label="$1"
    local result
    result=$(eval "$2" 2>&1)
    if [ -z "$result" ]; then
        printf "${GREEN}OK${NC} %s\n" "$label"
        ((ok++))
    else
        printf "${YELLOW}WARN${NC} %s\n" "$label"
        echo "$result" | head -5 | sed 's/^/    /'
        ((warn++))
    fi
}

echo "=== LyonFlow Coherence Check ==="
echo ""

# --- 1. Version unique ---
echo "--- Version ---"
check "config.py version = 0.6.6" \
    "python -c 'from src.config import get_settings; s = get_settings(); assert s.app_version == \"0.6.6\", f\"got {s.app_version}\"' 2>&1 | grep -v WARNING"

check "No hardcoded versions in dashboard" \
    "grep -rn 'v0\.3\.\|v0\.6\.1\|v0\.6\.x' dashboard/ --include='*.py'"

check "pyproject.toml version = 0.6.6" \
    "grep -q 'version = \"0.6.6\"' pyproject.toml || echo 'pyproject.toml version mismatch'"

echo ""

# --- 2. Zero mock ---
echo "--- Zero Mock ---"
check "No force_mock in non-test code" \
    "grep -rn 'force_mock' --include='*.py' . | grep -v tests/ | grep -v __pycache__ | grep -v '.pyc'"

check "No src.data.mock imports" \
    "grep -rn 'from src\.data\.mock' --include='*.py' . | grep -v tests/ | grep -v __pycache__"

check_warn "No 'mock data' or 'fallback mock' in dashboard" \
    "grep -rn 'mock data\|fallback mock' dashboard/ --include='*.py'"

check "No _is_demo_mode in data_loader" \
    "grep -n '_is_demo_mode\|_maybe_force_mock' src/data/data_loader.py"

echo ""

# --- 3. Auto-refresh ---
echo "--- Auto-refresh ---"
PAGES_WITHOUT_REFRESH=""
for page in dashboard/pages/{Pro,Elu,Usager}_*.py dashboard/pages/9_RGPD_Conformite.py dashboard/pages/A_Propos.py; do
    if [ -f "$page" ] && ! grep -q "setup_auto_refresh" "$page"; then
        PAGES_WITHOUT_REFRESH="$PAGES_WITHOUT_REFRESH\n    $(basename $page)"
    fi
done
if [ -z "$PAGES_WITHOUT_REFRESH" ]; then
    printf "${GREEN}OK${NC} All pages have setup_auto_refresh()\n"
    ((ok++))
else
    printf "${RED}FAIL${NC} Pages missing setup_auto_refresh():\n"
    echo -e "$PAGES_WITHOUT_REFRESH"
    ((fail++))
fi

echo ""

# --- 4. Cross-persona imports ---
echo "--- Cross-persona imports ---"
check "No Usager pages importing from widgets/pro_tcl/" \
    "grep -rn 'from dashboard.components.widgets.pro_tcl' dashboard/pages/Usager_*.py"

check "No Usager pages importing from widgets/elu/" \
    "grep -rn 'from dashboard.components.widgets.elu' dashboard/pages/Usager_*.py"

check "No Elu pages importing from widgets/pro_tcl/" \
    "grep -rn 'from dashboard.components.widgets.pro_tcl' dashboard/pages/Elu_*.py"

echo ""

# --- 5. TTL coherence ---
echo "--- TTL coherence ---"
check_warn "data_cache TTL_REALTIME <= 30s (Pro TCL refresh)" \
    "python -c \"
from dashboard.components.data_cache import TTL_REALTIME
assert TTL_REALTIME <= 30, f'TTL_REALTIME={TTL_REALTIME} > 30s Pro TCL refresh'
\" 2>&1 | grep -v WARNING"

echo ""

# --- Summary ---
total=$((ok + warn + fail))
echo "=== $ok/$total OK, $warn warnings, $fail failures ==="

if [ $fail -gt 0 ]; then
    exit 1
fi
exit 0
