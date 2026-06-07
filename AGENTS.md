# =============================================================================
# LyonFlowFull — AGENTS.md (mémoire projet pour assistants IA)
# =============================================================================
# Ce fichier est la source de vérité sur les décisions de phase et conventions
# du projet. À lire en premier par tout assistant IA.
# =============================================================================

# Phases du projet (état 2026-06-06)
# --------------------------------

# PHASE 1 (en cours) — Production-ready LOCAL
# - Tout le code doit fonctionner via `docker compose up -d --build`
# - Le dashboard doit se lancer via `streamlit run dashboard/Accueil.py`
# - Les 3 personas (usager, pro_tcl, elu) doivent naviguer
# - Les 8 collecteurs Bronze, transforms Silver/Gold, ML XGBoost, FastAPI, RGPD
# - Les 47 tests doivent passer (`pytest tests/`)
# - DB local (docker) ou VPS PostgreSQL (51.83.159.224:5432)
#
# PHASE 2 (à venir — K8s dans un AUTRE répertoire) — NON ENCORE DÉMARRÉ
# - Le user fournira un autre répertoire pour K8s
# - Sera fait uniquement après validation Phase 1
# - PAS dans ce repo
# - kompose ou manifests custom
#
# PHASE 3 (à venir — cloud démo Jedha) — après Phase 1 + Phase 2
# - Déploiement sur cloud public (OVH, Scaleway, etc.)
# - Pour certification Jedha RNCP 38777

# Déploiement VPS
# ---------------
# - VPS : 51.83.159.224 (Ubuntu, 6 CPU, 12 GB RAM, 100 GB SSD)
# - SSH key : ~/.ssh/lyonflow_deploy
# - DB : PostgreSQL 16 sur le VPS (conservera la base actuelle trafficlyon)
# - Ancien projet trafficlyon en /opt/lyonflow/ — sera REMPLACÉ par LyonFlowFull
#   MAIS en gardant la base PostgreSQL (les données sont OK)
# - NE PAS TOUCHER AU VPS tant que l'utilisateur n'a pas donné le feu vert
# - Vérifier l'état du disque avant tout : df -h / (souvent à 100%)

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
# - data binding : widgets Streamlit utilisent encore du mock data (src/data/mock/)
#   Sprint 6+ = remplacer par requêtes DB réelles
# - GNN : pas encore de training (seulement XGBoost)
# - Composant React deck.gl : pas encore intégré
# - Métriques Prometheus : pas en place
# - Backup auto : pas en place
# - K8s : pas en place (sera Phase 2)
# - Tests E2E Playwright : pas en place

# Règles strictes
# ---------------
# 1. Pas de push git sans accord explicite
# 2. Pas de modif sur VPS sans accord explicite
# 3. SQL paramétré PARTUT
# 4. Pas de credentials en dur
# 5. Containers non-root

# Liens utiles
# ------------
# - Repo GitHub : https://github.com/PDUCLOS/lyonflowfull
# - Issue tracker : GitHub Issues
# - CI : GitHub Actions (.github/workflows/ci.yml)
# - Docs : /docs/ (README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE)
