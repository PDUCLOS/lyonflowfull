#!/bin/bash
# =============================================================================
# commit-audit-fixes.sh — Helper pour commit séparé par fix (Sprint P0-P3)
# =============================================================================
# Lancé depuis /Users/patriceduclos/Documents/Lyonfull par Patrice.
#
# NE PAS POUSSER (pas de `git push`). Laisse Patrice review + push lui-même.
#
# Usage :
#   chmod +x commit-audit-fixes.sh
#   ./commit-audit-fixes.sh          # dry-run (affiche ce qui sera ajouté)
#   ./commit-audit-fixes.sh --apply  # applique réellement les git add
# =============================================================================

set -euo pipefail

DRY_RUN=true
if [ "${1:-}" = "--apply" ]; then
    DRY_RUN=false
fi

cd "$(dirname "$0")"

stage() {
    local label="$1"
    shift
    local files=("$@")
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $label:"
        printf "  %s\n" "${files[@]}"
    else
        git add "${files[@]}"
        echo "[STAGED] $label"
    fi
}

# -----------------------------------------------------------------------------
# Commit 1 — P0.1 : Conflit scheduler (archive du DAG désactivé)
# -----------------------------------------------------------------------------
stage "P0.1: archive _disabled_*.py (conflit scheduler Airflow)" \
    "dags/_archive/__init__.py" \
    "dags/_archive/.airflowignore" \
    "dags/_archive/_disabled_dag_live_speed_retrain.py"

# -----------------------------------------------------------------------------
# Commit 2 — P0.2 : 4 stubs dans db_query.py
# -----------------------------------------------------------------------------
stage "P0.2: 4 stubs P0.2 (lieux, cadence, drift) dans db_query.py" \
    "src/data/db_query.py"

# -----------------------------------------------------------------------------
# Commit 3 — P0.3 : Fix API predict_traffic
# -----------------------------------------------------------------------------
stage "P0.3: API predict_traffic cast str(node_idx)" \
    "src/api/main.py"

# -----------------------------------------------------------------------------
# Commit 4 — P0.4 : Format line_kpis dict[line_id, kpis]
# -----------------------------------------------------------------------------
stage "P0.4: get_line_kpis retourne dict[line_id, kpis]" \
    "src/data/db_query.py"

# -----------------------------------------------------------------------------
# Commit 5 — P0.5 : 2 index sur gold.trafic_predictions
# -----------------------------------------------------------------------------
stage "P0.5: alembic 0002 - 2 index gold.trafic_predictions" \
    "alembic/versions/0002_trafic_predictions_indexes.py"

# -----------------------------------------------------------------------------
# Commit 6 — P1.1 : Table gold.velov_features (alembic 0003)
# -----------------------------------------------------------------------------
stage "P1.1: alembic 0003 - table gold.velov_features" \
    "alembic/versions/0003_velov_features_table.py"

# -----------------------------------------------------------------------------
# Commit 7 — P1.2 : get_traffic_for_node aligné + JOIN
# -----------------------------------------------------------------------------
stage "P1.2: get_traffic_for_node aligné schéma réel + JOIN dim_spatial_grid_mapping" \
    "src/data/db_query.py"

# -----------------------------------------------------------------------------
# Commit 8 — P1.3 : Flag LYONFLOW_DEMO_AUTH_HELPER_VISIBLE
# -----------------------------------------------------------------------------
stage "P1.3: flag LYONFLOW_DEMO_AUTH_HELPER_VISIBLE (cacher mdp démo en prod)" \
    "src/persona/auth.py" \
    ".env.example" \
    "scripts/check-deploy-env.sh"

# -----------------------------------------------------------------------------
# Commit 9 — P1.4 : TTL rate-limit
# -----------------------------------------------------------------------------
stage "P1.4: rate-limit TTL idle 1h + lazy cleanup" \
    "src/api/middleware/rate_limit.py"

# -----------------------------------------------------------------------------
# Commit 10 — P1.5 : Table gold.app_users
# -----------------------------------------------------------------------------
stage "P1.5: alembic 0004 - table gold.app_users (uuid PK + persona_id CHECK)" \
    "alembic/versions/0004_app_users_table.py"

# -----------------------------------------------------------------------------
# Commit 11 — P1.6 : reset_lieux_cache dans clear_all_caches
# -----------------------------------------------------------------------------
stage "P1.6: clear_all_caches purge aussi le cache lieux" \
    "dashboard/components/data_cache.py"

# -----------------------------------------------------------------------------
# Commit 12 — P2.1 : Réduire horizons XGBoost
# -----------------------------------------------------------------------------
stage "P2.1: XGBoost speed H+1h + velov H+30min uniquement" \
    "dags/ml/retrain_xgboost.py"

# -----------------------------------------------------------------------------
# Commit 13 — P2.2 : Géocoder dynamique bottlenecks
# -----------------------------------------------------------------------------
stage "P2.2: bottlenecks carte Élu géocodage dynamique" \
    "src/data/db_query.py" \
    "src/data/data_loader.py" \
    "dashboard/components/widgets/elu/bottleneck_map.py"

# -----------------------------------------------------------------------------
# Commit 14 — P2.3 : Idempotence INSERT trafic_predictions
# -----------------------------------------------------------------------------
stage "P2.3: ON CONFLICT DO NOTHING sur INSERT trafic_predictions" \
    "dags/ml/dag_live_speed_retrain.py" \
    "dags/_archive/_disabled_dag_live_speed_retrain.py"

# -----------------------------------------------------------------------------
# Commit 15 — P2.4 : Sampling audit rate-limit
# -----------------------------------------------------------------------------
stage "P2.4: audit rate-limit sampling 10%" \
    "src/api/middleware/rate_limit.py"

# -----------------------------------------------------------------------------
# Commit 16 — P2.5 : bus_delay_segments + infrastructure_bottlenecks
# -----------------------------------------------------------------------------
stage "P2.5: alembic 0005 - bus_delay_segments + infrastructure_bottlenecks" \
    "alembic/versions/0005_gold_bottleneck_tables.py"

# -----------------------------------------------------------------------------
# Commit 17 — P2.6 : referentiel + mv_line_kpis + xgb_training
# -----------------------------------------------------------------------------
stage "P2.6: alembic 0006 - referentiel + mv_line_kpis_live + xgb_training_set" \
    "alembic/versions/0006_referentiel_and_mvs.py"

# -----------------------------------------------------------------------------
# Commit 18 — P3.1 : mv_kpis_12_months + 3 autres vues
# -----------------------------------------------------------------------------
stage "P3.1: alembic 0007 - mv_kpis_12_months + mv_otp_heatmap + fact_correlation_matrix + amenagements_history" \
    "alembic/versions/0007_gold_views_and_history.py"

# -----------------------------------------------------------------------------
# Commit 19 — P3.3 : Doc seed_users
# -----------------------------------------------------------------------------
stage "P3.3: doc seed_users.py" \
    "scripts/seed_users.py"

# -----------------------------------------------------------------------------
# Commit 20 — P3.4 : velov station_id
# -----------------------------------------------------------------------------
stage "P3.4: load_velov_stations expose station_id" \
    "src/data/data_loader.py"

# -----------------------------------------------------------------------------
# Commit 21 — P3.5 : Archive legacy_dag_pipeline
# -----------------------------------------------------------------------------
stage "P3.5: archive legacy_github/dag_pipeline.py" \
    "dags/_archive/legacy_dag_pipeline.py"

# -----------------------------------------------------------------------------
# Commit 22 — P4.1 + P4.2 : Tests + doc
# -----------------------------------------------------------------------------
stage "P4.1+P4.2: tests intégration Mon Trajet + AUDIT_FIXES_RECAP" \
    "tests/integration/test_usager_mon_trajet_loaders.py" \
    "AUDIT_FIXES_RECAP.md"

# -----------------------------------------------------------------------------
# Commit 23 — Plan markdown (commit unique, à part)
# -----------------------------------------------------------------------------
stage "Plans d'audit (lecture seule)" \
    "AUDIT_INTEGRATION_LIVE.md" \
    "AUDIT_P0_PLAN.md" \
    "AUDIT_P1_PLAN.md" \
    "AUDIT_P2_PLAN.md" \
    "AUDIT_P3_P4_PLAN.md"

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "[INFO] C'était un dry-run. Pour appliquer réellement :"
    echo "       $0 --apply"
    echo ""
    echo "[NEXT] Après avoir vérifié, lance les commits manuellement avec :"
    echo "        git commit -m 'P0.1: ...'"
    echo "        ..."
    echo "       Ou crée un script de commits automatique à partir de cette liste."
fi
