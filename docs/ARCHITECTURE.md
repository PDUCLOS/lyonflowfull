# LyonFlowFull — Architecture détaillée

## Vue d'ensemble

LyonFlowFull suit une architecture **Medallion** (Bronze → Silver → Gold)
avec 8 sources open data ingérées toutes les 5 min, transformées en
features ML-ready, et servies via API REST + dashboard multi-persona.

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCES OPEN DATA                         │
│  Grand Lyon WFS · Vélov GBFS · Open-Meteo · SIRI Lite ·    │
│  Chantiers · Calendrier · Jours fériés · Vitesses limites   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 BRONZE LAYER (immutable)                      │
│  • 8 tables bronze.* (raw_data JSONB + fetched_at)          │
│  • Backup offsite (rclone Google Drive / SSH)                 │
│  • Rétention 7-365j (purge DAG quotidien 03h)               │
└────────────────────────────┬────────────────────────────────┘
                             │  Transforms psycopg2
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 SILVER LAYER (nettoyé)                        │
│  • Dédup DISTINCT ON                                         │
│  • Parse JSON → colonnes typées                             │
│  • Géométrie WGS84 + Lamb93 (PostGIS)                       │
│  • Validation métier                                        │
│  5 tables : trafic_boucles_clean, velov_clean,              │
│             tcl_vehicles_clean, meteo_hourly, chantiers     │
└────────────────────────────┬────────────────────────────────┘
                             │  Feature engineering
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  GOLD LAYER (ML-ready)                        │
│  • Lags + deltas + temporel (sin/cos) + météo               │
│  • Label encoding stations (économie RAM)                   │
│  • Fenêtre glissante 7-14j                                  │
│  Tables : traffic_features_live, velov_features,            │
│           bus_delay_segments, infrastructure_bottlenecks,   │
│           trafic_predictions, predictions_vs_actuals        │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                ML MODELS (tracking MLflow)                   │
│  • XGBoost Speed (H+1h, focus stable depuis VPS-6)          │
│  • XGBoost Vélov (2 horizons : 30/60 min)                    │
│  • ST-GRU-GNN (Sprint 6+ : spatial dependencies)            │
│  Quality gate : MAE ≤ prev × 1.15                           │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              SERVING LAYER                                   │
│  • FastAPI REST (port 8000)                                 │
│  • Streamlit Dashboard (port 8501, 18 pages)                │
│  • Nginx reverse proxy (port 80 public)                     │
│  • Endpoints : /health, /api/v1/predict/*,                  │
│                /api/v1/recommend, /api/v1/bottlenecks,      │
│                /api/v1/rgpd/request, /api/v1/auth/login     │
└─────────────────────────────────────────────────────────────┘
```

## Architecture applicative

### Backend (Python 3.12)

```
src/
├── config.py            # Pydantic Settings (env vars)
├── db/                  # PostgreSQL connection (SQLAlchemy + psycopg2)
│   ├── __init__.py
│   └── connection.py
├── ingestion/           # Template Method pour 8 collecteurs
│   ├── base.py          # DataCollector ABC + tenacity retry
│   ├── trafic_grandlyon.py
│   ├── velov.py
│   ├── meteo.py
│   ├── air_quality.py
│   ├── chantiers.py
│   ├── tcl_siri_lite.py
│   ├── calendrier_scolaire.py
│   ├── jours_feries.py
│   └── collectors.py    # ALL_COLLECTORS = [8 instances]
├── transformation/      # psycopg2 pur (pas Polars)
│   ├── bronze_to_silver.py
│   └── silver_to_gold.py
├── models/              # XGBoost + GNN
│   ├── xgboost_speed.py
│   └── xgboost_velov.py
├── api/                 # FastAPI
│   └── main.py          # 8 endpoints
├── rgpd/                # RGPD (consent, audit, DSR)
│   └── service.py
├── governance/          # Data dictionary + lineage
│   └── data_dictionary.py
├── reporting/           # PDF (WeasyPrint + fallback reportlab)
│   └── pdf_renderer.py
├── routing/             # (Sprint 6+)
├── monitoring/          # (Sprint 6+ : Evidently)
├── api/models/          # (Sprint 6+ : SQLAlchemy ORM)
├── person/              # Persona system (Sprint 1-4)
│   ├── personas_loader.py
│   ├── manager.py
│   └── auth.py
└── data/mock/           # Mock data Lyon (Sprint 1-4)
```

### Frontend (Streamlit 1.32+)

```
dashboard/
├── Accueil.py                 # Landing avec sélecteur persona
├── components/
│   ├── persona_switcher.py
│   ├── persona_guard.py
│   ├── navigation.py
│   ├── theme.py
│   └── widgets/
│       ├── usager/             # 14 widgets
│       ├── pro_tcl/            # 25 widgets
│       └── elu/                # 20 widgets
└── pages/
    ├── Accueil.py
    ├── Usager_1_Mon_Trajet.py
    ├── Usager_2_Alertes.py
    ├── Usager_3_Notre_Modele.py         # Sprint 22+ — MLOps citoyen 🤖
    ├── Usager_4_Sources_Donnees.py      # Sprint 22+ — MLOps citoyen 🌐
    ├── Usager_5_Statut_Service.py       # Sprint 22+ — MLOps citoyen 🩺
    ├── Pro_1_PCC_Live.py
    ├── Pro_2_Heatmap_OTP.py
    ├── Pro_3_Correlation.py
    ├── Pro_4_Simulateur.py
    ├── Pro_6_Pipeline_Mgmt.py
    ├── Pro_7_Model_Monitoring.py
    ├── Elu_1_Synthese.py
    ├── Elu_2_Bottlenecks.py             # Sprint 22++ — branche sur vraies données DB
    ├── Elu_3_Avant_Apres.py
    ├── Elu_4_Simulateur.py
    ├── Elu_5_Rapport.py
    ├── 9_RGPD_Conformite.py
    └── A_Propos.py
```

> **Note historique** : `Usager_3_Favoris.py` et `Usager_4_Files.py` ont été
> remplacés par les 3 pages MLOps citoyen en Sprint 22+ (v0.12.0).
> `Pro_5_Export.py` (export SAEIV) abandonné depuis Sprint 13+ — export
> désormais via `Elu_5_Rapport.py`.

### Orchestration (Airflow 2.9)

```
dags/
├── bronze/
│   └── collect_bronze.py         # */5 * * * * (8 collecteurs parallèles)
├── transforms/
│   ├── transform_bronze_to_silver.py  # */5 * * * *
│   └── transform_silver_to_gold.py    # */10 * * * *
├── ml/
│   └── retrain_xgboost.py        # hourly :20 (trafic) et :40 (velov)
├── maintenance/
│   └── maintenance.py            # 04h15 (quality) + 03h (purge)
└── utils/                        # alerting, helpers
```

### Infrastructure (Docker Compose)

9 services conteneurisés :

| Service          | Image                        | Port | CPU  | RAM  |
|------------------|------------------------------|------|------|------|
| postgres         | postgis/postgis:16-3.4       | 5432 | 1.0  | 2 GB |
| redis            | redis:7-alpine               | 6379 | 0.5  | 512M |
| minio            | minio/minio:latest           | 9000 | 0.5  | 1 GB |
| minio-init       | minio/mc:latest              | -    | -    | -    |
| mlflow           | ghcr.io/mlflow/mlflow:v2.12  | 5000 | 0.5  | 1 GB |
| airflow-init     | lyonflow-app                 | -    | -    | -    |
| airflow-webserver| lyonflow-app                 | 8080 | 0.5  | 1.5G |
| airflow-scheduler| lyonflow-app                 | -    | 0.5  | 1.5G |
| airflow-worker   | lyonflow-app                 | -    | 1.0  | 2 GB |
| api              | lyonflow-app                 | 8000 | 0.5  | 1 GB |
| streamlit        | lyonflow-app                 | 8501 | 0.5  | 1.5G |
| nginx            | nginx:1.27-alpine            | 80   | 0.2  | 256M |
| **TOTAL**        |                              |      | **5.7** | **13.7G** |

## Schéma PostgreSQL (résumé)

5 schémas + 30+ tables :

- **bronze** (8 tables) : données brutes, immutable, JSONB
- **silver** (5 tables) : nettoyées, dédup, géo
- **gold** (8 tables) : features ML, prédictions, bottlenecks
- **rgpd** (4 tables) : consent, audit, DSR, purge log
- **governance** (2 tables) : data dictionary, lineage

Voir [deploy/init-db.sql](../deploy/init-db.sql) pour le détail.

## Sécurité (10 règles)

1. **Zéro credential en dur** — `os.getenv()` partout
2. **SQL paramétré partout** — pas de f-string SQL
3. **MLflow avec auth** — pas de `--disable-security-middleware`
4. **API key obligatoire** sur FastAPI (sauf `/health` et `/api/v1/rgpd/*`)
5. **Réseau interne** — ports Docker sur 127.0.0.1 sauf Nginx
6. **SSH key only** sur VPS
7. **Pas de secrets dans git** — `.env` dans .gitignore, gitleaks en CI
8. **Containers non-root** — USER appuser dans Dockerfile
9. **RGPD** — hash IP/UA, audit log, DSR
10. **Fernet key Airflow** générée, pas hardcodée

## Patterns utilisés

| Pattern | Où | Bénéfice |
|---------|-----|----------|
| Template Method | DataCollector | Héritage uniforme, retry/validate/save en commun |
| Repository | Transforms | SQL psycopg2 pur, réutilisable |
| Singleton | Config, Engine | 1 seule instance par process |
| Context Manager | session_scope, raw_connection | Transactions safe |
| Medallion (Bronze/Silver/Gold) | Pipeline data | Séparation raw / cleaned / features |
| Strategy | Renderers (WeasyPrint ↔ reportlab) | Fallback gracieux |
| Pipeline | DAGs Airflow | Orchestration déclarative |
| RBAC | Airflow + app_users | Personas ↔ accès DB |
| Hash anonymisation | RGPD service | Pas de réversibilité triviale |

## Limites & dette technique

Sprint 5 a livré un **MVP production-ready**. Reste à faire :

1. **Real data binding** dans les widgets Streamlit (actuellement mock)
2. **Component React deck.gl** pour simulateur d'aménagement
3. **GNN training** (training/stgcn/) — pour l'instant seulement XGBoost
4. **Tests E2E Playwright** — pour l'instant smoke + intégration
5. **Métriques Prometheus** + Grafana
6. **Kubernetes manifests** dans un répertoire dédié
7. **Backup/restore automatisé** (PostgreSQL + MinIO)
8. **CD pipeline** (déploiement auto sur VPS)
