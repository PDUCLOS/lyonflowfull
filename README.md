# LyonFlow

**Plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal sur la Métropole de Lyon.**

[![Version](https://img.shields.io/badge/version-0.12.1-blue)]()
[![Branche](https://img.shields.io/badge/branche-vps%20(prod)-success)]()
[![Tests](https://img.shields.io/badge/tests-620%20verts-brightgreen)]()
[![Licence](https://img.shields.io/badge/licence-MIT-lightgrey)]()

Auteur : **Patrice DUCLOS** — Senior Data Analyst, Jedha RNCP 38777 (Architecte en IA)
Repo : `PDUCLOS/lyonflow` · Déploiement production : VPS unique `51.83.159.224`

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture](#2-architecture)
3. [Stack technique](#3-stack-technique)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Utilisation](#6-utilisation)
7. [Développement](#7-développement)
8. [Tests](#8-tests)
9. [Déploiement](#9-déploiement)
10. [RGPD](#10-rgpd)
11. [État du projet & prochaines étapes](#11-état-du-projet--prochaines-étapes)
12. [Contribution](#12-contribution)

---

## 1. Vue d'ensemble

LyonFlow fusionne trois projets en une plateforme unifiée : ingestion temps réel
(9 sources open data), pipeline Medallion Bronze→Silver→Gold sur PostgreSQL,
modèles ML (trafic, bus, vélos en libre-service), routage multimodal
(pgRouting), et un dashboard Streamlit à 3 personas.

### Les 3 personas

| Persona | Cible | Pages | Auth |
|---|---|---|---|
| Usager | Grand public | 5 (Mon Trajet, Alertes, Notre Modèle, Sources Données, Statut Service) | Non |
| Pro TCL | Opérateurs réseau (Keolis) | 6 (PCC Live, Heatmap OTP, Corrélation, Simulateur, Pipeline Mgmt, Model Monitoring) | Oui |
| Élu | Décideurs Grand Lyon | 5 (Synthèse, Bottlenecks, Avant/Après, Simulateur, Rapport PDF) | Oui |

**18 pages × 3 personas + Accueil + RGPD + À propos — 59 widgets.**

### Les 4 piliers ML

1. **Trafic routier** — XGBoost H+1h (retrain toutes les 30 min), focus fiabilité production
2. **Bus TCL** — analyse SIRI Lite (retard par tronçon/ligne/heure) + diagnostic infrastructure
3. **Vélov** — XGBoost H+1h, label encoding stations (~458 stations, économe en RAM)
4. **Recommandation trajet** — voiture (pgRouting `pgr_dijkstra` sur réseau OSM), bus/tram (SIRI), Vélov (scoring composite), marche, métro (GTFS) — scoring 50% temps + 30% coût + 20% CO₂

### Le différenciateur clé

Le croisement spatial **bus × trafic** (`gold.mv_bus_traffic_spatial`, JOIN 100m)
identifie les zones où un retard bus coïncide avec une congestion routière —
signal d'un problème d'infrastructure (voie dédiée à créer) plutôt
qu'opérationnel.

---

## 2. Architecture

Architecture Medallion (Bronze → Silver → Gold) sur PostgreSQL + PostGIS + pgRouting :

```
┌──────────── 9 sources open data ────────────┐
│ Grand Lyon (trafic, chantiers), TCL SIRI,   │
│ Vélo'v GBFS, Open-Meteo (météo + air),      │
│ Vigilance météo, TomTom, calendriers...     │
└────────────────┬─────────────────────────────┘
                 │  Airflow — collecte 5min → 6h selon source
                 ▼
        ┌────────────────┐
        │  BRONZE layer  │  Raw JSONB, immutable
        └────────┬───────┘
                 │  Transforms psycopg2 (dédup, parse, géo)
                 ▼
        ┌────────────────┐
        │  SILVER layer  │  Nettoyé, normalisé
        └────────┬───────┘
                 │  Feature engineering
                 ▼
        ┌────────────────┐
        │   GOLD layer   │  Features ML-ready + vues métier
        └────────┬───────┘
                 │
        ┌────────┴────────┐        ┌──────────────────┐
        │  XGBoost H+1h   │        │  osm.* (pgRouting) │
        │  trafic/vélov   │        │  routage voiture   │
        └────────┬────────┘        └─────────┬──────────┘
                 │                            │
        ┌────────┴────────────────────────────┴────────┐
        │        FastAPI + Streamlit (3 personas)       │
        └────────────────────────────────────────────────┘
```

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) et
[docs/diagrams/](docs/diagrams/) (6 schémas drawio détaillés) pour le détail complet.

---

## 3. Stack technique

| Couche | Technologie |
|---|---|
| Orchestration | Apache Airflow 2.9 |
| Base de données | PostgreSQL 16 + PostGIS 3.5 + **pgRouting 3.7.3** (schémas bronze/silver/gold/osm/referentiel/rgpd) |
| Storage objet | MinIO (S3-compatible) — archivage silver > 7j |
| ML Tracking / Registry | MLflow 2.12 |
| ML Trafic | XGBoost H+1h |
| ML Vélov | XGBoost H+1h (label encoding) |
| ML Bus | XGBoost delay (phase analyse) |
| API | FastAPI + Uvicorn |
| Dashboard | Streamlit multi-pages |
| Monitoring | Prometheus + Alertmanager + Grafana |
| Transformation | psycopg2 pur (pas de Polars dans Airflow) |
| CI/CD | GitHub Actions |
| Infra | Docker Compose |
| Reverse proxy | Nginx 1.27 |

---

## 4. Installation

### Pré-requis

- Docker 24+ et Docker Compose v2+
- 6 CPU, 12 GB RAM, 100 GB SSD (minimum recommandé)
- Python 3.12+ (pour dev local sans Docker)

### Démarrage rapide (Docker)

```bash
# 1. Cloner
git clone https://github.com/PDUCLOS/lyonflow.git
cd lyonflow

# 2. Configurer
cp .env.example .env
# Éditer .env et remplir POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, etc.

# 3. Démarrer
docker compose up -d --build

# 4. Vérifier
docker compose ps
docker compose logs -f streamlit
```

L'app est accessible sur http://localhost (port 80, Nginx).

### Dev local (sans Docker)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL + PostGIS + pgRouting local
createdb lyonflow
psql lyonflow < deploy/init-db.sql

cp .env.example .env
export $(cat .env | xargs)

streamlit run dashboard/Accueil.py
```

---

## 5. Configuration

Variables d'environnement (voir `.env.example`) :

| Variable | Obligatoire | Usage |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` / `POSTGRES_DB` | oui | DB |
| `MLFLOW_TRACKING_URI` | oui | MLflow server |
| `LYONFLOW_API_KEY` | oui | Auth FastAPI (header `X-API-Key`) |
| `AIRFLOW_FERNET_KEY` | oui | Chiffrement Airflow |
| `LYONFLOW_DEMO_MODE` | oui | **Doit être `0` en prod** — zéro mock |
| `TOMTOM_API_KEY` | non | Cross-validation trafic (free tier 2500 req/j) |
| `LYON_DEFAULT_SPEED` | non (30.0) | Vitesse imputation fallback |
| `LYON_LATITUDE` / `LYON_LONGITUDE` | non | Centre carte par défaut (45.7640 / 4.8357) |

---

## 6. Utilisation

### Usager (grand public)

- http://localhost — pas d'auth
- "Mon Trajet" (ex : Villeurbanne → Part-Dieu), Alertes, Notre Modèle, Statut Service

### Pro TCL (opérateur)

- Sélectionner le persona "Pro TCL", auth par mot de passe env
- Carte live, heatmap OTP, corrélation bus×trafic, simulateur, monitoring modèle

### Élu (décideur)

- Sélectionner le persona "Élu", auth par mot de passe env
- Synthèse exécutive, bottlenecks classés ROI, génération PDF rapport

### API REST

```bash
curl http://localhost/api/health

curl -X POST http://localhost/api/v1/predict/traffic \
  -H "X-API-Key: <LYONFLOW_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "LYO00042", "horizon_minutes": 60}'
```

Voir [docs/API.md](docs/API.md) pour la référence complète.

---

## 7. Développement

### Structure du projet

```
lyonflow/
├── dags/                   # Airflow DAGs (bronze/, transforms/, ml/, maintenance/)
├── src/
│   ├── config.py           # Pydantic settings
│   ├── data/                # Accès données (data_loader, db_query — fail loud, zéro mock)
│   ├── ingestion/           # Collecteurs (DataCollector ABC)
│   ├── transformation/      # Bronze→Silver→Gold, data quality
│   ├── models/              # XGBoost trafic/vélov/bus
│   ├── routing/             # Recommandation multimodale
│   ├── monitoring/          # Drift (PSI)
│   ├── rgpd/                # Consentement, audit
│   ├── governance/          # Data dictionary, lineage
│   ├── reporting/           # Génération PDF
│   └── api/                 # FastAPI
├── dashboard/
│   ├── components/widgets/  # 59 widgets (usager/pro_tcl/elu/common)
│   └── pages/                # 18 pages × 3 personas
├── scripts/
│   ├── sql/                  # Migrations
│   └── *.sh                  # Healthcheck, backup, déploiement
├── tests/                    # pytest (unit, persona, integration, e2e)
├── docs/                      # Documentation + docs/diagrams/ (schémas drawio)
├── monitoring/                # Config Prometheus/Grafana/Alertmanager
├── nginx/                      # Config reverse proxy
├── docker-compose.yml
├── docker-compose.monitoring.yml
└── Dockerfile
```

### Conventions de code

- Anglais pour le code (variables, fonctions, classes) — français pour docstrings métier
- **SQL paramétré partout** (`%s` psycopg2), zéro f-string SQL
- Zéro credential en dur — toujours via `os.getenv()`
- Tests pytest pour chaque module, type hints partout

Voir [AGENTS.md](AGENTS.md) pour les conventions détaillées.

---

## 8. Tests

```bash
pytest tests/ -v --tb=short           # suite complète (exclut integration par défaut)
pytest tests/ -m integration          # tests nécessitant le stack démarré
pytest tests/ --cov=src --cov=dags --cov-report=html
```

**620 tests** (23 integration exclus par défaut, nécessitent le stack Docker démarré).

---

## 9. Déploiement

**Cible production unique : VPS** (`51.83.159.224`, Ubuntu, 6 CPU / 12 GB RAM, 2× 100 GB SSD).
Branche `vps` = source de vérité du déploiement actif.

```bash
make check-deploy-env       # vérifie .deploy.env (chmod 600 + vars critiques)
make deploy-vps              # rsync + restart systemd
./scripts/healthcheck-vps.sh  # 20+ checks (containers, disque, DB, endpoints)
make rollback-vps            # rollback dernière release
make monitoring-up           # stack Prometheus/Grafana/Alertmanager
make tls-status               # statut cert Let's Encrypt
```

Docs : [docs/VPS_HARDENING.md](docs/VPS_HARDENING.md) ·
[docs/MONITORING.md](docs/MONITORING.md) ·
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

### Branches dormantes (futur AWS/GCP — ne pas merger)

| Branche | État | Cible future |
|---|---|---|
| `kubernetes` | dormante | EKS / GKE |
| `cloud-demo` | dormante | POC Scaleway / AWS ponctuel |

---

## 10. RGPD

Voir [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md) pour le détail.

- Aucune donnée personnelle nominative collectée (open data uniquement)
- Consentement utilisateur (`rgpd.*`), audit des purges (`rgpd.purge_log`)
- Purge automatique Bronze/Silver/Gold par rétention (Airflow, DAG `purge_bronze`)
- Page conformité dans le dashboard (`RGPD_Conformite`)

---

## 11. État du projet & prochaines étapes

**Statut actuel** : production VPS stable — 18 pages / 59 widgets, 27 DAGs Airflow
(25 actifs, 2 pausés intentionnellement), zéro mock en production, pipeline
Medallion complet (9 sources → Bronze → Silver → Gold), routage voiture temps réel
(pgRouting), monitoring Prometheus/Grafana déployé.

**Axes en cours ou à venir** :
- Qualité des données (validateurs `data_quality.py`, contrôle continu)
- Report modal Vélov ↔ transports en commun (proximité spatiale)
- Propagation de congestion (corrélation spatiale/temporelle)
- Météo comme variable d'interaction quantifiée par mode de transport
- Phase cloud (Kubernetes / démo publique) — dormante, hors périmètre VPS actuel

---

## 12. Contribution

1. Fork le repo
2. Créer une branche feature (`git checkout -b feature/ma-feature`)
3. Commiter (`git commit -m "feat: ma feature"`)
4. Pousser (`git push origin feature/ma-feature`)
5. Ouvrir une Pull Request

Standards : tests pytest, ruff lint (CI bloquant), type hints, pas de credential en dur, pas de f-string SQL.

---

## Licence

MIT — voir [LICENSE](LICENSE).

## Contact

Patrice DUCLOS — [PDUCLOS](https://github.com/PDUCLOS) sur GitHub.
