# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [0.6.0] - 2026-06-07 — VPS production (branche `vps`, ACTIVE)

**Décision déploiement : VPS unique.** Branche `vps` = source de vérité du
déploiement actif. Les branches `kubernetes` et `cloud-demo` restent dormantes,
préparées pour un futur déploiement AWS/GCP, **non mergées dans `vps` ou `main`**.

### Sprint VPS-1 — TLS + hardening

- **TLS Let's Encrypt** via certbot (`make certbot-init`, `make certbot-renew`)
- **nginx/ssl.conf** : HSTS, ciphers modernes, OCSP stapling
- **scripts/check-deploy-env.sh** : vérifie `.deploy.env` chmod 600 + vars critiques
- **docs/VPS_HARDENING.md** : SSH key-only, ufw firewall, fail2ban, users dédiés
- **make healthcheck-vps**, **make tls-status**

### Sprint VPS-2 — systemd + backup + rollback

- **scripts/systemd/lyonflow.service** : process supervisor
- **scripts/systemd/lyonflow-backup.timer** + `.service` : backup quotidien 03:00
- **scripts/backup.sh** + **scripts/restore.sh** : pg_dump compressed + rétention 30j
- **make rollback-vps** : rollback automatique dernière release
- **make tag-vps** : tag versionné déploiements
- CI `.github/workflows/ci.yml` : branche `vps` ajoutée

### Sprint VPS-3 — monitoring Prometheus / Grafana / Alertmanager

- **docker-compose.monitoring.yml** : Prometheus, Alertmanager, Grafana,
  node-exporter, postgres-exporter, nginx-exporter, redis-exporter
- **monitoring/prometheus/prometheus.yml** : scrape 15s, rétention 30j
- **monitoring/prometheus/rules/** : alertes api.yml, database.yml, system.yml
- **monitoring/alertmanager/alertmanager.yml** : webhook Discord/Slack
- **monitoring/grafana/dashboards/** : lyonflow-overview.json + lyonflow-business.json
- **nginx stub_status** sur localhost+Docker networks pour nginx-exporter
- **docs/MONITORING.md** : guide complet
- **make monitoring-up/down/status/logs**

### Sprint VPS-4 — métriques FastAPI custom

- **src/api/metrics.py** : Counter/Histogram/Gauge custom
  - `lyonflow_predictions_total` (model, horizon, status)
  - `lyonflow_prediction_latency_seconds` (model)
  - `lyonflow_persona_requests_total` (persona, endpoint)
  - `lyonflow_dag_runs_total` (dag_id, state)
  - `lyonflow_mlflow_active_runs` (experiment_name)
  - `lyonflow_db_query_duration_seconds` (query_type)
- **prometheus_fastapi_instrumentator** : expose `/metrics` standard FastAPI
  (http_requests_total, http_request_duration_seconds, process_*)
- Instrumentation `/api/v1/predict/traffic` + `/api/v1/predict/velov`

### Audit isolation

- **docs/CONTROLE_VPS_VS_CLOUD_DEMO.md** : matrice 3 contextes (VPS / K8s / cloud-demo)
  - Isolation physique VPS ↔ cloud-demo (cluster Scaleway séparé)
  - Isolation logique VPS ↔ K8s (namespace + NetworkPolicy)
  - Garde-fous PostgreSQL prod (volume `/opt/lyonflow/postgres_data`)

## [0.5.0-rc1] - 2026-06-07 — Phase 3 Cloud demo Jedha (branche `cloud-demo`, DORMANTE)

### Ajouté
- **Terraform Scaleway Kapsule** ephemere (control plane + 2 pools POP2)
- **Overlay `jedha-demo`** extends `kubernetes/base` (1 replica, hosts demo)
- **Scripts** `spin-up.sh` / `tear-down.sh` / `seed-demo-data.sh`
- **Docs soutenance** `SOUTENANCE_RNCP_38777.md` (pitch + Q&A + URLs)
- **DEMO_SCRIPT.md** : minute par minute 20 min + parade pannes
- Cout estime : ~0,40 €/h, ~2 € pour 3 repetitions + jour J

## [0.4.0] - 2026-06-07 — Phase 2 Kubernetes complete (branche `kubernetes`, DORMANTE)

### Ajouté
- **Kustomize base + overlays** (dev/prod) : 8 services manifests
- **Postgres StatefulSet** PostGIS 16 + PVC + backup CronJob daily
- **FastAPI/Streamlit** Deployment + HPA + Ingress TLS + PDB
- **Airflow Helm values** KubernetesExecutor + git-sync DAGs
- **Monitoring** kube-prometheus-stack + ServiceMonitor + 9 alertes
- **GNN trainer CronJob** nodeSelector GPU + tolerations + PVC weights
- **4 Dockerfiles** (api, dashboard, airflow, gnn CUDA 12.1)
- **CI workflow** `k8s-images.yml` buildx multi-arch + ghcr push + Trivy
- **Tests de charge** k6 (100 VU API) + Locust (Streamlit sessions)
- **Migration script** VPS→K8s avec checksums MD5 gold tables
- **Documentation** DEPLOY.md, RUNBOOK.md, DECOMMISSION.md

## [0.3.1] - 2026-06-07 — Fix pipeline (branche `main` + `vps`)

### Corrige
- **is_vacances/is_ferie** : 2 fonctions PL/pgSQL `_is_vacances(date)` /
  `_is_ferie(date)` enrichissent depuis bronze.calendrier_scolaire /
  bronze.jours_feries. Avant : valeur hardcodee `FALSE`.
- **N+1 SQL silver_to_gold.py** : remplace boucle Python 4 sous-queries
  par `INSERT...SELECT` avec window LAG/AVG + LATERAL meteo + JOIN
  spatial. Speedup x100 estime sur 1000 capteurs.
- **Doublon `src/ingestion/collectors.py`** : supprime (meme contenu
  que `__init__.py`).

### Change
- `src/ingestion/__init__.py` expose **classes** (lazy) au lieu d'instances
  pre-construites. Nouveaux : `REALTIME_COLLECTORS`, `MONTHLY_COLLECTORS`,
  `ALL_COLLECTOR_CLASSES`.
- DAGs `collect_bronze.py`, `collect_calendriers_monthly.py` : boucle
  `for cls in COLLECTORS` au lieu d'instanciation hardcodee.
- DAG `transform_silver_to_gold.py` : 3 fonctions Python nommees au
  lieu de lambdas (XCom serialisation propre).

### Conserve
- MinIO path dans `src/ingestion/base.py` (deprecated mais opt-in).

## [0.3.0] - 2026-06-06 — Phase 1 production-ready local (branche `main`)

### Sprint 7 — GNN training

#### Ajouté
- **SpatioTemporalGCN** PyTorch Geometric (`training/stgcn/model.py`)
- **STGCNDataset** + **STGCNTrainer** + **STGCNWrapper** production
- DAG Airflow `retrain_gnn.py` (daily 03h sur GPU)
- 19 tests (12 OK sans torch, 6 skip, 1 skip cuda.is_available)

### Sprint 6 — Couche data offline-first

#### Ajouté
- `src/data/db_query.py` (~480L) : helpers SQL parametres typeSafe
- `src/data/data_loader.py` (~280L) : cache + retry + fallback mock
- 6 widgets migres vers DB (sur 47, voir `SPRINT_6_WIDGET_MIGRATION_CHECKLIST.md`)
- Page RGPD live + 42 nouveaux tests

## [0.1.0] - 2026-06-06 — Sprint 5

### Sprint 5 — Production-ready local

#### Ajouté
- **Infrastructure** : Docker Compose (12 services), Dockerfile non-root,
  Nginx reverse proxy avec rate limiting, init-db.sql complet
- **Ingestion** : 8 collecteurs Bronze (DataCollector ABC + tenacity)
- **Transforms** : Bronze→Silver (5 transformers) + Silver→Gold (3 builders)
- **ML** : XGBoost Speed (4 horizons) + Vélov (3 horizons)
- **API** : FastAPI 8 endpoints (predict, recommend, bottlenecks, RGPD, auth)
- **RGPD** : consentement, audit log, DSR, hashing SHA256
- **Data Governance** : data dictionary, lineage, PII classification
- **Airflow** : 6 DAGs (collect, transforms, retrain, maintenance)
- **File Manager** : page upload/download Streamlit
- **CI/CD** : GitHub Actions (lint, security, tests, docker build, Trivy)
- **Documentation** : README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE
- **Monitoring** : 6 health checks + rate limit middleware
- **Sécurité** : scanning secrets, JWT auth, audit trail

### Sprint 1-4 — UI Foundation

#### Ajouté
- 3 personas (Usager, Pro TCL, Élu) avec auth par mot de passe
- 16 pages Streamlit (Mon Trajet, PCC Live, Synthèse exécutive, etc.)
- 45 widgets réutilisables
- Mock data Lyon réaliste (12 lignes TCL, 458 stations Vélov, etc.)
- Génération PDF (WeasyPrint + fallback reportlab)
- 28 tests (tous verts)
- Sélecteur de persona dans la sidebar

### Notes
- **Déploiement production actif** : VPS (branche `vps`, 0.6.0)
- Branche `kubernetes` (0.4.0) : DORMANTE, préparée AWS/GCP futur
- Branche `cloud-demo` (0.5.0-rc1) : DORMANTE, POC cloud ponctuel futur
- VPS replacement : garder PostgreSQL, remplacer le reste
