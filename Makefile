# =============================================================================
# LyonFlowFull — Makefile
# =============================================================================
# Targets principaux : test, lint, dev, deploy, logs
# =============================================================================

.PHONY: help install lint format typecheck test test-unit test-integration \
        test-smoke coverage build up down restart logs ps shell-db shell-api \
        shell-streamlit backup restore clean seed-users docs

# Variables
PYTHON := python3
DOCKER := docker
COMPOSE := docker compose
PROJECT := lyonflowfull
# VPS (override via .deploy.env ou env vars, JAMAIS hardcoder en repo)
VPS_HOST ?= $(shell [ -f .deploy.env ] && grep -E '^VPS_HOST=' .deploy.env | cut -d= -f2 || echo "ubuntu@example.com")
SSH_KEY ?= $(shell [ -f .deploy.env ] && grep -E '^VPS_SSH_KEY=' .deploy.env | cut -d= -f2 || echo "~/.ssh/id_rsa")

help:  ## Affiche cette aide
	@echo "LyonFlowFull v0.1.0 — Makefile"
	@echo ""
	@echo "Targets disponibles :"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------------
install:  ## Installe les dépendances Python
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

install-dev:  ## Installe les dépendances dev (pytest, ruff, mypy)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio ruff mypy bandit

# -----------------------------------------------------------------------------
# Lint / Format
# -----------------------------------------------------------------------------
lint:  ## Ruff lint (bloquant)
	ruff check . --output-format=github

format:  ## Ruff format (auto-fix)
	ruff format .

format-check:  ## Vérifie format sans modifier
	ruff format --check .

typecheck:  ## Mypy type check (non bloquant)
	$(PYTHON) -m pip install mypy 2>/dev/null || true
	$(PYTHON) -m mypy src/ dags/ --ignore-missing-imports || true

security:  ## Bandit + pip-audit
	bandit -r src/ dags/ -f json -o bandit-report.json || true
	$(PYTHON) -m pip install pip-audit 2>/dev/null && $(PYTHON) -m pip_audit || true

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
test:  ## Tous les tests
	$(PYTHON) -m pytest tests/ -v

test-unit:  ## Tests persona (UI)
	$(PYTHON) -m pytest tests/persona/ -v

test-integration:  ## Tests intégration (infra)
	$(PYTHON) -m pytest tests/integration/ -v

test-smoke:  ## Tests E2E smoke (nécessite stack up)
	$(PYTHON) -m pytest tests/smoke/ -v

coverage:  ## Tests avec couverture HTML
	$(PYTHON) -m pytest tests/ --cov=src --cov=dags --cov-report=html
	@echo "Ouvrir htmlcov/index.html pour voir la couverture"

# -----------------------------------------------------------------------------
# Dev (sans Docker)
# -----------------------------------------------------------------------------
dev:  ## Lance Streamlit en local
	streamlit run dashboard/Accueil.py

dev-api:  ## Lance FastAPI en local
	uvicorn src.api.main:app --reload --port 8000

# -----------------------------------------------------------------------------
# Docker
# -----------------------------------------------------------------------------
build:  ## Build des images Docker
	$(COMPOSE) build

up:  ## Démarre la stack complète
	$(COMPOSE) up -d --build
	@echo ""
	@echo "✅ Stack démarrée. Accès :"
	@echo "  - Dashboard : http://localhost"
	@echo "  - API : http://localhost/api/health"
	@echo "  - Airflow : http://localhost/airflow"
	@echo "  - MLflow : http://localhost/mlflow"
	@echo "  - MinIO Console : http://localhost/minio"

down:  ## Stoppe la stack
	$(COMPOSE) down

restart:  ## Redémarre la stack
	$(COMPOSE) restart

ps:  ## Liste les containers
	$(COMPOSE) ps

logs:  ## Logs de tous les services (tail)
	$(COMPOSE) logs --tail=100 -f

logs-streamlit:  ## Logs Streamlit uniquement
	$(COMPOSE) logs --tail=100 -f streamlit

logs-api:  ## Logs API uniquement
	$(COMPOSE) logs --tail=100 -f api

logs-airflow:  ## Logs Airflow uniquement
	$(COMPOSE) logs --tail=100 -f airflow-webserver

# -----------------------------------------------------------------------------
# Shell interactif
# -----------------------------------------------------------------------------
shell-db:  ## Ouvre psql connecté à la DB
	$(COMPOSE) exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

shell-api:  ## Ouvre un shell dans le container API
	$(COMPOSE) exec api /bin/bash

shell-streamlit:  ## Ouvre un shell dans le container Streamlit
	$(COMPOSE) exec streamlit /bin/bash

# -----------------------------------------------------------------------------
# Maintenance
# -----------------------------------------------------------------------------
backup:  ## Backup PostgreSQL + MinIO
	./scripts/backup.sh

restore:  ## Restore depuis backup (BACKUP_FILE=path requis)
	./scripts/restore.sh $${BACKUP_FILE}

seed-users:  ## Seed les users initiaux (Pro TCL, Élu)
	$(COMPOSE) exec streamlit python scripts/seed_users.py

clean:  ## Nettoie caches, __pycache__, etc.
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Caches nettoyés"

clean-docker:  ## ⚠️ Nettoie volumes Docker (data perte !)
	@echo "⚠️  ATTENTION : va supprimer postgres_data, minio_data, airflow_data"
	@read -p "Confirmez avec 'yes' : " confirm && [ "$$confirm" = "yes" ] || exit 1
	$(COMPOSE) down -v

# -----------------------------------------------------------------------------
# Deploy VPS
# -----------------------------------------------------------------------------
deploy-vps:  ## Déploie sur le VPS (synchronise + restart)
	rsync -avz --exclude='.git' --exclude='.env' --exclude='uploads/' \
	      -e "ssh -i $(SSH_KEY)" \
	      ./ $(VPS_HOST):/opt/lyonflow/
	ssh -i $(SSH_KEY) $(VPS_HOST) "cd /opt/lyonflow && docker compose up -d --build"

# -----------------------------------------------------------------------------
# Docs
# -----------------------------------------------------------------------------
docs:  ## Ouvre la doc locale
	@echo "Documentation disponible :"
	@ls -la docs/

# -----------------------------------------------------------------------------
# Initialisation
# -----------------------------------------------------------------------------
init:  ## Premier démarrage (génère .env, démarre stack)
	@if [ ! -f .env ]; then cp .env.example .env && echo "✅ .env créé (à éditer)"; fi
	@echo "Édite .env, puis lance : make up"
