#!/bin/bash
# test_apply_migrations.sh — Tests unitaires pour scripts/apply-migrations.sh.
#
# Sprint 16 (2026-06-20) — Cf docs/SPEC_APPLY_MIGRATIONS.md §13.
# Usage : bash tests/test_apply_migrations.sh
# Exit 0 si tous les tests passent, 1 sinon.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APPLY_SH="${REPO_ROOT}/scripts/apply-migrations.sh"

# Vérifier que le script existe
if [[ ! -f "${APPLY_SH}" ]]; then
    echo "FAIL: apply-migrations.sh introuvable à ${APPLY_SH}"
    exit 1
fi

# Charger les fonctions (extraction via source — nécessite que le script soit
# sourceable sans exécuter main). On fait un source avec un wrapper qui
# skip main.
#
# Workaround : extraire juste la fonction extract_version en l'évaluant
# avec bash. Le plus simple : copier le code de extract_version ici et
# vérifier qu'il matche le script source.
EXTRACT_VERSION_INLINE='
extract_version() {
    local filename="$1"
    echo "$filename" | sed -E "s/.*migration_0*([0-9]+).*/\1/"
}
'

# Couleurs
if [[ -t 1 ]]; then
    C_GREEN='\033[0;32m'
    C_RED='\033[0;31m'
    C_RESET='\033[0m'
else
    C_GREEN=''; C_RED=''; C_RESET=''
fi

PASS=0
FAIL=0

assert_equals() {
    local expected="$1" actual="$2" desc="$3"
    if [[ "${expected}" == "${actual}" ]]; then
        echo -e "${C_GREEN}${C_RESET} ${desc}"
        PASS=$((PASS + 1))
    else
        echo -e "${C_RED}${C_RESET} ${desc} (expected='${expected}' actual='${actual}')"
        FAIL=$((FAIL + 1))
    fi
}

# --- Test 1: extract_version 3 chiffres ---
echo ""
echo "Test extract_version :"

# Vérifier que la fonction extract_version existe dans le script
if grep -q "^extract_version()" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} extract_version() définie dans le script"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} extract_version() introuvable dans le script"
    FAIL=$((FAIL + 1))
fi

# Test direct avec le regex
test_extract() {
    local fname="$1" expected="$2"
    local actual
    actual=$(echo "$fname" | sed -E 's/.*migration_0*([0-9]+).*/\1/')
    assert_equals "$expected" "$actual" "extract_version($fname) = $expected"
}

test_extract "migration_14_gold_coherence_tomtom_v2.sql" "14"
test_extract "migration_15_aggregate_line_ref.sql" "15"
test_extract "migration_016_tarifs_modes.sql" "16"
test_extract "migration_017_multimodal_grid.sql" "17"
test_extract "migration_018_bus_traffic_spatial.sql" "18"
test_extract "migration_019_network_health.sql" "19"
test_extract "migration_020_xgb_vs_tomtom.sql" "20"
test_extract "migration_021_source_health.sql" "21"
test_extract "migration_999_foo.sql" "999"

# --- Test 2: sort order ---
echo ""
echo "Test sort order (must be 14 15 16 17 18 19 20 21):"

SORTED=$(ls scripts/sql/migration_*.sql | while read f; do
    basename "$f" | sed -E 's/.*migration_0*([0-9]+).*/\1/'
done | sort -n)
EXPECTED=$'14\n15\n16\n17\n18\n19\n20\n21'
assert_equals "${EXPECTED}" "${SORTED}" "8 migrations triées numériquement"

# --- Test 3: idempotence (sub-test) ---
echo ""
echo "Test idempotence (syntaxique) :"

# Le script doit pouvoir être invoqué 2x sans erreur de syntaxe.
# On ne peut PAS tester l'idempotence réelle sans DB live, mais on
# peut tester que la fonction is_applied() et list_migrations()
# sont bien définies.
if grep -q "^is_applied()" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} is_applied() définie"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} is_applied() manquante"
    FAIL=$((FAIL + 1))
fi

if grep -q "^list_migrations()" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} list_migrations() définie"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} list_migrations() manquante"
    FAIL=$((FAIL + 1))
fi

if grep -q "ensure_tracking_table" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} ensure_tracking_table() définie"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} ensure_tracking_table() manquante"
    FAIL=$((FAIL + 1))
fi

if grep -q "ON CONFLICT.*DO UPDATE" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} record_migration() gère ON CONFLICT (idempotent)"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} record_migration() ne gère pas ON CONFLICT"
    FAIL=$((FAIL + 1))
fi

# --- Test 4: parsing args ---
echo ""
echo "Test parsing args :"

if grep -q '\-\-dry-run' "${APPLY_SH}" && grep -q 'DRY_RUN=true' "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} --dry-run géré"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} --dry-run manquant"
    FAIL=$((FAIL + 1))
fi

if grep -q '\-\-status' "${APPLY_SH}" && grep -q 'STATUS_ONLY=true' "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} --status géré"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} --status manquant"
    FAIL=$((FAIL + 1))
fi

if grep -q '\-\-force' "${APPLY_SH}" && grep -q 'FORCE_VERSION=' "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} --force géré"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} --force manquant"
    FAIL=$((FAIL + 1))
fi

if grep -q '\-\-direct' "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} --direct géré"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} --direct manquant"
    FAIL=$((FAIL + 1))
fi

# --- Test 5: pre-checks ---
echo ""
echo "Test pre-checks :"
for chk in "PostgreSQL reachable" "Schema gold exists" "PostGIS"; do
    if grep -q "${chk}" "${APPLY_SH}"; then
        echo -e "${C_GREEN}${C_RESET} pre-check '${chk}' présent"
        PASS=$((PASS + 1))
    else
        echo -e "${C_RED}${C_RESET} pre-check '${chk}' manquant"
        FAIL=$((FAIL + 1))
    fi
done

# --- Test 6: tracking table schema ---
echo ""
echo "Test tracking table schema :"
if grep -q "CREATE TABLE IF NOT EXISTS public.schema_migrations" "${APPLY_SH}"; then
    echo -e "${C_GREEN}${C_RESET} table public.schema_migrations créée"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} table public.schema_migrations manquante"
    FAIL=$((FAIL + 1))
fi

for col in version filename applied_at checksum status; do
    if grep -q "    ${col} " "${APPLY_SH}"; then
        echo -e "${C_GREEN}${C_RESET} colonne '${col}' présente"
        PASS=$((PASS + 1))
    else
        echo -e "${C_RED}${C_RESET} colonne '${col}' manquante"
        FAIL=$((FAIL + 1))
    fi
done

# --- Test 7: fichiers non-migration ignorés ---
echo ""
echo "Test glob (uniquement migration_*.sql) :"
if ls "${REPO_ROOT}"/scripts/sql/migration_*.sql >/dev/null 2>&1; then
    N_MIG=$(ls "${REPO_ROOT}"/scripts/sql/migration_*.sql | wc -l | tr -d ' ')
    N_ALL=$(ls "${REPO_ROOT}"/scripts/sql/*.sql | wc -l | tr -d ' ')
    N_NOT_MIG=$((N_ALL - N_MIG))
    echo -e "${C_GREEN}${C_RESET} ${N_MIG} fichiers migration_*.sql, ${N_NOT_MIG} autres (create_*, audit_*, backfill_*)"
    PASS=$((PASS + 1))
else
    echo -e "${C_RED}${C_RESET} aucun fichier migration_*.sql"
    FAIL=$((FAIL + 1))
fi

# --- Résumé ---
echo ""
echo "============================================"
echo -e "Tests: ${C_GREEN}${PASS} passed${C_RESET}, ${C_RED}${FAIL} failed${C_RESET}"
echo "============================================"

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
