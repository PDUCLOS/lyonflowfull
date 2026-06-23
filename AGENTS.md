# =============================================================================
# LyonFlowFull — AGENTS.md (mémoire projet pour assistants IA)
# =============================================================================
# Ce fichier est la source de vérité sur les décisions de phase et conventions
# du projet. À lire en premier par tout assistant IA.
# Dernière mise à jour : 2026-06-22, Sprint 21 (v0.11.0).
# =============================================================================

# Phases du projet (état 2026-06-22)
# --------------------------------

# PHASE 1 (livrée) — Production-ready LOCAL (branche `main`)
# - Tout le code fonctionne via `docker compose up -d --build`
# - Dashboard via `streamlit run dashboard/Accueil.py`
# - 3 personas (usager, pro_tcl, elu) naviguent
# - 8 collecteurs Bronze, transforms Silver/Gold, ML XGBoost, FastAPI, RGPD
#
# PHASE 2 (ACTIVE) — Déploiement VPS production (branche `vps`)
# - Cible production unique : VPS 51.83.159.224 (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD)
# - **v0.11.0** — 615 tests verts, ~60 widgets, 15 pages × 3 personas, 15 DAGs Airflow
# - Sprints livrés : VPS 1-8, 9+, 11+, 12+, 13, 13+, 15+, 17, 17+, 18, 20, 21
#
# Résumé des sprints majeurs :
#   * VPS-1 à VPS-4 : TLS, systemd, backup, monitoring, métriques custom
#   * VPS-5 : pipeline trafic reconnecté, 166 lignes TCL, Pro_4_Simulateur
#   * VPS-6 : focus H+1h, Nginx healthcheck fix, DB cleanup multi-horizons
#   * VPS-7 : KPIs TCL vues matérialisées (mv_line_kpis_live, mv_otp_heatmap)
#   * Sprint 8 : ZÉRO MOCK + ingestion Bronze complète (8 sources)
#   * Sprint 9+ : découplage training/inférence, GNN données réelles,
#     mapping LYO↔twgid, gold.xgb_training_set, MinIO sdb2
#   * Sprint 11+ : libellés TCL lisibles, OOM-kill SIRI/Vélov résolu, reorg docs
#   * Sprint 12+ : cleanup final audits Pro TCL + Usager (force_mock viré)
#   * Sprint 13 : version unique, auto-refresh par persona, nettoyage force_mock
#   * Sprint 13+ : TomTom Niveau 1 (cross-validation, détecteur capteurs HS)
#   * Sprint 15+ : interdépendances multimodales (Axes 1+3+5), mypy clean,
#     comparateur modes usager
#   * Sprint 17/17+ : Axes 2+4+6+7 (propagation Granger, report modal,
#     qualité données, météo interaction)
#   * Sprint 18 : pgRouting voiture OSM (87k vertices, 101k arêtes, trafic
#     temps réel */15 min). Image Docker pgrouting/pgrouting:16-3.5-3.7.3
#   * Sprint 20 : UX unifiée (plotly_theme, error_display, loading_wrapper,
#     freshness_badge, a11y)
#   * Sprint 21 : quantile regression XGBoost P10/P50/P90, sparkline 24h,
#     backup template, documentation cleanup (13 docs archivés, doublons
#     tests mergés, docs centrales à jour)
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
# - VPS : 51.83.159.224 (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD)
#   - sda1 = /, OS + code (Docker data-root migré sur sdb Sprint 9+)
#   - sdb = /mnt/postgres-data + /mnt/minio-data + Docker data-root
# - SSH : user `ubuntu`, clé `~/.ssh/id_ed25519`
# - DB : PostgreSQL 16 + PostGIS 3.5 + pgRouting 3.7.3
#   (4 schémas : bronze/silver/gold/osm + referentiel)
#   Image Docker : pgrouting/pgrouting:16-3.5-3.7.3
# - Path déploiement : /opt/lyonflow/
# - Reverse proxy : Nginx 1.27 (self-signed cert, DNS lyonflowfull.fr mort → accès par IP)
# - Process : systemd unit lyonflow.service
# - Backup : timer systemd quotidien 03:00 → scripts/backup.sh + offsite scripts/backup-offsite.sh
# - Monitoring : Grafana + Alertmanager UP. Prometheus supprimé Sprint 15+ (config YAML cassée v2.54)
# - NE PAS TOUCHER AU VPS tant que l'utilisateur n'a pas donné le feu vert
# - Commandes : make deploy-vps, make rollback-vps, make monitoring-up, ./scripts/healthcheck-vps.sh
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

# Conventions de code
# -------------------
# - Python 3.12+
# - SQL paramétré psycopg2 %s (jamais f-string)
# - Pas de credentials en dur (os.getenv() partout)
# - Code (variables, fonctions) en ANGLAIS
# - Commentaires / docstrings en FRANÇAIS
# - Ruff lint (line-length 120)
# - Type hints partout — mypy clean (82 fichiers, 0 erreur, Sprint 15+ v0.7.1)
# - pytest pour chaque module (conftest.py centralisé avec MockDB fixture)
# - Zéro mock dans le projet (Sprint 8) — DashboardDataError + show_error()

# Personas & accès
# ----------------
# - Usager : pas d'auth (accès public)
# - Pro TCL : auth par mot de passe (env PERSONA_PRO_TCL_PASSWORD) OU login user
# - Élu : auth par mot de passe (env PERSONA_ELU_PASSWORD) OU login user
# - 3 personas dans 1 dashboard, switcher dans la sidebar
# - Fichiers pages : Usager_*.py, Pro_*.py, Elu_*.py (avec préfixe ordre)

# Composants UX transversaux (Sprint 20+)
# ----------------------------------------
# - plotly_theme.py : LYF_TEMPLATE + COLORS dict. apply_lyf_theme(fig).
# - error_display.py : show_error(error_type, detail) — adapté par persona.
# - loading_state.py : loading_wrapper(msg, icon) — context manager spinner.
# - freshness_badge.py : badge prochaine MAJ par persona (30s/60s/300s).
# - a11y.py : plotly_with_alt(fig), sr_only(text) — accessibilité WCAG.
# - sparkline.py : sparkline 24h santé réseau.
# - auto_refresh.py : auto-refresh par persona (streamlit-autorefresh).

# Dette technique connue (Sprint 21)
# -----------------------------------
# - Vélov schéma ancien : xgboost_velov.py + gold.velov_features sur ancien
#   schéma (temperature_c, rain_mm, hour_sin). Pipeline trafic migré v0.3.1.
# - dim_spatial_grid_mapping.properties_twgid ≠ traffic_features_live.channel_id
#   (LYO00xxx) — backfill lat/lon OK, mapping identité à réconcilier.
# - /opt/lyonflow/logs/ doit être chown 50000:0 récursif après chaque rsync.
# - GNN training : code livré (stgcn_wrapper), retrain Airflow à finaliser.
# - DNS lyonflowfull.fr mort → accès par IP. Self-signed cert (Sprint 21 fix).
# - Prometheus supprimé Sprint 15+ (config YAML v2.54 cassée). Grafana sans source.
# - test_error_display 3 failures pré-existantes (test_persona_a_5_types).
# - OFFSITE_HOST non configuré (backup-template.sh livré, destination à choisir).

# Résolu depuis Sprint 8
# ----------------------
# - Tests E2E Playwright : OK
# - Data binding (Sprint 6) : OK (100% widgets branchés, fail loud Sprint 8+)
# - Résilience : OK (zéro mock — fail loud strict DashboardDataError)
# - Métriques Prometheus : supprimé Sprint 15+ (pas un bug, décision ops)
# - Backup auto : OK (Sprint VPS-2, timer systemd)
# - TLS production : self-signed (Sprint 21 fix, DNS mort)
# - Ingestion Bronze : OK (8 sources + TomTom Sprint 13+)
# - Nginx restart-loop : FIXÉ Sprint 21 (cert manquant → self-signed généré)
# - Mode démo / mocks : VIRÉ Sprint 8. Cleanup terminé Sprint 12+.
# - NetworkX routing : VIRÉ Sprint 18. pgRouting pgr_dijkstra.
# - snap_to_roads.py : VIRÉ Sprint 18. Dead code.
# - 13 docs stale : ARCHIVÉS Sprint 21 (convention déplacer, jamais supprimer).
# - test drift_detector doublon : MERGÉ Sprint 21.

# Règles strictes
# ---------------
# 1. Pas de push git sans accord explicite
# 2. Pas de modif sur VPS sans accord explicite
# 3. SQL paramétré PARTOUT
# 4. Pas de credentials en dur
# 5. Containers non-root
# 6. Pas de merge `kubernetes` ou `cloud-demo` dans `vps` ou `main`
# 7. ZÉRO MOCK DANS LE PROJET (Sprint 8)
# 8. Référentiel lieux en DB (referentiel.lieux_lyon, lieux_transports, lieux_calendrier)
# 9. Fiabilité VPS : DAGs critiques retries=0, backfill lat/lon */5min
# 10. Cache Python .pyc : purger __pycache__ après modif src/ dans containers Airflow
# 11. DOCKER DATA-ROOT SUR SDB — ne pas revenir à /var/lib/docker
# 12. BACKUP OFFSITE OBLIGATOIRE — jamais de backup persistant sur sdb
# 13. Archive convention : déplacer, jamais supprimer (traçabilité RNCP 38777)

# Liens utiles
# ------------
# - Repo GitHub : https://github.com/PDUCLOS/lyonflowfull
# - Issue tracker : GitHub Issues
# - CI : GitHub Actions (.github/workflows/ci.yml)
# - Docs : /docs/ (ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE, RUNBOOK, MONITORING, SPECs)
# - Rapports sprint : /archive/sprints/ (convention : déplacer, jamais supprimer)
# - Healthcheck : scripts/healthcheck-vps.sh
# - TODO restant : docs/TODO.md (P2 tabs/collapsibles, P2.4 index pgRouting)
