#!/usr/bin/env bash
# deploy-sprint24.sh — Déploie le fix gold-stale (Sprint 24) SANS git ni rebuild.
#
# À LANCER DEPUIS LE MAC (pas depuis la session SSH du VPS), à la racine du repo :
#   cd ~/Documents/Lyonfull && bash scripts/deploy-sprint24.sh
#
# Ce script :
#   1. rsync les 6 fichiers Sprint 24 vers /opt/lyonflow (rien d'autre)
#   2. applique la migration 036 via apply-migrations.sh (tracking pending)
#   3. purge le cache .pyc Airflow (sinon ancienne version des DAGs)
#   4. recharge scheduler + worker (restart, PAS de --build)
#   5. trigger refresh_heavy_mv (1er refresh — plain car MV recréée)
#   6. healthcheck gold-stale
#
# Léger volontairement : pas de git tag, pas de docker --build, pas de restart
# de toute la stack. Pour un déploiement complet officiel, utiliser `make deploy-vps`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Config VPS depuis .deploy.env ---
[[ -f .deploy.env ]] || { echo "ERREUR : .deploy.env introuvable à la racine."; exit 1; }
VPS_HOST="$(grep -E '^VPS_HOST=' .deploy.env | cut -d= -f2)"
SSH_KEY="$(grep -E '^VPS_SSH_KEY=' .deploy.env | cut -d= -f2)"
SSH_KEY="${SSH_KEY/#\~/$HOME}"
: "${VPS_HOST:?VPS_HOST manquant dans .deploy.env}"
: "${SSH_KEY:?VPS_SSH_KEY manquant dans .deploy.env}"
SSH="ssh -i $SSH_KEY $VPS_HOST"

FILES=(
  # Sprint 24 — fix gold stale + purge
  "src/transformation/silver_to_gold.py"
  "dags/transforms/transform_silver_to_gold.py"
  "dags/transforms/refresh_heavy_mv.py"
  "scripts/sql/migration_036_bus_traffic_spatial_48h.sql"
  "scripts/sql/migration_037_idx_purge_traffic_features_live.sql"
  # Sprint 23 bonus (même working tree, pas encore sur le VPS)
  "scripts/sql/migration_035_mv_latest_sensor_position.sql"
  "dags/transforms/build_spatial_mapping.py"
  "dags/maintenance/critical_pipeline_health.py"
  "dashboard/components/widgets/pro_tcl/gnn_map.py"
  # Outils + docs
  "scripts/healthcheck-gold-stale.sh"
  "scripts/pg-audit.sh"
  "docs/SPRINT_24_FIX_GOLD_STALE.md"
  "docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md"
)

echo "==[ 1/7 rsync fichiers → $VPS_HOST:/opt/lyonflow ]=="
# -R conserve les chemins relatifs (src/..., dags/..., etc.)
rsync -avzR -e "ssh -i $SSH_KEY" "${FILES[@]}" "$VPS_HOST:/opt/lyonflow/"

# Sprint 24++ (2026-06-29) — ÉTAPE CRITIQUE oubliée au 1er run : rsync pose les
# fichiers en 600 ubuntu:ubuntu, mais Airflow tourne en UID 50000. Sans ce
# chown, le scheduler lève PermissionError sur chaque DAG/module rsyncé et ne
# charge plus aucun DAG (gotcha Sprint VPS-5). Doit couvrir dags/ ET src/
# (les DAGs importent src.transformation...). sudo requis (chown vers autre UID).
echo "==[ 2/7 chown 50000:0 post-rsync (anti PermissionError Airflow) ]=="
$SSH "sudo chown -R 50000:0 /opt/lyonflow/dags /opt/lyonflow/src /opt/lyonflow/dashboard 2>/dev/null; sudo chmod -R u+rX,g+rX /opt/lyonflow/dags /opt/lyonflow/src /opt/lyonflow/dashboard"

echo "==[ 3/7 apply migration 036/037 (tracking pending) ]=="
$SSH "cd /opt/lyonflow && ./scripts/apply-migrations.sh"

echo "==[ 4/7 purge cache .pyc Airflow ]=="
$SSH "docker exec lyonflow-airflow-scheduler find /opt/airflow -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"

# Sprint 24++ : LocalExecutor depuis Sprint 11+ → PAS de container worker
# (le 1er run a échoué sur 'No such container: lyonflow-airflow-worker').
# On restart le scheduler seul.
echo "==[ 5/7 reload scheduler (restart, pas de rebuild) ]=="
$SSH "docker restart lyonflow-airflow-scheduler"

echo "==[ attente 30s que le scheduler reparse les DAGs ]=="
sleep 30

echo "==[ 6/7 vérifie + trigger refresh_heavy_mv ]=="
$SSH "docker exec lyonflow-airflow-scheduler airflow dags list 2>/dev/null | grep -E 'refresh_heavy_mv|transform_silver_to_gold' || true"
$SSH "docker exec lyonflow-airflow-scheduler airflow dags unpause refresh_heavy_mv 2>/dev/null || true"
$SSH "docker exec lyonflow-airflow-scheduler airflow dags trigger refresh_heavy_mv 2>/dev/null || true"

echo "==[ 7/7 healthcheck gold-stale (laisse ~1-2 min au refresh) ]=="
$SSH "cd /opt/lyonflow && bash scripts/healthcheck-gold-stale.sh" || true

echo "✅ Sprint 24 déployé. Re-check dans 2 min : ssh $VPS_HOST 'cd /opt/lyonflow && bash scripts/healthcheck-gold-stale.sh'"
