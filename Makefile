# =============================================================================
# LyonFlowFull — Makefile
# =============================================================================
# Targets principaux : test, lint, dev, deploy, logs
# =============================================================================

.PHONY: help install lint format typecheck test test-unit test-integration \
        test-smoke coverage build up down restart logs ps shell-db shell-api \
        shell-streamlit backup restore clean seed-users docs \
        deploy-vps rollback-vps tag-vps certbot-init certbot-renew \
        healthcheck-vps check-deploy-env tls-status \
        monitoring-up monitoring-down monitoring-status monitoring-logs

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

test-docker:  ## Lance tous les tests dans un container éphémère (isole les dépendances C complexes)
	docker compose run --rm api pytest tests/ -v

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
backup:  ## Backup PostgreSQL OFFSITE (gdrive ou ssh) — JAMAIS local
	./scripts/backup-offsite.sh

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
# Deploy VPS (Sprint VPS-1 + VPS-2)
# -----------------------------------------------------------------------------
check-deploy-env:  ## Vérifie .deploy.env (perms 600, vars critiques) avant deploy
	./scripts/check-deploy-env.sh .deploy.env

healthcheck-vps:  ## Healthcheck post-deploy (HTTP + DB + nginx)
	@echo "==[ HTTP /api/health ]=="
	@curl -fsS --max-time 10 http://localhost/api/health || (echo "❌ API health failed" && exit 1)
	@echo "==[ HTTP /nginx-health ]=="
	@curl -fsS --max-time 5 http://localhost/nginx-health || (echo "❌ nginx health failed" && exit 1)
	@echo "==[ DB ping ]=="
	@$(COMPOSE) exec -T postgres pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB} || (echo "❌ DB not ready" && exit 1)
	@echo "==[ TLS status (si actif) ]=="
	@if [ -f /etc/letsencrypt/live/lyonflow/fullchain.pem ]; then \
	    openssl x509 -in /etc/letsencrypt/live/lyonflow/fullchain.pem -noout -subject -dates; \
	else \
	    echo "Pas de cert Let's Encrypt (HTTP-only). Run: make certbot-init"; \
	fi
	@echo "✅ All healthchecks passed"

deploy-vps: check-deploy-env  ## Déploie sur le VPS (Sprint VPS-1+VPS-2 : tag + rsync + healthcheck)
	@echo "==[ Tag version deploy ]=="
	@$(MAKE) tag-vps
	@echo "==[ Rsync code (exclude data dirs pour preserver state VPS) ]=="
	rsync -avz \
	      --exclude='.git' \
	      --exclude='.env' \
	      --exclude='.deploy.env' \
	      --exclude='uploads/' \
	      --exclude='backups/' \
	      --exclude='postgres_data/' \
	      --exclude='minio_data/' \
	      --exclude='airflow_data/' \
	      --exclude='mlflow_data/' \
	      --exclude='grafana_data/' \
	      --exclude='prometheus_data/' \
	      -e "ssh -i $(SSH_KEY)" \
	      ./ $(VPS_HOST):/opt/lyonflow/
	@echo "==[ Restart stack ]=="
	ssh -i $(SSH_KEY) $(VPS_HOST) "cd /opt/lyonflow && docker compose up -d --build"
	@echo "==[ Healthcheck post-deploy ]=="
	ssh -i $(SSH_KEY) $(VPS_HOST) "cd /opt/lyonflow && make healthcheck-vps"
	@echo "✅ Deploy OK : $$(git describe --tags --abbrev=0)"

rollback-vps:  ## Rollback deploy VPS vers tag précédent (Sprint VPS-2)
	@PREV=$$(git tag --list 'vps-*' --sort=-version:refname | sed -n '2p'); \
	if [ -z "$$PREV" ]; then echo "❌ Pas de tag vps-* précédent"; exit 1; fi; \
	echo "Rollback vers $$PREV"; \
	git checkout $$PREV && \
	ssh -i $(SSH_KEY) $(VPS_HOST) "cd /opt/lyonflow && git fetch && git checkout $$PREV && docker compose up -d --build" && \
	git checkout -
	@echo "✅ Rollback OK"

tag-vps:  ## Tag le commit actuel avec la date (Sprint VPS-2)
	@TAG="vps-$$(date +%Y%m%d-%H%M%S)"; \
	git tag -a $$TAG -m "VPS deploy $$TAG" && \
	echo "✅ Tag créé : $$TAG"

# -----------------------------------------------------------------------------
# TLS Let's Encrypt (Sprint VPS-1)
# -----------------------------------------------------------------------------
certbot-init:  ## Init certbot Let's Encrypt (1ere fois, interactif)
	@echo "==[ Install certbot si manquant ]=="
	@if ! command -v certbot >/dev/null 2>&1; then \
	    sudo apt update && sudo apt install -y certbot python3-certbot-nginx; \
	fi
	@echo "==[ Génère cert pour ton domaine ]=="
	@read -p "Domaine (ex: lyonflow.fr) : " DOMAIN; \
	if [ -z "$$DOMAIN" ]; then echo "❌ Domaine requis"; exit 1; fi; \
	sudo certbot --nginx -d $$DOMAIN --non-interactive --agree-tos -m admin@$$DOMAIN
	@echo "✅ Cert généré. Test : https://$$DOMAIN"

certbot-renew:  ## Renouvelle les certs Let's Encrypt (cron systemd certbot.timer)
	sudo certbot renew --nginx --quiet
	@echo "✅ Certs vérifiés. Voir status : make tls-status"

tls-status:  ## Status des certs TLS
	@sudo certbot certificates 2>/dev/null | head -30 || echo "Certbot non installé"

# -----------------------------------------------------------------------------
# Backup VPS offsite (Sprint VPS-2)
# -----------------------------------------------------------------------------
backup-offsite:  ## Push backup vers serveur distant (rsync over SSH)
	@if [ -z "$$OFFSITE_HOST" ]; then \
	    echo "❌ OFFSITE_HOST non défini. Ajouter à .deploy.env : OFFSITE_HOST=user@backup.example.com"; \
	    exit 1; \
	fi
	@rsync -avz --delete -e "ssh -i $(SSH_KEY)" \
	    backups/ $$OFFSITE_HOST:~/lyonflow-backups/
	@echo "✅ Backup offsite synced"

# -----------------------------------------------------------------------------
# Monitoring (Sprint VPS-3) — Prometheus + Alertmanager + Grafana
# -----------------------------------------------------------------------------
MONITORING_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.monitoring.yml

monitoring-up:  ## Démarre la stack monitoring (Prometheus + Grafana + Alertmanager)
	$(MONITORING_COMPOSE) up -d prometheus alertmanager grafana node-exporter postgres-exporter nginx-exporter redis-exporter
	@echo ""
	@echo "✅ Stack monitoring démarrée :"
	@echo "  - Prometheus    : http://localhost:9090"
	@echo "  - Alertmanager  : http://localhost:9093"
	@echo "  - Grafana       : http://localhost:3000 (admin / \$$GRAFANA_ADMIN_PASSWORD)"
	@echo ""
	@echo "⚠️  Expose via Nginx sur /grafana/, /prometheus/, /alertmanager/"

monitoring-down:  ## Stoppe la stack monitoring
	$(MONITORING_COMPOSE) stop prometheus alertmanager grafana node-exporter postgres-exporter nginx-exporter redis-exporter

monitoring-status:  ## Status des services monitoring
	@$(MONITORING_COMPOSE) ps prometheus alertmanager grafana node-exporter postgres-exporter nginx-exporter redis-exporter 2>/dev/null || echo "Stack monitoring pas démarrée"
	@echo ""
	@echo "==[ Targets Prometheus ]=="
	@curl -fsS http://localhost:9090/api/v1/targets 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f\"  {t['labels']['job']:20s} {t['health']:10s} {t['lastScrape'][:19]}\") for t in d.get('data',{}).get('activeTargets',[])]" 2>/dev/null || echo "  (Prometheus pas accessible)"
	@echo ""
	@echo "==[ Alertes actives ]=="
	@curl -fsS http://localhost:9090/api/v1/alerts 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f\"  [{a['labels']['severity']}] {a['labels']['alertname']}: {a['annotations']['summary']}\") for a in d.get('data',{}).get('alerts',[])]" 2>/dev/null || echo "  (Prometheus pas accessible)"

monitoring-logs:  ## Logs monitoring
	$(MONITORING_COMPOSE) logs -f prometheus alertmanager grafana

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
