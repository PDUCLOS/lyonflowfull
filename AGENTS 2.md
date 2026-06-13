# =============================================================================
# LyonFlowFull — AGENTS.md (mémoire projet pour assistants IA)
# =============================================================================
# Ce fichier est la source de vérité sur les décisions de phase et conventions
# du projet. À lire en premier par tout assistant IA.
<<<<<<< HEAD
# =============================================================================

# Phases du projet (état 2026-06-07)
=======
# Dernière mise à jour : 2026-06-12, Sprint 8 (zéro mock + ingestion Bronze + focus H+1h).
# =============================================================================

# Phases du projet (état 2026-06-12)
>>>>>>> origin/main
# --------------------------------

# PHASE 1 (livrée) — Production-ready LOCAL (branche `main`)
# - Tout le code fonctionne via `docker compose up -d --build`
# - Dashboard via `streamlit run dashboard/Accueil.py`
# - 3 personas (usager, pro_tcl, elu) naviguent
# - 8 collecteurs Bronze, transforms Silver/Gold, ML XGBoost, FastAPI, RGPD
# - 47+ tests passent (`pytest tests/`)
#
# PHASE 2 (ACTIVE) — Déploiement VPS production (branche `vps`)
<<<<<<< HEAD
# - Cible production unique : VPS 51.83.159.224
# - Sprints VPS 1-5 livrés :
=======
# - Cible production unique : VPS 51.83.159.224 (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD)
# - Sprints VPS 1-8 livrés :
>>>>>>> origin/main
#   * VPS-1 : TLS Let's Encrypt + healthcheck + hardening SSH/firewall
#   * VPS-2 : systemd unit + backup timer + rollback + CI vps branch
#   * VPS-3 : Prometheus + Alertmanager + Grafana + exporters (node, postgres, nginx, redis)
#   * VPS-4 : métriques FastAPI custom (predictions, latency, personas, DAGs, MLflow, DB)
#   * VPS-5 : pipeline trafic reconnecté (dag_live_speed_retrain) + 166 lignes TCL
#     Pro_4_Simulateur + sort/explore KPIs par ligne + 5 régressions SQL corrigées
#     + fix perms logs/ worker Airflow
<<<<<<< HEAD
# - Docs : docs/VPS_HARDENING.md, docs/MONITORING.md, docs/CONTROLE_VPS_VS_CLOUD_DEMO.md,
#   SPRINT_VPS-5_REPORT.md
#
# Dette technique connue (Sprint 9+) :
# - src/models/xgboost_speed.py : 9+ colonnes référencent l'ancien schéma
#   gold.traffic_features_live. Refacto nécessaire pour vraies prédictions ML
#   (en attendant : baseline = dernière vitesse observée propagée sur 4 horizons).
# - dim_spatial_grid_mapping.properties_twgid (entiers) ne match pas
#   traffic_features_live.channel_id (LYO00xxx). Réconcilier pour géocoder
#   les prédictions sur la carte.
# - /opt/lyonflow/logs/ doit être chown 50000:0 récursif après chaque rsync.
#   Fix durable = entrypoint Dockerfile.
=======
#   * VPS-6 (2026-06-11) : focus H+1h stable
#       - dag_live_speed_retrain : HORIZON_MAP={60:1} (suppression 0/3/6)
#       - schedule :20 hourly → */30 * * * * (toutes les 30 min)
#       - Nginx Docker healthcheck fix : `localhost` → `127.0.0.1` (IPv6 ::1 connection refused)
#       - DB cleanup : DELETE 232k rows multi-horizons, reste 77k rows horizon=1
#   * VPS-7 (2026-06-12) : KPIs TCL via vues matérialisées
#       - gold.mv_line_kpis_live (155 lignes TCL avec OTP, retard, fréquence, charge)
#       - gold.mv_otp_heatmap (4416 triplets ligne×date×hour)
#       - DAG refresh_lieux_calendrier quotidien 5h
#   * VPS-8 (2026-06-12) : ZÉRO MOCK DANS LE PROJET + INGESTION BRONZE
#       - Suppression complète de `src/data/mock/` (déplacé dans `tests/fixtures/mock_data/`)
#       - Tous widgets/data_loader/db_query fail loud via DashboardDataError
#       - 18 fallbacks mock virés (data_loader, db_query, airflow_client)
#       - Tests conftest centralisé + 6 tests valident la politique "zéro mock"
#       - Sprint 8+1 : focus H+1h durci (FEATURE_COLS 14→9, horizons=[60], retries=0)
#       - Sprint 8+4 : durcissement monitoring Prometheus/Grafana/Alertmanager (config YAML v2.54)
#       - Sprint 8+5 : Cron backfill lat/lon `*/5min` (dette schéma propriétés_twgid)
#       - Sprint 8+6 : Trigger SQL `trg_dim_spatial_has_lat_lon` (défense en profondeur)
#       - Sprint 8+7 : Pathfinding voiture/Vélov (signature + smart routing)
#       - Sprint 8+8 : 5 régressions ingestion Bronze (uq_*_nodup dropped, _count_records Open-Meteo)
#         air_quality 72 records + chantiers 428 records débloqués
#       - Refacto xgboost_speed.py : schéma v0.3.1 (lag_h1/h2/h3, delta_h1, rolling_mean_h1)
# - Docs : docs/VPS_HARDENING.md, docs/MONITORING.md, docs/CONTROLE_VPS_VS_CLOUD_DEMO.md,
#   SPRINT_VPS-5_REPORT.md, SPRINT_VPS-6_REPORT.md, SPRINT_VPS-8_REPORT.md, PLAN_NO_MOCK_VPS.md
# - Healthcheck : scripts/healthcheck-vps.sh (Sprint 8+, 20 checks : containers + DB + endpoints)
#
# Dette technique connue (Sprint 9+) :
# - get_bottlenecks_summary n'est pas exporté par src.data.db_query (load_bottlenecks_top plante)
# - dim_spatial_grid_mapping.properties_twgid (entiers ou strings) ne match pas
#   traffic_features_live.channel_id (LYO00xxx) d'identité — backfill lat/lon OK mais mapping
#   à réconcilier pour la jointure d'identité dans gold.trafic_predictions.
# - /opt/lyonflow/logs/ doit être chown 50000:0 récursif après chaque rsync.
#   Fix durable = entrypoint Dockerfile.
# - TomTom Traffic : module helpers sans classe DataCollector. DAG no-op Sprint 8,
#   réactivation Sprint 12+ = coder `TomTomTrafficFlow(DataCollector)`.
# - GNN training : code livré (stgcn_wrapper), retrain Airflow à finaliser
# - Composant React deck.gl : pas encore intégré
# - Intégration dynamique FastAPI ↔ MLflow : en cours
>>>>>>> origin/main
#
# PHASE 3 (dormante, futur AWS/GCP) — Kubernetes (branche `kubernetes`)
# - NE PAS MERGER dans `vps` ni `main`
# - Préparée pour EKS/GKE futur, pas de déploiement actif
#
# PHASE 4 (dormante, futur AWS/GCP) — Cloud démo Jedha (branche `cloud-demo`)
# - NE PAS MERGER dans `vps` ni `main`
# - Préparée pour POC cloud public ponctuel, pas active

# Déploiement VPS (cible production unique)
# -----------------------------------------
<<<<<<< HEAD
# - VPS : 51.83.159.224 (Ubuntu, 6 CPU, 12 GB RAM, 100 GB SSD)
# - SSH key : ~/.ssh/lyonflow_deploy
# - DB : PostgreSQL 16 sur le VPS (base actuelle conservée)
# - Path déploiement : /opt/lyonflow/
# - Reverse proxy : Nginx + TLS Let's Encrypt
# - Process : systemd unit lyonflow.service
# - Backup : timer systemd quotidien 03:00 → scripts/backup.sh
# - Monitoring : docker-compose.monitoring.yml (Prometheus/Grafana/Alertmanager)
# - NE PAS TOUCHER AU VPS tant que l'utilisateur n'a pas donné le feu vert
# - Vérifier l'état du disque avant tout : df -h / (souvent à 100%)
# - Commandes : make deploy-vps, make rollback-vps, make healthcheck-vps, make monitoring-up
=======
# - VPS : 51.83.159.224 (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD)
#   - sda1 = /, OS + code + tous volumes Docker (Airflow, MLflow, Grafana, Prometheus, Redis)
#   - sdb = /mnt/postgres-data + /mnt/minio-data (données applicatives uniquement)
# - SSH key : ~/.ssh/lyonflow_deploy (ED25519)
# - DB : PostgreSQL 16 + PostGIS sur le VPS (3 schémas : bronze/silver/gold + referentiel)
# - Path déploiement : /opt/lyonflow/
# - Reverse proxy : Nginx 1.27 (DNS lyonflowfull.fr mort → accès par IP)
# - Process : systemd unit lyonflow.service
# - Backup : timer systemd quotidien 03:00 → scripts/backup.sh + offsite scripts/backup-offsite.sh
# - Monitoring : docker-compose.monitoring.yml (Prometheus/Grafana/Alertmanager — tous UP Sprint 8+)
# - NE PAS TOUCHER AU VPS tant que l'utilisateur n'a pas donné le feu vert
# - Vérifier l'état du disque avant tout : df -h /opt (sda1 à 80% — 19 Go libres)
# - Commandes : make deploy-vps, make rollback-vps, make monitoring-up, ./scripts/healthcheck-vps.sh
>>>>>>> origin/main
#
# Règle CRITIQUE : toute correction faite SUR le VPS doit aussi être commitée dans git
# --------------------------------------------------------------------------
# Si tu patch un fichier en place sur le VPS (sed, edit, etc.), tu dois
# IMPÉRATIVEMENT aussi :
#   1. Récupérer la version patchée (scp vers le Mac)
#   2. L'appliquer dans le repo local (branche vps)
#   3. git commit + push
# Sinon le prochain deploy (rsync + restart) ÉCRASE ta correction.
# Idem pour les installs pip dans un container : ajouter au requirements.txt
# correspondant dans le repo.
<<<<<<< HEAD
=======
# Astuce : pousser un fichier via `cat local | ssh user@host "cat > remote"` (bypass chattr +a).
# Astuce 2 : rebuild streamlit nécessaire car le container n'a pas de bind mount src/.
>>>>>>> origin/main

# Conventions de code
# -------------------
# - Python 3.12+
# - SQL paramétré psycopg2 %s (jamais f-string)
# - Pas de credentials en dur (os.getenv() partout)
# - Code (variables, fonctions) en ANGLAIS
# - Commentaires / docstrings en FRANÇAIS
# - Ruff lint (line-length 120)
# - Type hints partout (mypy non bloquant)
# - pytest pour chaque module (conftest.py centralisé avec MockDB fixture)

# Personas & accès
# ----------------
# - Usager : pas d'auth (accès public)
# - Pro TCL : auth par mot de passe (env PERSONA_PRO_TCL_PASSWORD) OU login user
# - Élu : auth par mot de passe (env PERSONA_ELU_PASSWORD) OU login user
# - 3 personas dans 1 dashboard, switcher dans la sidebar
# - Fichiers pages : Usager_*.py, Pro_*.py, Elu_*.py (avec préfixe ordre)

# Résolu en Phase 2 (vps)
# -----------------------
<<<<<<< HEAD
# - GNN training : code livré (stgcn_wrapper), retrain Airflow à finaliser
# - Composant React deck.gl : pas encore intégré
# - Intégration dynamique FastAPI ↔ MLflow : en cours
#
# Résolu en Phase 2 (vps) :
# - Tests E2E Playwright : OK (Tests profil Élu et résilience implémentés)
# - Data binding (Sprint 6) : OK (100% des widgets branchés avec fallback auto)
# - Résilience : OK (Gestion OperationalError psycopg2 avec fallback mock)
# - Métriques Prometheus : OK (Sprint VPS-3 + VPS-4)
# - Backup auto : OK (Sprint VPS-2, timer systemd)
# - TLS production : OK (Sprint VPS-1, Let's Encrypt)
=======
# - Tests E2E Playwright : OK (Tests profil Élu et résilience implémentés)
# - Data binding (Sprint 6) : OK (100% des widgets branchés, fail loud Sprint 8+)
# - Résilience : OK (ZÉRO mock en Sprint 8 — fail loud strict via DashboardDataError)
# - Métriques Prometheus : OK (Sprint VPS-3 + VPS-4)
# - Backup auto : OK (Sprint VPS-2, timer systemd)
# - TLS production : OK (Sprint VPS-1, Let's Encrypt)
# - Ingestion Bronze : OK (Sprint VPS-8 — air_quality 72 records, chantiers 428 records)
>>>>>>> origin/main

# Règles strictes
# ---------------
# 1. Pas de push git sans accord explicite
# 2. Pas de modif sur VPS sans accord explicite
# 3. SQL paramétré PARTOUT
# 4. Pas de credentials en dur
# 5. Containers non-root
# 6. Pas de merge `kubernetes` ou `cloud-demo` dans `vps` ou `main` (dormantes AWS/GCP)
<<<<<<< HEAD
=======
# 7. **ZÉRO MOCK DANS LE PROJET** (Sprint 8, 2026-06-12) : helper `_is_demo_mode()`
#    retourne TOUJOURS False. `LYONFLOW_DEMO_MODE` doit être `0` en prod
#    (defense in depth via .env + check-deploy-env.sh). Toute source de
#    données indisponible lève `DashboardDataError` et le widget affiche
#    `st.error()`. Pas de fallback mock silencieux, jamais. Mode démo
#    complètement supprimé. Cf. tests/data/test_no_mock_vps_policy.py.
# 8. **Référentiel lieux en DB** : 21 lieux emblématiques Lyon stockés dans
#    `referentiel.lieux_lyon` (PostgreSQL) — pas de codé-en-dur. Les desserts
#    TCL dans `referentiel.lieux_transports`, les cadences dans
#    `referentiel.lieux_calendrier`. 10 lignes emblématiques (M_A..D, T1..T6,
#    C3, C13) extraites dans `src/data/tcl_lines.py` (référentiel statique,
#    pas un mock).
# 9. **Fiabilité VPS** (Sprint 8+) : DAGs critiques ont `retries=0` (le
#    cycle suivant rattrape). Le backfill lat/lon tourne `*/5min`. Tests
#    `pytest -m "not integration"` par défaut (integration skippable en CI
#    sans stack).
# 10. **Cache Python .pyc** dans containers Airflow : purger `find /opt/airflow
#     -name __pycache__ -type d -exec rm -rf {} +` après modification de
#     `src/`. Sinon DAGs chargent l'ancienne version (Sprint 8 leçon apprise).
>>>>>>> origin/main

# Liens utiles
# ------------
# - Repo GitHub : https://github.com/PDUCLOS/lyonflowfull
# - Issue tracker : GitHub Issues
# - CI : GitHub Actions (.github/workflows/ci.yml)
# - Docs : /docs/ (README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE, RUNBOOK, MONITORING)
# - Rapports sprint : /SPRINT_*.md (8 rapports)
# - Healthcheck : scripts/healthcheck-vps.sh (20 checks)
