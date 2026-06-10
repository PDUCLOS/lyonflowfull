# =============================================================================
# LyonFlowFull — README principal
# =============================================================================
# Plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal
# sur la Métropole de Lyon.
#
# Auteur: Patrice DUCLOS — Senior Data Analyst, Jedha RNCP 38777
# Repo: PDUCLOS/lyonflowfull
# Version: 0.6.1 (Sprint VPS-5 livré — voir SPRINT_VPS-5_REPORT.md)
#
# Branches :
#   - main         : Phase 1 production-ready local + fixes pipeline
#   - vps          : ACTIVE — Phase 2 déploiement VPS production (Sprints VPS 1-5)
#   - kubernetes   : DORMANTE — Phase 2 alternative K8s, futur AWS/GCP, NON mergée
#   - cloud-demo   : DORMANTE — Phase 3 Scaleway Kapsule, démo Jedha, NON mergée
#
# Voir docs/GIT_STRUCTURE.md pour le workflow branches/merges.
# Voir docs/REPO_STRUCTURE.md pour l'arbre annoté du repo.
# Voir SPRINT_VPS-5_REPORT.md pour le détail du dernier sprint.
# =============================================================================

# Table des matières
# ------------------
# 1. Vue d'ensemble
# 2. Architecture
# 3. Stack technique
# 4. Installation
# 5. Configuration
# 6. Utilisation
# 7. Développement
# 8. Tests
# 9. Déploiement
# 10. RGPD
# 11. Roadmap
# 12. Contribution

---

## 1. Vue d'ensemble

LyonFlowFull est une plateforme MLOps de prédiction et d'analyse du trafic
multimodal sur la Métropole de Lyon. Elle fusionne trois projets open source
en une solution unifiée :

- `caroheymes/Architect-IA-final-project` — modèle ST-GRU-GNN (spatial)
- `PDUCLOS/LyonFlow` — routing multimodal, ingestion ABC
- `PDUCLOS/lyontraffic` — production Medallion, XGBoost live

### Les 3 personas (interface unifiée)

| Persona    | Cible            | Pages | Auth |
|------------|------------------|-------|------|
| 🌱 Usager  | Lyonnais (grand public) | 4 pages (Mon Trajet, Alertes, Favoris, Files) | Non |
| 🎛 Pro TCL | Opérateurs réseau (Keolis) | 5 pages (PCC Live, Heatmap OTP, Corrélation, Simulateur, Export) | Oui (env) |
| 🏛 Élu     | Décideurs Grand Lyon | 5 pages (Synthèse, Bottlenecks, Avant/Après, Simulateur, Rapport PDF) | Oui (env) |

### Les 4 piliers ML

1. **Trafic routier** — tandem ST-GRU-GNN (spatial) + XGBoost (réactif)
2. **Bus TCL** — analyse SIRI Lite + diagnostic infrastructure
3. **Vélov** — prédiction disponibilité H+30min et H+1h
4. **Recommandation trajet** — scoring composite (50% temps + 30% coût + 20% CO₂)

### Le différenciateur clé

La **matrice de corrélation bus × trafic** croise retards bus et congestion
routière par segment. Aucun concurrent open source (TomTom, HERE, Waze)
ne fait ce croisement. C'est ce qui permet d'identifier :

- 🟢 OK — RAS
- 🔵 Voie bus dédiée fonctionne (à étendre)
- 🟡 Problème exploitation (fréquence, charge)
- 🔴 Problème infrastructure → action prioritaire (ROI 18 mois)

---

## 2. Architecture

Architecture Medallion (Bronze → Silver → Gold) sur PostgreSQL + PostGIS :

```
┌─────────── 8 sources open data ───────────┐
│ Grand Lyon WFS, Vélov GBFS, Open-Meteo,  │
│ SIRI Lite, Chantiers, Calendrier, ...    │
└────────────────┬───────────────────────────┘
                 │  Airflow DAGs 5min
                 ▼
        ┌────────────────┐
        │  BRONZE layer  │  Raw JSONB, immutable
        └────────┬───────┘
                 │  Transforms psycopg2
                 ▼
        ┌────────────────┐
        │  SILVER layer  │  Dédup, géo, normalisé
        └────────┬───────┘
                 │  Feature engineering
                 ▼
        ┌────────────────┐
        │   GOLD layer   │  Features ML-ready
        └────────┬───────┘
                 │
        ┌────────┴────────┐
        │  Models (ML)    │
        │  XGBoost + GNN  │
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        │  FastAPI +      │
        │  Streamlit      │
        └─────────────────┘
```

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour le détail complet.

---

## 3. Stack technique

| Couche | Technologie |
|--------|-------------|
| Orchestration | Apache Airflow 2.9 (CeleryExecutor) |
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| Storage objet | MinIO (S3-compatible) |
| Cache | Redis 7 |
| ML Tracking | MLflow 2.12 |
| ML Trafic (spatial) | ST-GRU-GNN (PyTorch Geometric) |
| ML Trafic (réactif) | XGBoost multi-horizon |
| ML Vélov | XGBoost (label encoding, 2 horizons) |
| ML Bus | XGBoost delay (analyse) |
| API | FastAPI + Uvicorn |
| Dashboard | Streamlit multi-pages |
| Monitoring | Evidently AI |
| PDF | WeasyPrint (HTML→PDF) |
| CI/CD | GitHub Actions |
| Infra | Docker Compose |
| Reverse proxy | Nginx 1.27 |

---

## 4. Installation

### Pré-requis

- Docker 24+ et Docker Compose v2+
- 6 CPU, 12 GB RAM, 100 GB SSD (minimum)
- Python 3.12+ (pour dev local sans Docker)

### Démarrage rapide (Docker)

```bash
# 1. Cloner
git clone https://github.com/PDUCLOS/lyonflowfull.git
cd lyonflowfull

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
# Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL + PostGIS local
createdb lyonflow
psql lyonflow < deploy/init-db.sql

# Variables d'environnement
cp .env.example .env
export $(cat .env | xargs)

# Lancer Streamlit
streamlit run dashboard/Accueil.py
```

---

## 5. Configuration

Variables d'environnement (voir `.env.example`) :

| Variable | Obligatoire | Usage |
|----------|-------------|-------|
| `POSTGRES_USER` | oui | DB user |
| `POSTGRES_PASSWORD` | oui | DB password |
| `POSTGRES_HOST` | oui | DB host |
| `POSTGRES_DB` | oui | DB name |
| `MINIO_ROOT_USER` | oui | MinIO admin user |
| `MINIO_ROOT_PASSWORD` | oui | MinIO admin password |
| `MLFLOW_TRACKING_URI` | oui | MLflow server URL |
| `LYONFLOW_API_KEY` | prod | API auth header |
| `AIRFLOW_ADMIN_PASSWORD` | prod | Airflow webserver auth |
| `AIRFLOW_FERNET_KEY` | prod | Airflow secret key |
| `PERSONA_PRO_TCL_PASSWORD` | non | Auth Pro TCL (legacy env-var) |
| `PERSONA_ELU_PASSWORD` | non | Auth Élu (legacy env-var) |
| `SEQ_LEN` | non (120) | Longueur séquence GNN |
| `HORIZONS` | non (6,12,36) | Horizons prédiction GNN |
| `HIDDEN_CHANNELS` | non (128) | Dimension GRU/GCN |
| `LYON_LATITUDE` | non (45.76) | Centre carte par défaut |
| `LYON_LONGITUDE` | non (4.84) | Centre carte par défaut |

---

## 6. Utilisation

### Pour l'usager (grand public)

- Aller sur http://localhost
- Pas d'auth requise
- Tester "Mon trajet" (ex: Villeurbanne → Part-Dieu)
- Consulter "Alertes" et "Favoris"

### Pour Pro TCL (opérateur)

- Sélectionner persona "Pro TCL" sur l'accueil
- Entrer le mot de passe (env `PERSONA_PRO_TCL_PASSWORD`)
- Dashboard PCC avec 4 quadrants (carte live, alertes, heatmap, bottlenecks)
- Simulateur de fréquences
- Export SAEIV/Hastus

### Pour l'Élu (décideur)

- Sélectionner persona "Élu"
- Entrer le mot de passe (env `PERSONA_ELU_PASSWORD`)
- Synthèse exécutive (5 KPIs + 5 décisions)
- Bottlenecks classés par ROI
- Génération PDF rapport CM

### API REST

```bash
# Health (public)
curl http://localhost/api/health

# Prédiction trafic
curl -X POST http://localhost/api/api/v1/predict/traffic \
  -H "X-API-Key: <LYONFLOW_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"node_idx": 42, "horizon_minutes": 30}'

# Recommandation
curl -X POST http://localhost/api/api/v1/recommend \
  -H "X-API-Key: <LYONFLOW_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"origin": "Villeurbanne", "destination": "Part-Dieu"}'
```

Voir [docs/API.md](docs/API.md) (à venir) pour la référence complète.

---

## 7. Développement

### Structure du projet

```
lyonflowfull/
├── config/                 # Configs YAML (personas, etc.)
├── dags/                   # Airflow DAGs
│   ├── bronze/
│   ├── transforms/
│   ├── ml/
│   ├── maintenance/
│   └── utils/
├── src/                    # Code source
│   ├── config.py           # Pydantic settings
│   ├── db/                 # PostgreSQL connection
│   ├── ingestion/          # 8 collecteurs (DataCollector ABC)
│   ├── transformation/     # Bronze→Silver→Gold
│   ├── models/             # XGBoost, GNN
│   ├── api/                # FastAPI
│   ├── rgpd/               # Consentement, audit
│   ├── governance/         # Data dictionary, lineage
│   ├── reporting/          # PDF generation
│   └── data/               # Mock data
├── training/               # GNN training (Sprint 5+)
├── dashboard/              # Streamlit multi-pages
│   ├── components/
│   │   └── widgets/        # 45 widgets par persona
│   └── pages/              # 15 pages
├── tests/                  # pytest
├── docs/                   # Documentation
├── deploy/                 # init-db.sql
├── nginx/                  # nginx.conf
├── .github/workflows/      # CI/CD
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Conventions de code

- **Anglais pour le code** (variables, fonctions, classes)
- **Français pour les commentaires et docstrings** métier
- **SQL paramétré partout** (`%s` psycopg2 ou `:param` SQLAlchemy)
- **Zéro credential en dur** — toujours via `os.getenv()`
- **Pas de f-string SQL** — toujours `cur.execute(query, params)`
- **Tests pytest** pour chaque module
- **Type hints** partout (mypy non bloquant)

### Ajouter un nouveau collecteur

```python
# src/ingestion/mon_api.py
from src.ingestion.base import DataCollector, FetchResult, CollectorError

class MonAPICollector(DataCollector):
    def __init__(self):
        super().__init__(
            source="mon_api",
            bronze_table="ma_table_bronze",
        )

    def fetch_raw(self) -> FetchResult:
        try:
            r = self._http_get("https://api.example.com/data")
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur: {e}") from e

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=self._count_records(data),
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
```

Puis ajouter dans `src/ingestion/collectors.py::ALL_COLLECTORS` et créer le DAG.

---

## 8. Tests

```bash
# Tous les tests
pytest tests/ -v

# Tests persona (UI)
pytest tests/persona/ -v

# Tests d'intégration (infra)
pytest tests/integration/ -v

# Smoke tests (E2E — nécessite stack démarrée)
pytest tests/smoke/ -v

# Avec couverture
pytest tests/ --cov=src --cov=dags --cov-report=html
open htmlcov/index.html
```

Tests actuels : 28 (persona UI) + 16 (intégration) + 3 (smoke) = **47 tests**.

---

## 9. Déploiement

**Cible production unique : VPS** (`51.83.159.224`, Ubuntu 6 CPU / 12 GB RAM).
Branche `vps` = source de vérité du déploiement actif.

### Déploiement local (Docker Compose)

```bash
docker compose up -d --build
```

### Déploiement production VPS (branche `vps`)

Stack complète livrée via Sprints VPS 1-4 :
- **VPS-1** TLS Let's Encrypt + healthcheck + hardening SSH/firewall
- **VPS-2** systemd unit + backup timer + rollback automatique
- **VPS-3** monitoring Prometheus + Alertmanager + Grafana + exporters
- **VPS-4** métriques FastAPI custom (predictions, latency, personas)

```bash
# Pré-flight (vérifie .deploy.env chmod 600 + vars critiques)
make check-deploy-env

# Déploiement initial
make deploy-vps              # rsync + restart systemd
make certbot-init            # cert TLS Let's Encrypt
make monitoring-up           # stack Prometheus/Grafana

# Opérations courantes
make healthcheck-vps         # ping /api/health + TLS check
make rollback-vps            # rollback dernière release
make backup                  # backup DB manuel (timer auto 03:00)
make tls-status              # statut cert Let's Encrypt
make monitoring-logs         # logs stack monitoring
```

Docs :
- [docs/VPS_HARDENING.md](docs/VPS_HARDENING.md) — durcissement (SSH, firewall, fail2ban, users)
- [docs/MONITORING.md](docs/MONITORING.md) — Prometheus + Grafana + alertes
- [docs/CONTROLE_VPS_VS_CLOUD_DEMO.md](docs/CONTROLE_VPS_VS_CLOUD_DEMO.md) — isolation vs autres branches

### Branches dormantes (futur AWS/GCP — ne pas merger)

Le projet n'utilise QUE le VPS. Les branches suivantes sont préparées
pour un éventuel déploiement cloud public, mais **ne doivent pas être
mergées dans `vps` ni `main`** :

| Branche | État | Cible future |
|---------|------|--------------|
| `kubernetes` | dormante | EKS / GKE |
| `cloud-demo` | dormante | POC Scaleway / AWS ponctuel |

---

## 10. RGPD

Voir [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md) pour le détail.

Points clés :
- ✅ Aucune donnée personnelle nominative collectée (que open data + hash)
- ✅ Consentement utilisateur (rgpd.user_consents)
- ✅ Audit log de toutes les actions (rgpd.audit_log)
- ✅ Data Subject Requests (accès, suppression, portabilité, rectification)
- ✅ IP et user_agent hashés en SHA256
- ✅ Endpoint API RGPD public : `POST /api/v1/rgpd/request`
- ✅ Page conformité : http://localhost/RGPD_Conformite

---

## 11. Roadmap

### Sprint 1-4 (livré) ✅
- Foundation personas + auth
- 13 pages × 3 personas
- 45 widgets Streamlit
- Mock data Lyon réaliste
- Génération PDF
- 28 tests verts

### Sprint 5 (livré) ✅
- Infrastructure Docker Compose complète
- PostgreSQL + PostGIS + init-db.sql
- 8 collecteurs Bronze (DataCollector ABC)
- Transforms Bronze→Silver→Gold psycopg2
- DAGs Airflow (collect, transform, retrain, maintenance)
- FastAPI REST endpoints
- XGBoost models (trafic + vélov)
- RGPD (consent, audit, DSR)
- Data governance (data dictionary, lineage)
- File manager
- CI/CD GitHub Actions
- 47 tests

### Sprint 6+ (à venir)
- Real data binding complet (remplacer mock par requêtes DB)
- Component React deck.gl pour simulateur d'aménagement
- Entraînement GNN réel (training/stgcn/)
- HPO Optuna intégré
- Tests E2E Playwright
- Métriques Prometheus + Grafana
- Alertes PagerDuty
- Kubernetes manifests (répertoire dédié)

---

## 12. Contribution

Pour contribuer :
1. Fork le repo
2. Créer une branche feature (`git checkout -b feature/ma-feature`)
3. Commiter (`git commit -m "feat: ma feature"`)
4. Pousser (`git push origin feature/ma-feature`)
5. Ouvrir une Pull Request

Standards :
- Tests pytest pour chaque nouvelle feature
- Ruff lint (CI bloque si KO)
- Type hints
- Docstrings pour les fonctions publiques
- Pas de credential en dur
- Pas de f-string SQL

---

## Licence

MIT — voir [LICENSE](LICENSE).

## Contact

Patrice DUCLOS — patrice.duclos@example.fr

*LyonFlowFull v0.1.0 · 2026-06-06*
