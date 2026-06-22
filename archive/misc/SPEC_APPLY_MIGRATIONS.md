# SPEC — `scripts/apply-migrations.sh`

> **Date** : 2026-06-20  
> **Contexte** : Sprint 16 — 8 migrations SQL (014-021) à appliquer sur VPS  
> **Priorité** : bloquant déploiement (rien du Sprint 15+/16 ne tourne sans les vues Gold)

---

## 1. Problème

8 fichiers SQL dans `scripts/sql/migration_*.sql`. Aucun mécanisme pour :
- Savoir lesquels sont déjà appliqués sur le VPS
- Les appliquer dans l'ordre
- Détecter un échec et stopper avant de corrompre l'état
- Rejouer une migration ratée sans tout casser

Aujourd'hui : copier-coller manuel dans `psql` via SSH. Fragile, non traçable.

---

## 2. Inventaire des migrations

| Fichier | Sprint | Contenu | Idempotent |
|---------|--------|---------|------------|
| `migration_14_gold_coherence_tomtom_v2.sql` | 13+ | Vues `gold.v_coherence_tomtom_vs_grandlyon` + `gold.v_tomtom_gl_drift` | ✅ CREATE OR REPLACE |
| `migration_15_aggregate_line_ref.sql` | 15 | Agrégation `line_ref` pour KPIs TCL | ✅ CREATE OR REPLACE |
| `migration_016_tarifs_modes.sql` | 15+ | Table `gold.tarifs_modes` + seed data | ✅ IF NOT EXISTS + ON CONFLICT |
| `migration_017_multimodal_grid.sql` | 15+ | Vue matérialisée `gold.mv_multimodal_grid` | ✅ IF NOT EXISTS |
| `migration_018_bus_traffic_spatial.sql` | 15+ | Vue matérialisée `gold.mv_bus_traffic_spatial` | ✅ IF NOT EXISTS |
| `migration_019_network_health.sql` | 15+ | Fonction `gold.fn_network_health_score()` | ✅ CREATE OR REPLACE |
| `migration_020_xgb_vs_tomtom.sql` | 16 | Vue matérialisée `gold.mv_xgb_vs_tomtom` + vue `gold.v_xgb_accuracy_summary` + table `gold.model_drift_reports` | ✅ IF NOT EXISTS |
| `migration_021_source_health.sql` | 16 | Vue `gold.v_source_health` + tables monitoring | ✅ IF NOT EXISTS |

**Toutes les migrations sont idempotentes** (CREATE IF NOT EXISTS, CREATE OR REPLACE, ON CONFLICT DO NOTHING). Re-exécuter une migration déjà appliquée = no-op.

---

## 3. Design du script

### 3.1. Principes

1. **Table de tracking** : `public.schema_migrations(version INT, filename TEXT, applied_at TIMESTAMPTZ, checksum TEXT)`. Crée automatiquement si absente.
2. **Ordre strict** : tri numérique sur le numéro de version (14, 15, 016, 017...).
3. **Skip si déjà appliqué** : vérifie `version` dans `schema_migrations` avant exécution.
4. **Transaction par migration** : chaque fichier dans un `BEGIN ... COMMIT`. Si erreur → `ROLLBACK` + stop.
5. **Checksum SHA-256** : stocké à l'application. Si le fichier change après application → warning (pas de blocage, les migrations sont idempotentes).
6. **Dry-run** : `--dry-run` montre ce qui serait appliqué sans toucher la DB.
7. **Exécution locale ou VPS** : fonctionne via `docker exec` (VPS) ou connexion directe (local).

### 3.2. Modes d'exécution

```bash
# Sur le VPS (via docker exec)
./scripts/apply-migrations.sh

# Dry-run (liste les migrations pendantes)
./scripts/apply-migrations.sh --dry-run

# Forcer une migration spécifique (re-apply)
./scripts/apply-migrations.sh --force 020

# Connexion directe (pas de Docker)
./scripts/apply-migrations.sh --direct

# Statut uniquement (montre applied vs pending)
./scripts/apply-migrations.sh --status
```

### 3.3. Variables d'environnement

| Variable | Défaut | Usage |
|----------|--------|-------|
| `POSTGRES_USER` | `lyonflow` | DB user |
| `POSTGRES_DB` | `lyonflow` | DB name |
| `POSTGRES_HOST` | `localhost` | DB host (mode `--direct`) |
| `POSTGRES_PASSWORD` | (requis en mode `--direct`) | DB password |
| `DOCKER_CONTAINER` | `lyonflow-postgres` | Container PostgreSQL (mode docker) |
| `MIGRATIONS_DIR` | `scripts/sql` | Répertoire des fichiers SQL |

---

## 4. Pseudo-code

```bash
#!/bin/bash
# apply-migrations.sh — Applique les migrations SQL dans l'ordre
set -euo pipefail

MIGRATIONS_DIR="${MIGRATIONS_DIR:-scripts/sql}"
DOCKER_CONTAINER="${DOCKER_CONTAINER:-lyonflow-postgres}"
POSTGRES_USER="${POSTGRES_USER:-lyonflow}"
POSTGRES_DB="${POSTGRES_DB:-lyonflow}"
DRY_RUN=false
DIRECT=false
STATUS_ONLY=false
FORCE_VERSION=""

# --- Parse args ---
# --dry-run, --direct, --status, --force <N>

# --- Fonction psql_exec ---
# Mode docker : docker exec -i $DOCKER_CONTAINER psql -U $POSTGRES_USER -d $POSTGRES_DB
# Mode direct : PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB

# --- 1. Créer table tracking si absente ---
psql_exec <<'SQL'
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    status      TEXT NOT NULL DEFAULT 'applied'  -- 'applied' | 'failed'
);
SQL

# --- 2. Lister migrations disponibles ---
# Glob : migration_*.sql, tri par numéro de version extrait du filename
# Regex : migration_(\d+)_ → version = $1

# --- 3. Pour chaque migration (triée par version) ---
for file in sorted_migrations; do
    version = extract_version(file)
    
    # Skip si déjà appliquée (sauf --force)
    if already_applied(version) && ! force; then
        # Vérifier checksum
        stored_checksum = get_stored_checksum(version)
        current_checksum = sha256sum(file)
        if stored_checksum != current_checksum; then
            warn "⚠ Migration $version checksum changed since application"
        fi
        echo "⏭ Skip $file (already applied)"
        continue
    fi
    
    if dry_run; then
        echo "🔜 Would apply: $file (version $version)"
        continue
    fi
    
    # Appliquer dans une transaction
    echo "🔄 Applying $file..."
    if psql_exec < "$file"; then
        # Enregistrer dans schema_migrations
        record_migration(version, file, checksum, 'applied')
        echo "✅ $file applied successfully"
    else
        record_migration(version, file, checksum, 'failed')
        echo "❌ $file FAILED — stopping"
        exit 1
    fi
done

# --- 4. Résumé ---
echo "Applied: N | Skipped: M | Pending: P"
```

---

## 5. Extraction du numéro de version

Problème : nommage incohérent (`migration_14_...`, `migration_016_...`).

```bash
extract_version() {
    local filename="$1"
    # Extrait le premier groupe de chiffres après "migration_"
    echo "$filename" | sed -E 's/.*migration_0*([0-9]+).*/\1/'
}
```

| Fichier | Version extraite |
|---------|-----------------|
| `migration_14_gold_coherence_tomtom_v2.sql` | 14 |
| `migration_15_aggregate_line_ref.sql` | 15 |
| `migration_016_tarifs_modes.sql` | 16 |
| `migration_017_multimodal_grid.sql` | 17 |
| `migration_018_bus_traffic_spatial.sql` | 18 |
| `migration_019_network_health.sql` | 19 |
| `migration_020_xgb_vs_tomtom.sql` | 20 |
| `migration_021_source_health.sql` | 21 |

Tri numérique → `sort -n` → ordre garanti 14, 15, 16, 17, 18, 19, 20, 21.

---

## 6. Table `public.schema_migrations`

```sql
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    status      TEXT NOT NULL DEFAULT 'applied'
);

COMMENT ON TABLE public.schema_migrations IS
    'Tracking des migrations SQL appliquées. Utilisé par scripts/apply-migrations.sh.';
```

Exemple après application complète :

```
 version |                   filename                    |        applied_at         |   checksum   | status
---------+----------------------------------------------+---------------------------+--------------+---------
      14 | migration_14_gold_coherence_tomtom_v2.sql     | 2026-06-20 14:30:12+00    | a3f2c8...    | applied
      15 | migration_15_aggregate_line_ref.sql           | 2026-06-20 14:30:14+00    | 7b1e9d...    | applied
      16 | migration_016_tarifs_modes.sql                | 2026-06-20 14:30:15+00    | e4d6a1...    | applied
      ...
```

---

## 7. Gestion des erreurs

### 7.1. Migration échoue

```
🔄 Applying migration_020_xgb_vs_tomtom.sql...
ERROR:  relation "gold.mv_xgb_vs_tomtom" already exists
❌ migration_020_xgb_vs_tomtom.sql FAILED — stopping

Status: version 020 recorded as 'failed' in schema_migrations.
Fix the SQL, then re-run with: ./scripts/apply-migrations.sh --force 020
```

Le script **s'arrête immédiatement**. Les migrations suivantes ne sont PAS appliquées (elles pourraient dépendre de celle qui a échoué).

### 7.2. Checksum mismatch

```
⏭ Skip migration_017_multimodal_grid.sql (already applied)
  ⚠ WARNING: file checksum changed since application (was a3f2c8, now 9e1b7d)
  → File was modified after initial application. This is OK if the migration is idempotent.
  → To re-apply: ./scripts/apply-migrations.sh --force 017
```

Warning seulement — pas bloquant. Toutes les migrations sont idempotentes.

### 7.3. Pré-checks

Avant d'appliquer quoi que ce soit :

```bash
# 1. Vérifier que PostgreSQL répond
psql_exec -c "SELECT 1" || die "PostgreSQL unreachable"

# 2. Vérifier que le schéma gold existe
psql_exec -c "SELECT 1 FROM pg_namespace WHERE nspname = 'gold'" || die "Schema gold missing"

# 3. Vérifier que PostGIS est installé (requis par 017, 018)
psql_exec -c "SELECT PostGIS_version()" || warn "PostGIS not installed — spatial migrations may fail"
```

---

## 8. Intégration Makefile

```makefile
# Migrations SQL
migrate:
	./scripts/apply-migrations.sh

migrate-dry-run:
	./scripts/apply-migrations.sh --dry-run

migrate-status:
	./scripts/apply-migrations.sh --status

migrate-force:
	@read -p "Version to force-apply: " v && ./scripts/apply-migrations.sh --force $$v
```

---

## 9. Intégration déploiement

Dans `make deploy-vps` (ou `scripts/deploy-vps.sh`), ajouter après `rsync` + `systemctl restart` :

```bash
# Appliquer les migrations pendantes
echo "📦 Applying pending SQL migrations..."
ssh lyonflow@51.83.159.224 "cd /opt/lyonflow && ./scripts/apply-migrations.sh"
```

Séquence déploiement complète :

```
1. make check-deploy-env      # vérifie .deploy.env
2. rsync → VPS                # sync code
3. apply-migrations.sh        # ← NOUVEAU : SQL avant restart
4. docker-compose up -d       # restart containers
5. healthcheck-vps.sh         # vérifie que tout tourne
```

**Migrations AVANT restart containers** : les vues Gold doivent exister avant que les DAGs essaient de les lire.

---

## 10. Output attendu

### `--status`

```
📋 Migration status for lyonflow@lyonflow-postgres:

  ✅ 014  migration_14_gold_coherence_tomtom_v2.sql     (applied 2026-06-18 15:30)
  ✅ 015  migration_15_aggregate_line_ref.sql           (applied 2026-06-19 10:00)
  🔜 016  migration_016_tarifs_modes.sql                (pending)
  🔜 017  migration_017_multimodal_grid.sql             (pending)
  🔜 018  migration_018_bus_traffic_spatial.sql          (pending)
  🔜 019  migration_019_network_health.sql              (pending)
  🔜 020  migration_020_xgb_vs_tomtom.sql               (pending)
  🔜 021  migration_021_source_health.sql               (pending)

Summary: 2 applied, 6 pending
```

### Exécution normale

```
🔧 LyonFlowFull — SQL Migration Runner
  Target: lyonflow-postgres / lyonflow
  Migrations dir: scripts/sql (8 files)

Pre-checks:
  ✅ PostgreSQL reachable
  ✅ Schema gold exists
  ✅ PostGIS 3.4.0 installed

⏭ 014  migration_14_gold_coherence_tomtom_v2.sql     (already applied)
⏭ 015  migration_15_aggregate_line_ref.sql           (already applied)
🔄 016  migration_016_tarifs_modes.sql...             ✅ applied (0.3s)
🔄 017  migration_017_multimodal_grid.sql...          ✅ applied (1.2s)
🔄 018  migration_018_bus_traffic_spatial.sql...      ✅ applied (0.8s)
🔄 019  migration_019_network_health.sql...           ✅ applied (0.4s)
🔄 020  migration_020_xgb_vs_tomtom.sql...            ✅ applied (2.1s)
🔄 021  migration_021_source_health.sql...            ✅ applied (1.5s)

✅ Done: 6 applied, 2 skipped, 0 failed (6.3s total)
```

---

## 11. Convention nommage futures migrations

```
migration_NNN_description_courte.sql
```

- `NNN` : **3 chiffres, zero-padded** (022, 023, ...). Les anciens (14, 15) gardent leur nommage.
- Description : snake_case, max 40 caractères
- Chaque fichier **doit être idempotent** : `CREATE IF NOT EXISTS`, `CREATE OR REPLACE`, `ON CONFLICT DO NOTHING`
- Chaque fichier **doit être wrappé** dans `BEGIN; ... COMMIT;` (transaction)
- Header standard :

```sql
-- =============================================================================
-- LyonFlowFull — Migration NNN (Sprint XX, YYYY-MM-DD)
-- =============================================================================
-- Description courte.
-- Idempotent : <méthode>.
-- =============================================================================

BEGIN;

-- ... contenu ...

COMMIT;
```

---

## 12. Fichiers non-migration dans `scripts/sql/`

Les fichiers suivants ne sont PAS des migrations (pas de préfixe `migration_`) et sont ignorés par le script :

| Fichier | Rôle | Exécution |
|---------|------|-----------|
| `audit_dim_spatial_writers.sql` | Audit one-shot | Manuelle |
| `backfill_dim_spatial_lat_lon.sql` | Backfill one-shot | DAG Airflow |
| `create_lieux_*.sql` | Setup référentiel | One-shot initial |
| `create_mv_*.sql` | Setup vues mat. | Supplanté par migrations |
| `create_pathfinder_helpers.sql` | Fonctions routing | One-shot initial |
| `create_referentiel_*.sql` | Setup référentiel | One-shot initial |
| `create_tomtom_traffic.sql` | Setup Bronze TomTom | One-shot initial |
| `create_velov_maillage.sql` | Setup vélov | One-shot initial |
| `create_xgb_training_set.sql` | Setup training | One-shot initial |

Le glob du script : `migration_*.sql` → **uniquement** les fichiers nommés migration.

---

## 13. Tests

### 13.1. Test unitaire bash (via bats ou shellcheck)

```bash
# test_apply_migrations.sh

test_extract_version_3_digits() {
    result=$(extract_version "migration_016_tarifs_modes.sql")
    assertEquals 16 "$result"
}

test_extract_version_2_digits() {
    result=$(extract_version "migration_14_gold_coherence_tomtom_v2.sql")
    assertEquals 14 "$result"
}

test_sort_order() {
    # Vérifie que 14 < 15 < 16 < ... < 21
    versions=$(ls scripts/sql/migration_*.sql | while read f; do
        extract_version "$(basename $f)"
    done | sort -n)
    expected="14 15 16 17 18 19 20 21"
    assertEquals "$expected" "$(echo $versions | tr '\n' ' ' | sed 's/ $//')"
}
```

### 13.2. Test intégration (Docker local)

```bash
# Lance un PostgreSQL éphémère, applique toutes les migrations, vérifie
docker run -d --name test-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=lyonflow postgres:16
sleep 3

# Créer schémas prérequis
docker exec test-pg psql -U postgres -d lyonflow -c "CREATE SCHEMA IF NOT EXISTS gold; CREATE SCHEMA IF NOT EXISTS bronze; CREATE SCHEMA IF NOT EXISTS silver; CREATE SCHEMA IF NOT EXISTS referentiel;"
docker exec test-pg psql -U postgres -d lyonflow -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Appliquer
DOCKER_CONTAINER=test-pg POSTGRES_USER=postgres ./scripts/apply-migrations.sh

# Vérifier
docker exec test-pg psql -U postgres -d lyonflow -c "SELECT version, filename, status FROM public.schema_migrations ORDER BY version"

# Cleanup
docker rm -f test-pg
```

### 13.3. Test idempotence

```bash
# Appliquer 2 fois → même résultat, 0 erreurs
./scripts/apply-migrations.sh          # première fois : 8 applied
./scripts/apply-migrations.sh          # deuxième fois : 8 skipped, 0 applied
```

---

## 14. Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|-----------|
| Migration échoue à mi-chemin | Tables partiellement créées | Transaction par fichier (ROLLBACK automatique) + idempotence |
| Ordre incorrect | Vue qui référence une table pas encore créée | Tri numérique strict + dépendances linéaires (chaque migration ne dépend que des précédentes) |
| Fichier SQL modifié après application | Comportement inattendu si re-appliqué | Checksum warning + `--force` explicite |
| `docker exec` non disponible | Script inutilisable hors VPS | Mode `--direct` avec connexion psql native |
| Schéma `gold` n'existe pas | Toutes les migrations échouent | Pré-check + création automatique si absent |
| PostGIS absent | Migrations 017/018 échouent | Pré-check avec warning explicite |

---

## 15. Livrable

Un seul fichier : **`scripts/apply-migrations.sh`** (~150 lignes bash).

Cible `make migrate` dans le Makefile.

Temps estimé : **30 minutes** d'implémentation.
