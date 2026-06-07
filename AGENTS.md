# =============================================================================
# LyonFlowFull — AGENTS.md (mémoire projet pour assistants IA)
# =============================================================================
# Ce fichier est la source de vérité sur les décisions de phase et conventions
# du projet. À lire en premier par tout assistant IA.
# =============================================================================

# Phases du projet (état 2026-06-07)
# --------------------------------

# PHASE 1 (livrée) — Production-ready LOCAL (branche `main`)
# - Tout le code fonctionne via `docker compose up -d --build`
# - Dashboard via `streamlit run dashboard/Accueil.py`
# - 3 personas (usager, pro_tcl, elu) naviguent
# - 8 collecteurs Bronze, transforms Silver/Gold, ML XGBoost, FastAPI, RGPD
# - 47+ tests passent (`pytest tests/`)
#
# PHASE 2 (ACTIVE) — Déploiement VPS production (branche `vps`)
# - Cible production unique : VPS 51.83.159.224
# - Sprints VPS 1-4 livrés :
#   * VPS-1 : TLS Let's Encrypt + healthcheck + hardening SSH/firewall
#   * VPS-2 : systemd unit + backup timer + rollback + CI vps branch
#   * VPS-3 : Prometheus + Alertmanager + Grafana + exporters (node, postgres, nginx, redis)
#   * VPS-4 : métriques FastAPI custom (predictions, latency, personas, DAGs, MLflow, DB)
# - Docs : docs/VPS_HARDENING.md, docs/MONITORING.md, docs/CONTROLE_VPS_VS_CLOUD_DEMO.md
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

# Conventions de code
# -------------------
# - Python 3.12+
# - SQL paramétré psycopg2 %s (jamais f-string)
# - Pas de credentials en dur (os.getenv() partout)
# - Code (variables, fonctions) en ANGLAIS
# - Commentaires / docstrings en FRANÇAIS
# - Ruff lint (line-length 120)
# - Type hints partout (mypy non bloquant)
# - pytest pour chaque module

# Personas & accès
# ----------------
# - Usager : pas d'auth (accès public)
# - Pro TCL : auth par mot de passe (env PERSONA_PRO_TCL_PASSWORD) OU login user
# - Élu : auth par mot de passe (env PERSONA_ELU_PASSWORD) OU login user
# - 3 personas dans 1 dashboard, switcher dans la sidebar
# - Fichiers pages : Usager_*.py, Pro_*.py, Elu_*.py (avec préfixe ordre)

# Dette technique connue
# -----------------------
# - data binding : 41 widgets Streamlit utilisent encore du mock data
#   (cf SPRINT_6_WIDGET_MIGRATION_CHECKLIST.md)
# - GNN training : code livré, retrain Airflow planifié
# - Composant React deck.gl : pas encore intégré
# - Tests E2E Playwright : pas en place
#
# Résolu en Phase 2 (vps) :
# - Métriques Prometheus : OK (Sprint VPS-3 + VPS-4)
# - Backup auto : OK (Sprint VPS-2, timer systemd)
# - TLS production : OK (Sprint VPS-1, Let's Encrypt)

# Règles strictes
# ---------------
# 1. Pas de push git sans accord explicite
# 2. Pas de modif sur VPS sans accord explicite
# 3. SQL paramétré PARTOUT
# 4. Pas de credentials en dur
# 5. Containers non-root
# 6. Pas de merge `kubernetes` ou `cloud-demo` dans `vps` ou `main` (dormantes AWS/GCP)

# Liens utiles
# ------------
# - Repo GitHub : https://github.com/PDUCLOS/lyonflowfull
# - Issue tracker : GitHub Issues
# - CI : GitHub Actions (.github/workflows/ci.yml)
# - Docs : /docs/ (README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE)
