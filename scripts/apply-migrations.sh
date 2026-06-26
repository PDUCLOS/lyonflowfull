#!/bin/bash
# apply-migrations.sh — Applique les migrations SQL dans l'ordre.
#
# Sprint 16 (2026-06-20) — Spec docs/SPEC_APPLY_MIGRATIONS.md.
# Usage : voir ./apply-migrations.sh --help
#
# Modes :
#   (défaut)        Applique les migrations pendantes
#   --dry-run       Liste les migrations pendantes sans les appliquer
#   --status        Affiche applied vs pending
#   --force <N>     Force la ré-application de la migration N
#   --direct        Connexion psql native (pas docker exec)
#
# Variables env : POSTGRES_USER, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD,
# DOCKER_CONTAINER (défaut lyonflow-postgres), MIGRATIONS_DIR (défaut scripts/sql).

set -euo pipefail

# --- Constantes ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-${REPO_ROOT}/scripts/sql}"
DOCKER_CONTAINER="${DOCKER_CONTAINER:-lyonflow-postgres}"
POSTGRES_USER="${POSTGRES_USER:-lyonflow}"
POSTGRES_DB="${POSTGRES_DB:-lyonflow}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"

# Couleurs (si terminal)
if [[ -t 1 ]]; then
    C_GREEN='\033[0;32m'
    C_YELLOW='\033[0;33m'
    C_RED='\033[0;31m'
    C_BLUE='\033[0;34m'
    C_GRAY='\033[0;90m'
    C_RESET='\033[0m'
else
    C_GREEN=''; C_YELLOW=''; C_RED=''; C_BLUE=''; C_GRAY=''; C_RESET=''
fi

# --- Parse args ---
DRY_RUN=false
DIRECT=false
STATUS_ONLY=false
FORCE_VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --status) STATUS_ONLY=true; shift ;;
        --force) FORCE_VERSION="$2"; shift 2 ;;
        --direct) DIRECT=true; shift ;;
        -h|--help)
            grep -E "^#" "$0" | sed 's/^# *//'
            exit 0
            ;;
        *) echo -e "${C_RED}Unknown option: $1${C_RESET}" >&2; exit 1 ;;
    esac
done

# --- Fonctions utilitaires ---

log()  { echo -e "$@"; }
ok()   { log "${C_GREEN}✅${C_RESET} $*"; }
warn() { log "${C_YELLOW}⚠${C_RESET}  $*"; }
err()  { log "${C_RED}❌${C_RESET} $*"; }
info() { log "${C_BLUE}ℹ${C_RESET}  $*"; }

die() { err "$*"; exit 1; }

extract_version() {
    # Extrait le numéro de version du filename, gère 2 et 3 chiffres.
    # migration_14_xxx.sql → 14
    # migration_016_xxx.sql → 16
    local filename="$1"
    echo "$filename" | sed -E 's/.*migration_0*([0-9]+).*/\1/'
}

sha256_file() {
    # SHA-256 d'un fichier, cross-platform (BSD sur macOS, GNU sur Linux).
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# --- Connexion psql (docker ou direct) ---

psql_exec() {
    # Exécute le SQL reçu sur stdin. Retourne le code retour de psql.
    if [[ "${DIRECT}" == "true" ]]; then
        if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
            die "POSTGRES_PASSWORD required in --direct mode"
        fi
        PGPASSWORD="${POSTGRES_PASSWORD}" psql \
            -h "${POSTGRES_HOST}" \
            -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" \
            -v ON_ERROR_STOP=1 \
            "$@"
    else
        docker exec -i "${DOCKER_CONTAINER}" \
            psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 "$@"
    fi
}

psql_query() {
    # Query qui retourne 1 ligne 1 colonne, sans header.
    psql_exec -t -A -c "$1"
}

# --- Pré-checks ---

pre_checks() {
    info "Pre-checks..."

    # 1. PostgreSQL reachable
    if ! psql_query "SELECT 1" >/dev/null 2>&1; then
        die "PostgreSQL unreachable (container=${DOCKER_CONTAINER}, mode=$( [[ "${DIRECT}" == "true" ]] && echo direct || echo docker ))"
    fi
    ok "PostgreSQL reachable"

    # 2. Schema gold exists
    local gold_count
    gold_count=$(psql_query "SELECT count(*) FROM pg_namespace WHERE nspname='gold'" 2>/dev/null || echo "0")
    if [[ "${gold_count}" != "1" ]]; then
        die "Schema 'gold' does not exist (got count=${gold_count}). Run init-db.sql first."
    fi
    ok "Schema gold exists"

    # 3. PostGIS installed (requis par migrations 017, 018)
    local postgis_ver
    postgis_ver=$(psql_query "SELECT PostGIS_version()" 2>/dev/null || echo "")
    if [[ -z "${postgis_ver}" ]]; then
        warn "PostGIS not installed — spatial migrations (017, 018) may fail"
    else
        ok "PostGIS ${postgis_ver} installed"
    fi
}

# --- Tracking table ---

ensure_tracking_table() {
    psql_exec <<'SQL' >/dev/null
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    status      TEXT NOT NULL DEFAULT 'applied'
);
COMMENT ON TABLE public.schema_migrations IS
    'Tracking des migrations SQL appliquées. Utilisé par scripts/apply-migrations.sh.';

-- Migration depuis une version antérieure (2 colonnes: version, applied_at).
-- ADD COLUMN IF NOT EXISTS est safe (no-op si déjà présente).
ALTER TABLE public.schema_migrations ADD COLUMN IF NOT EXISTS filename TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE public.schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT;
ALTER TABLE public.schema_migrations ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'applied';
SQL
}

is_applied() {
    local version="$1"
    local status
    status=$(psql_query "SELECT status FROM public.schema_migrations WHERE version=$version" 2>/dev/null || echo "")
    [[ "${status}" == "applied" ]]
}

get_checksum() {
    local version="$1"
    psql_query "SELECT checksum FROM public.schema_migrations WHERE version=$version" 2>/dev/null || echo ""
}

record_migration() {
    local version="$1" filename="$2" checksum="$3" status="$4"
    psql_exec <<SQL >/dev/null
INSERT INTO public.schema_migrations (version, filename, checksum, status)
VALUES ($version, '$filename', '$checksum', '$status')
ON CONFLICT (version) DO UPDATE SET
    filename = EXCLUDED.filename,
    checksum = EXCLUDED.checksum,
    status   = EXCLUDED.status,
    applied_at = NOW();
SQL
}

# --- Liste et tri des migrations ---

list_migrations() {
    # Glob les fichiers migration_*.sql, retourne "version filename" trié par version.
    if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
        die "Migrations dir not found: ${MIGRATIONS_DIR}"
    fi
    # Écrire les lignes dans une variable, puis echo une par une (évite
    # les bugs de scope local/subshell avec `for file in ... | sort`).
    local file
    local -a lines
    for file in "${MIGRATIONS_DIR}"/migration_*.sql; do
        [[ -f "$file" ]] || continue
        local v
        v=$(extract_version "$(basename "$file")")
        lines+=("${v}|${file}")
    done
    # Sort et print
    printf '%s\n' "${lines[@]}" | sort -t'|' -k1 -n
}

# --- Mode --status ---

do_status() {
    log ""
    log "${C_BLUE}📋 Migration status for ${POSTGRES_USER}@${POSTGRES_DB}:${C_RESET}"
    log ""

    local counts_applied=0 counts_pending=0 counts_failed=0
    local v file fname applied_at prev_status
    # Workaround : on lit la sortie de list_migrations dans un array (évite
    # les bugs de `while ... done` avec set -euo pipefail + subshell scope).
    local -a mig_lines
    while IFS= read -r line; do
        mig_lines+=("$line")
    done < <(list_migrations)
    for line in "${mig_lines[@]}"; do
        v="${line%%|*}"
        file="${line#*|}"
        [[ -z "$v" ]] && continue
        fname=$(basename "$file")
        if is_applied "$v"; then
            applied_at=$(psql_query "SELECT to_char(applied_at, 'YYYY-MM-DD HH24:MI') FROM public.schema_migrations WHERE version=$v" 2>/dev/null || echo "?")
            printf "  ✅  %03d  %-50s (applied %s)\n" "$v" "$fname" "$applied_at"
            counts_applied=$((counts_applied + 1))
        else
            prev_status=$(psql_query "SELECT status FROM public.schema_migrations WHERE version=$v" 2>/dev/null || echo "")
            if [[ "${prev_status}" == "failed" ]]; then
                printf "  ❌  %03d  %-50s (FAILED — re-run with --force %d)\n" "$v" "$fname" "$v"
                counts_failed=$((counts_failed + 1))
            else
                printf "  🔜  %03d  %-50s (pending)\n" "$v" "$fname"
                counts_pending=$((counts_pending + 1))
            fi
        fi
    done

    log ""
    log "${C_BLUE}Summary${C_RESET}: ${C_GREEN}${counts_applied} applied${C_RESET}, ${C_YELLOW}${counts_pending} pending${C_RESET}, ${C_RED}${counts_failed} failed${C_RESET}"
}

# --- Boucle principale d'application ---

do_apply() {
    local n_applied=0 n_skipped=0 n_failed=0
    local v file fname checksum stored_checksum start_t end_t
    # Workaround : array au lieu de `while` (cf do_status)
    local -a mig_lines
    while IFS= read -r line; do
        mig_lines+=("$line")
    done < <(list_migrations)
    for line in "${mig_lines[@]}"; do
        v="${line%%|*}"
        file="${line#*|}"
        [[ -z "$v" ]] && continue
        fname=$(basename "$file")
        checksum=$(sha256_file "$file")

        # Skip si déjà appliquée (sauf --force)
        if is_applied "$v" && [[ -z "${FORCE_VERSION}" || "${FORCE_VERSION}" != "$v" ]]; then
            # Vérifier checksum (warning, pas bloquant)
            stored_checksum=$(get_checksum "$v")
            if [[ -n "${stored_checksum}" && "${stored_checksum}" != "${checksum}" ]]; then
                warn "Migration $v checksum changed (was ${stored_checksum:0:8}, now ${checksum:0:8})"
                log "  ${C_GRAY}→ File modified after initial application. Idempotent, no-op expected.${C_RESET}"
                log "  ${C_GRAY}→ To re-apply: $0 --force $v${C_RESET}"
            else
                info "⏭  Skip $fname (already applied)"
            fi
            n_skipped=$((n_skipped + 1))
            continue
        fi

        # Dry-run
        if [[ "${DRY_RUN}" == "true" ]]; then
            log "${C_BLUE}🔜 Would apply${C_RESET}: $fname (version $v)"
            continue
        fi

        # Appliquer
        info "🔄 Applying $fname..."
        start_t=$(date +%s)
        if psql_exec < "$file" >/dev/null 2>&1; then
            record_migration "$v" "$fname" "$checksum" "applied"
            end_t=$(date +%s)
            ok "  $fname applied ($((end_t - start_t))s)"
            n_applied=$((n_applied + 1))
        else
            record_migration "$v" "$fname" "$checksum" "failed"
            err "  $fname FAILED — stopping"
            err ""
            err "Fix the SQL, then re-run with: $0 --force $v"
            n_failed=$((n_failed + 1))
            return 1
        fi
    done

    log ""
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "${C_BLUE}ℹ Dry-run complete.${C_RESET}"
    else
        log "${C_GREEN}✅ Done${C_RESET}: ${C_GREEN}${n_applied} applied${C_RESET}, ${C_GRAY}${n_skipped} skipped${C_RESET}, ${C_RED}${n_failed} failed${C_RESET}"
    fi
}

# --- Main ---

main() {
    log "${C_BLUE}🔧 LyonFlow — SQL Migration Runner${C_RESET}"
    log "  Target: $( [[ "${DIRECT}" == "true" ]] && echo "${POSTGRES_HOST}:5432" || echo "${DOCKER_CONTAINER}" ) / ${POSTGRES_DB}"
    log "  Migrations dir: ${MIGRATIONS_DIR}"

    # Ensure table tracking + pre-checks
    ensure_tracking_table
    pre_checks
    log ""

    if [[ "${STATUS_ONLY}" == "true" ]]; then
        do_status
    else
        do_apply
    fi
}

main "$@"
