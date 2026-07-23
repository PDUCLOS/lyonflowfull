# Structure du repo — LyonFlow

## Arbre annote

```
lyonflow/
├── CLAUDE.md                # Project memory (instructions repo)
├── AGENTS.md                # Conventions equipe
├── README.md                # Entry point lecture rapide
├── CHANGELOG.md             # Releases versionnees
├── CONTRIBUTING.md          # Guide contrib
├── SECURITY.md              # Politique vulnerabilites
├── LICENSE
│
├── .env.example             # Template variables d'env
├── .deploy.env.example      # Template specifique VPS prod
├── .gitignore               # Secrets, builds, IDE, K8s sealed
├── .dockerignore            # Exclusions docker build
├── .editorconfig            # Conventions editeur (tabs/spaces)
│
├── docker-compose.yml       # Stack Phase 1 (12 services local)
├── Dockerfile               # Image runtime Phase 1 (VPS)
│
├── pyproject.toml           # Config Python (ruff, mypy, pytest)
├── requirements.txt         # Dependances pin (Phase 1 + 2 + 3)
│
├── src/                     # ─── CODE METIER ─────────────────────
│   ├── config.py            #   Settings Pydantic (env loader)
│   ├── api/                 #   FastAPI (endpoints, middleware, models)
│   ├── ingestion/           #   8 collecteurs Bronze (ABC + concrets)
│   ├── transformation/      #   Bronze→Silver, Silver→Gold (set-based)
│   ├── models/              #   Wrappers ML (XGBoost, GNN)
│   ├── ml/                  #   Registry MLflow
│   ├── routing/             #   Recommandation multimodale
│   ├── db/                  #   SQLAlchemy + psycopg2 helpers
│   ├── data/                #   db_query + data_loader (Sprint 6)
│   ├── monitoring/          #   Health checks
│   ├── governance/          #   Data dictionary + lineage
│   ├── persona/             #   Auth + manager 3 personas
│   ├── rgpd/                #   Consentement + DSR + audit
│   └── reporting/           #   PDF renderer (WeasyPrint + reportlab)
│
├── dags/                    # ─── AIRFLOW DAGS ─────────────────────
│   ├── bronze/              #   collect_bronze, collect_calendriers
│   ├── transforms/          #   bronze→silver, silver→gold, spatial
│   ├── ml/                  #   retrain XGBoost, retrain GNN
│   ├── maintenance/         #   data quality, purge, drift
│   └── utils/               #   alerting, helpers
│
├── training/                # ─── ML TRAINING ─────────────────────
│   └── stgcn/               #   SpatioTemporalGCN (model, dataset, train, CLI)
│
├── dashboard/               # ─── STREAMLIT ───────────────────────
│   ├── Accueil.py           #   Page d'accueil + selecteur persona
│   ├── pages/               #   18 pages (3 personas + RGPD + A propos)
│   └── components/          #   data_loader, theme, sidebar
│
├── tests/                   # 104 tests
│   ├── smoke/               #   tests rapides
│   ├── unit/                #   tests unitaires modules
│   ├── integration/         #   tests DB + API
│   └── ml/                  #   tests modeles + GNN (skip si torch absent)
│
├── deploy/                  # SQL bootstrap
│   └── init-db.sql          #   Schemas bronze/silver/gold + tables + index
│
├── alembic/                 # Migrations Postgres
│   ├── env.py
│   └── versions/
│
├── scripts/                 # Ops scripts Phase 1
│   ├── seed_users.py        #   Bootstrap users dev
│   ├── backup.sh            #   Dump VPS
│   └── restore.sh           #   Restore VPS
│
├── config/                  # YAML config
│   └── personas.yaml        #   3 personas (Usager / Pro TCL / Elu)
│
├── nginx/                   # Reverse proxy config Phase 1
│
├── .streamlit/              # Theme Streamlit
│
├── .github/                 # CI/CD
│   ├── workflows/
│   │   ├── ci.yml           #   Phase 1 : lint, tests, docker, Trivy
│   │   └── k8s-images.yml   #   Phase 2 : buildx multi-arch ghcr push
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── kubernetes/              # ─── PHASE 2 ─────────────────────────
│   ├── README.md            #   Architecture + statut
│   ├── base/                #   Kustomize manifests
│   │   ├── namespace.yaml + NetworkPolicy
│   │   ├── postgres/        #   StatefulSet + backup CronJob
│   │   ├── redis/
│   │   ├── mlflow/
│   │   ├── airflow/         #   Helm values
│   │   ├── fastapi/         #   Deploy + HPA + Ingress + PDB
│   │   ├── streamlit/       #   Deploy + HPA + Ingress sticky-session
│   │   ├── secrets/         #   SealedSecret template
│   │   ├── monitoring/      #   ServiceMonitor + alertes
│   │   └── gnn-trainer/     #   CronJob GPU
│   ├── overlays/
│   │   ├── dev/             #   1 replica, hosts -dev
│   │   └── prod/            #   3-15 replicas, ressources prod
│   ├── docker/              #   4 Dockerfiles (api, dashboard, airflow, gnn)
│   ├── scripts/             #   bootstrap, seal-secrets, backup, migrate
│   ├── loadtest/            #   k6 + locust + run-loadtest.sh
│   └── docs/                #   DEPLOY, RUNBOOK, DECOMMISSION
│
├── cloud-demo/              # ─── PHASE 3 ─────────────────────────
│   ├── README.md
│   ├── terraform/           #   Scaleway Kapsule ephemere
│   ├── overlays/jedha-demo/ #   Extends kubernetes/base
│   ├── scripts/             #   spin-up, tear-down, seed-demo-data
│   └── docs/                #   SOUTENANCE_RNCP_38777, DEMO_SCRIPT
│
├── docs/                    # Documentation projet
│   ├── ARCHITECTURE.md      #   Phase 1
│   ├── API.md
│   ├── DEPLOYMENT.md        #   Phase 1 VPS
│   ├── DATA_GOVERNANCE.md
│   ├── EC2_TRAINING_GUIDE.md
│   ├── RUNBOOK.md
│   ├── K8S_MIGRATION_PLAN.md     # Plan Phase 2 (source de verite)
│   ├── CLOUD_DEPLOY_OPTIONS.md   # Comparatif providers Phase 3
│   ├── PIPELINE_AUDIT_AND_PLAN.md
│   ├── ADR/                  # Architecture Decision Records
│   ├── GIT_STRUCTURE.md     # Ce qu'est le repo Git (4 branches)
│   └── REPO_STRUCTURE.md    # CE FICHIER (arbre annote)
│
├── archive/                 # Documents historises (plus actifs mais conserves)
│   ├── sprints/             #   Rapports sprints 1-7 + VPS-5/6/8 + Sprint 9+
│   ├── audits/              #   Audits 2026-06-12 et corrections trackers
│   ├── analysis/            #   Analyses des 3 repos sources pre-fusion
│   └── misc/                #   B4_CANCELLED, autres decisions archivees
│
└── SPRINT_*_REPORT.md       # Rapports sprints 1-7 (archivés — voir archive/sprints/)
```

## Conventions fichiers

| Pattern | Convention | Exemple |
|---------|-----------|---------|
| Code Python | `snake_case.py` | `bronze_to_silver.py` |
| YAML K8s | `kebab-case.yaml` | `service-monitor.yaml` |
| Docs | `UPPERCASE.md` | `RUNBOOK.md` |
| Scripts shell | `kebab-case.sh` + `chmod +x` | `bootstrap-cluster.sh` |
| Tests | `test_<module>.py` | `test_silver_to_gold.py` |

## Where-to-find-what

| Je cherche | Aller dans |
|-----------|-----------|
| Comment ajouter un collecteur Bronze | `src/ingestion/base.py` (ABC) puis nouveau fichier |
| Une feature ML | `src/models/` + `training/` + tests/ml/ |
| Une page dashboard | `dashboard/pages/` |
| Une route API | `src/api/main.py` |
| Une transformation SQL | `src/transformation/silver_to_gold.py` |
| Le schema Postgres | `deploy/init-db.sql` |
| Une migration Alembic | `alembic/versions/` |
| Un DAG Airflow | `dags/<phase>/` |
| Un manifest K8s | `kubernetes/base/<service>/` ou overlay |
| Un script ops VPS | `scripts/` |
| Un script ops K8s | `kubernetes/scripts/` |
| Un script demo cloud | `cloud-demo/scripts/` |
| Un test | `tests/<type>/` |
| Une variable d'env | `src/config.py` + `.env.example` |
| Une regle de securite | `SECURITY.md` + `CLAUDE.md` securite |

## Tailles approximatives (a la release v0.4.0)

| Composant | Lignes | Fichiers |
|-----------|--------|----------|
| `src/` (code metier) | ~6500 | 48 |
| `dags/` (Airflow) | ~700 | 9 |
| `dashboard/` (Streamlit) | ~3500 | 22 |
| `training/` (GNN) | ~1200 | 5 |
| `tests/` | ~2800 | 11 |
| `kubernetes/` (manifests) | ~1800 | 35 |
| `cloud-demo/` (Phase 3) | ~800 | 15 |
| Docs MD | ~6000 | 25 |
| **Total** | **~23 000** | **~170** |
