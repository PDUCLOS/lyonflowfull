# =============================================================================
# LyonFlow — AGENTS.md (mémoire projet pour assistants IA)
# =============================================================================
# Ce fichier est la source de vérité sur les décisions de phase et conventions
# du projet. À lire en premier par tout assistant IA.
# Dernière mise à jour : 2026-09-22, Sprint 26 (v0.14.1) — débloat osm.ways, backup offsite durci.
# =============================================================================

# Phases du projet (état 2026-07-23)
# --------------------------------

# PHASE 1 (livrée) — Production-ready LOCAL (historique, branche figée)
# - Snapshot préservé dans `legacy/phase1-main` (backup du 2026-07-23)
# - 3 personas (usager, pro_tcl, elu), 8 collecteurs Bronze, ML XGBoost, FastAPI, RGPD
#
# PHASE 2 (ACTIVE) — Déploiement VPS production (branche `main` depuis 2026-07-23)
# - Cible production unique : VPS 51.83.159.224 (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD)
# - **v0.14.1** (en cours sur main) — Sprint 26 (2026-09-22) : alertes Telegram en boucle + backup
# - **Sprint 26 (2026-09-22)** : origine des alertes Telegram = `refresh_osm_traffic_costs`
#   à 20,0 % d'échec (19/95, timeout 240 s) pile sur le seuil du dag-failure-rate-monitor.
#   Cause racine : `osm.ways` à 98 % de vide (1,5 Go heap + 0,9 Go index pour 101 k lignes)
#   parce que la migration 029 avait indexé `cost`/`reverse_cost` (jamais lus par pgr_dijkstra,
#   idx_scan = 0) → chaque UPDATE non-HOT. Fix : migration 048 (DROP 2 index + fillfactor 50 +
#   VACUUM FULL → 59 Mo / 6 Mo), migration 049 (4 index morts, ~10 Go, idx_scan = 0),
#   hystérésis 20 % / 15 % dans `scripts/dag-failure-rate-monitor.sh`, `purge_bronze` 03:00 → 03:08
#   et `dag_daily_speed_train` 03:00 → 03:38 (tempête 03:00 = restarts watchdog 05/06/07/10 sept).
#   Backup : timer `lyonflow-backup.timer` trouvé DÉSACTIVÉ depuis le 2026-07-22, config rclone
#   invalide (token JSON), 0 backup pendant 2 mois. Réactivé + `backup-offsite.sh` durci
#   (preflight destination AVANT pg_dump, trap qui termine le pg_dump orphelin, purge auto par
#   taille/âge) + `lyonflow-backup-failed.service` (OnFailure → Telegram). Reste à faire par
#   Patrice : OAuth Google Drive (`rclone authorize "drive"` sur le Mac, coller le token dans
#   `/opt/lyonflow/.rclone.conf`).
#   Incident annexe : activer le timer avec `Persistent=true` déclenche un run immédiat ; le
#   pg_dump lancé via `docker exec` a survécu 30 min à la mort du pipe rclone (locks sur toutes
#   les tables, REFRESH MV bloqués). Corrigé par le preflight + trap.
# - **Sprint 25 (2026-08-22)** : durcissement PG `tcp_keepalives_idle=60` + `idle_in_txn=2min` (commit 5c7289f).
#   Patch : `docker-compose.yml` (command: postgres -c tcp_keepalives_idle=60) +
#   `scripts/sql/migration_047_postgres_connection_health.sql` (ALTER SYSTEM + vue `gold.v_connection_health`).
#   Incident : 14 backends fantômes d'un container détruit → RAM PG 93 % → watchdog en boucle.
#   Doc : `docs/INCIDENTS/2026-08-22-postgres-connection-leak.md` (hors-github par convention Sprint 23).
# - **Sprint 23 (2026-07-23)** : `vps` renommé `main` (force-push).
#   Backup complet de l'ancien `main` dans `legacy/phase1-main`.
#   Le VPS tourne maintenant sur `main` (checkout + pull OK, containers healthy).
#   La branche `vps` reste trackée comme alias (== main @ cf75e53).
# - Sprints livrés : VPS 1-8, 9+, 11+, 12+, 13, 13+, 15+, 17, 17+, 18, 20, 21, 25, 26
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
#   * Sprint 22+ : optimisations UX/RAM (lazy loading, onglets, see MODIFICATIONS_IA_SPRINT22)
#   * Sprint 23 : docs/ hors github, `presentation.html` → `présentation/`,
#     `vps` → `main` (force-push), .opencode/tmp untrack, gitignore renforcé
#
# PHASE 3 (dormante, futur AWS/GCP) — Kubernetes (branche `kubernetes`)
# - NE PAS MERGER dans `main`
# - Préparée pour EKS/GKE futur, pas de déploiement actif
#
# PHASE 4 (dormante, futur AWS/GCP) — Cloud démo Jedha (branche `cloud-demo`)
# - NE PAS MERGER dans `main`
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
# - Path déploiement : /opt/lyonflow/ (branche checkout = `main` depuis Sprint 23)
# - Reverse proxy : Nginx 1.27 (self-signed cert, DNS lyonflow.fr mort → accès par IP)
# - Process : systemd unit lyonflow.service
# - Backup : timer systemd quotidien 03:00 → scripts/backup.sh + offsite scripts/backup-offsite.sh
# - Monitoring : Grafana + Alertmanager UP. Prometheus supprimé Sprint 15+ (config YAML cassée v2.54)
# - NE PAS TOUCHER AU VPS tant que l'utilisateur n'a pas donné le feu vert
# - Commandes : make deploy-vps, make rollback-vps, make monitoring-up, ./scripts/healthcheck-vps.sh
# - DEPLOY_BRANCH dans `.deploy.env` = `main` (Sprint 23)
#
# Règle CRITIQUE : toute correction faite SUR le VPS doit aussi être commitée dans git
# --------------------------------------------------------------------------
# Si tu patch un fichier en place sur le VPS (sed, edit, etc.), tu dois
# IMPÉRATIVEMENT aussi :
#   1. Récupérer la version patchée (scp vers le Mac)
#   2. L'appliquer dans le repo local (branche main)
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

# Dette technique connue (Sprint 26)
# -----------------------------------
# - BACKUP OFFSITE : OAuth Google Drive à finaliser (cf. Sprint 26). Tant que ce n'est pas fait,
#   `lyonflow-backup.service` échoue chaque nuit à 03:00 UTC au preflight (sans lancer pg_dump)
#   et envoie 1 alerte Telegram/jour — c'est voulu (signal), pas un bug.
# - `collect_bronze` ~4,5 % d'échec : `404 Not Found` du WFS data.grandlyon.com par rafales
#   (23 h et 08 h UTC), 3 collecteurs simultanés → panne amont, rien à corriger côté projet.
# - `.backup-offsite.conf` : `BACKUP_MAX_TOTAL_GB` / `BACKUP_KEEP_MIN` / `BACKUP_RETENTION_DAYS`
#   à ajuster une fois la taille réelle d'un dump connue (DB ~40 Go, Drive gratuit 15 Go).
# - Vélov schéma ancien : xgboost_velov.py + gold.velov_features sur ancien
#   schéma (temperature_c, rain_mm, hour_sin). Pipeline trafic migré v0.3.1.
# - dim_spatial_grid_mapping.properties_twgid ≠ traffic_features_live.channel_id
#   (LYO00xxx) — backfill lat/lon OK, mapping identité à réconcilier.
# - /opt/lyonflow/logs/ doit être chown 50000:0 récursif après chaque rsync.
# - GNN training : code livré (stgcn_wrapper), retrain Airflow à finaliser.
# - DNS lyonflow.fr mort → accès par IP. Self-signed cert (Sprint 21 fix).
# - Prometheus supprimé Sprint 15+ (config YAML v2.54 cassée). Grafana sans source.
# - test_error_display 3 failures pré-existantes (test_persona_a_5_types).
# - OFFSITE_HOST non configuré (backup-template.sh livré, destination à choisir).
# - Connexions DB sans `application_name` → impossible d'identifier le
#   service fuyard si leak à l'avenir. Patch P2 Sprint 26+ : forcer
#   `?application_name=lyonflow-<service>` dans DATABASE_URL.
# - `gold.v_connection_health` créé Sprint 25 (migration 047) mais pas
#   encore câblé dans le healthcheck-vps.sh. À faire Sprint 26+.

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
# - Bloat osm.ways + alertes Telegram en boucle (Sprint 26) : FIXÉ (migrations 048/049,
#   hystérésis dag-monitor). Détail dans la section Sprint 26 ci-dessus.
# - Fuite connexions Postgres (Sprint 25) : FIXÉ (tcp_keepalives_idle=60 +
#   idle_in_txn=2min + vue gold.v_connection_health). Incident doc
#   docs/INCIDENTS/2026-08-22-postgres-connection-leak.md.

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
