# CLAUDE.md — LyonFlowFull

## Projet

LyonFlowFull est une plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois repos sources (caroheymes/Architect-IA-final-project, PDUCLOS/LyonFlow, PDUCLOS/lyontraffic) en un projet unifié.

**Auteur**: Patrice DUCLOS — Senior Data Analyst, Jedha RNCP 38777 (Architecte en IA)
**Repo**: PDUCLOS/lyonflowfull

**Version actuelle** : v0.6.1 (Sprints 1-7 + VPS 1-5)
**Statut** : production VPS (branche `vps`, ACTIVE) — voir [SPRINT_VPS-5_REPORT.md](SPRINT_VPS-5_REPORT.md)
- 18 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · **9 DAGs Airflow** (8 actifs + 1 legacy paused)
- 9 endpoints API · 3 modèles ML (2 XGBoost + SpatioTemporalGCN) · RGPD complet
- 142 fichiers Python · ~18 600 lignes · 104+ tests
- Couche data complète (db_query + data_loader) — `gold.trafic_predictions` repeuplée hourly
- Sprint VPS-5 : connexion pipeline trafic (DAG manquant) + 166 lignes TCL sur Pro_4_Simulateur + sort/explore KPIs par ligne

**Phases (état 2026-06-10)** :
- ✅ Phase 1 — Production-ready local (branche `main`, Sprints 1-7)
- ✅ **Phase 2 — Déploiement VPS production (branche `vps`, ACTIVE)** — Sprints VPS 1-5 : TLS Let's Encrypt, systemd, monitoring Prometheus + Grafana + Alertmanager, backup automatique, métriques FastAPI custom, **connexion pipeline trafic**
- ⏸ Phase 3 (futur, AWS/GCP) — Kubernetes (branche `kubernetes`, dormante)
- ⏸ Phase 4 (futur, AWS/GCP) — Cloud démo Jedha (branche `cloud-demo`, dormante)

**Cible production** : **VPS uniquement** (51.83.159.224). Les branches `kubernetes` et `cloud-demo` sont préparées pour un futur déploiement AWS/GCP mais NE SONT PAS MERGEES dans `vps` ni `main`.

Voir [AGENTS.md](AGENTS.md) pour les conventions et la mémoire projet.

---

## Règles projet

- **Pas de changement de repo/commit/push sans accord explicite de l'utilisateur**
- **Déploiement : VPS unique (51.83.159.224)** — branche `vps` = cible production
- **Pas de merge `kubernetes` ni `cloud-demo` dans `vps` ou `main`** (dormantes, futur AWS/GCP)
- **🔴 BACKUP OFFSITE OBLIGATOIRE** — JAMAIS de backup persistant sur le VPS (full à 100%, 583M libre sur 96G). Toujours offsite via `scripts/backup-offsite.sh` (Google Drive via rclone OU serveur SSH). Stream pur, rien d'écrit sur le disque VPS.
- Langue: français pour pipeline/docs, anglais pour code modèle
- SQL paramétré partout, zéro f-string dans les requêtes

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Orchestration | Apache Airflow 2.9 |
| Base de données | PostgreSQL 16 + PostGIS |
| ML Tracking / Registry | MLflow 2.12 |
| ML Trafic (spatial) | ST-GRU-GNN (PyTorch Geometric) |
| ML Trafic (réactif) | XGBoost multi-horizon |
| ML Vélov | XGBoost (label encoding, **H+30min uniquement** — Sprint 12+) |
| ML Bus | XGBoost delay (après phase analyse) |
| API | FastAPI |
| Dashboard | Streamlit multi-pages |
| Monitoring | Evidently AI |
| Transformation | psycopg2 pur (pas de Polars dans Airflow) |
| CI/CD | GitHub Actions |
| Infra | Docker Compose |
| Reverse proxy | Nginx |

---

## 4 Piliers ML

### 1. Trafic routier: GNN + XGBoost en tandem

| Modèle | Rôle | Retrain | Force |
|--------|------|---------|-------|
| ST-GRU-GNN | Spatial — propagation congestion entre segments | Daily 03h | Dépendances spatiales, horizons longs |
| XGBoost speed | Réactif — changements récents | Hourly :25 | Météo/vacances/lags, horizons courts |

Architecture GNN (SpatioTemporalGCN):
- GRU (5 canaux input, hidden_channels) → dernier hidden state
- 2× GCNConv + LeakyReLU + skip connections
- Linear → prédictions multi-horizon
- Graphe: ~1520 nœuds, ~9540 arêtes, H3 res.13

Ensemble: les deux prédictions conservées. Recommandation trajet utilise le meilleur par segment (MAE comparé dans gold.predictions_vs_actuals).

### 2. Bus: Analyse → Prédiction

**Phase 1 — Analyse** (collecte SIRI Lite):
- Retard agrégé par tronçon de ligne, tranche horaire, jour, météo, vacances
- Détection accumulation retard sur le parcours

**Phase 2 — Croisement infrastructure**:
- Bus retard + trafic congestionné = problème infrastructure
- Bus retard + trafic fluide = problème opérationnel
- Trafic congestionné + bus OK = voie dédiée fonctionnelle

**Phase 3 — Prédiction** (quand données suffisantes):
- XGBoost delay: prédire delay_seconds par ligne/segment/heure
- Features: heure, jour, vacances, météo, vitesse trafic adjacente, historique retard

### 3. Vélov: H+30min uniquement, économe (Sprint 12+)

- **H+30min uniquement** (Patrice 2026-06-13 : "tout en H+30min pour Vélov")
  - Avant Sprint 12+ : 2 horizons (H+30min, H+1h)
  - Pourquoi : focus réactivité court terme, économie RAM/CPU sur le VPS
- Label encoding stations (pas 458 one-hot → économie RAM de 9GB à ~500MB)
- Features: station_id encodé, temporel, météo (pluie), is_vacances, is_ferie, lags, rolling means
- Retrain hourly :50
- Modèle H+1h Vélov **supprimé** du registry MLflow (DAG `retrain_xgboost_velov` entraîne uniquement `xgb_velov_h30`)

### 4. Recommandation trajet multimodale

Pour chaque mode (voiture, bus/tram, vélov, marche, métro):
- Voiture: prédiction vitesse GNN/XGBoost → temps estimé
- Bus/Tram: prédiction retard → temps ajusté
- Vélov: prédiction dispo stations → faisable + temps
- Marche: distance (toujours disponible)
- Métro: GTFS (fiable, peu de retard)

Scoring composite: 50% temps + 30% coût + 20% éco (CO2)

---

## Pipeline de Données — Architecture Medallion

### Bronze (Ingestion — 8 sources)

| Source | Fréquence | Table |
|--------|-----------|-------|
| Grand Lyon boucles (pvotrafic OGC) | */5 min | bronze.trafic_boucles |
| TCL SIRI Lite | */5 min | bronze.tcl_vehicles |
| Vélo'v GBFS | */5 min | bronze.velov |
| Open-Meteo weather | */1h | bronze.meteo |
| Open-Meteo air quality | */1h | bronze.air_quality |
| Grand Lyon chantiers | 1x/jour | bronze.chantiers |
| Vitesse limite ref | 1x/semaine | bronze.vitesse_limite_ref |
| Pistes cyclables + GTFS | 1x/semaine | bronze.infra_ref |

Tables référentielles (peuplées mensuellement):
- bronze.calendrier_scolaire (Zone A, data.education.gouv.fr)
- bronze.jours_feries (calendrier.api.gouv.fr)

Chaque table Bronze: `fetched_at TIMESTAMPTZ` + `raw_data JSONB`. Immutable. Rétention par purge (7j→45j selon volume).

### Silver (Nettoyage — 5 tables)

| Table | Source | Transformation |
|-------|--------|---------------|
| silver.trafic_boucles_clean | bronze.trafic_boucles | Dédup DISTINCT ON, capteurs sains, géo 4326+2154 |
| silver.tcl_vehicles_clean | bronze.tcl_vehicles | Parse SIRI, delay_seconds, line_ref, dédup |
| silver.velov_clean | bronze.velov | Dédup, stations actives |
| silver.meteo_hourly | bronze.meteo | Dédup par measurement_time |
| silver.chantiers_actifs | bronze.chantiers | Filtre date_debut ≤ now ≤ date_fin |

### Gold (Features + Analytique — 3 domaines)

**Domaine Trafic:**

| Table | Rôle |
|-------|------|
| gold.traffic_features_live | Features ML: `channel_id, fetched_at, computed_at, speed_kmh, vitesse_limite_kmh, lag_1/2/3, delta_1, rolling_mean_3, sin_hour, cos_hour, sin_dow, cos_dow, temperature_2m, precipitation, is_vacances, is_ferie, lat, lon, x_2154, y_2154` |
| gold.dim_spatial_grid_mapping | Capteurs → nœuds GNN (H3 res.13, cell_to_local_ij). ~1518 nœuds, PK = `properties_twgid` |
| gold.dim_gnn_adjacency | Arêtes graphe (K=2 grid_disk, bidirectionnel + self-loops) |
| gold.fact_traffic_series | Séries temporelles normalisées (5 canaux: speed, hour_sin/cos, day_sin/cos) |
| **gold.trafic_predictions** | **Prédictions pré-calculées. Schéma v0.3.1 : `axis_key, horizon_h (0/1/3/6), calculated_at, speed_pred, etat_pred, color, vitesse_limite_kmh, label, model_version, lat, lon`. Alimentée hourly par `dag_live_speed_retrain`** (Sprint VPS-5, baseline = dernière vitesse observée) |
| gold.predictions_vs_actuals | Backtesting pour comparaison modèles |

> **⚠️ Dette schéma Sprint VPS-5** : `src/models/xgboost_speed.py` référence encore
> `speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time` qui
> n'existent plus dans `gold.traffic_features_live` (renommés en
> `lag_1/delta_1/sin_hour/temperature_2m/precipitation/computed_at`).
> Refacto `xgboost_speed.py` + `xgboost_velov.py` = Sprint 9+.

**Domaine Bus:**

| Table | Rôle |
|-------|------|
| gold.bus_delay_segments | Retard agrégé par tronçon/ligne/heure/jour/météo/vacances |
| gold.infrastructure_bottlenecks | Croisement retard bus × congestion trafic → diagnostic infra |

**Domaine Vélov:**

| Table | Rôle |
|-------|------|
| gold.velov_features | station_id label-encoded, temporel, météo, vacances, lags, rolling |
| gold.velov_predictions | H+30min, H+1h |

---

## Scheduling Airflow — Sans conflit

```
:00  Collecte bronze (boucles + AQ horaire)
:02  Collecte bronze (SIRI Lite + Vélov)
:05  Transform bronze → silver (4 parallèles)
:15  Transform silver → gold (3 domaines parallèles)
:20  dag_live_speed_retrain (Sprint VPS-5) — train 4 XGBoost + INSERT gold.trafic_predictions
:25  Retrain XGBoost trafic (legacy, 4 horizons, ~10 min)
:50  Retrain Vélov (**H+30min uniquement** Sprint 12+, ~3 min)
03h  Retrain GNN daily (lourd, GPU si dispo)
04h  Data quality daily (6 checks) + bottleneck analysis
06h  Drift monitoring Evidently
1er du mois: refresh calendrier scolaire + jours fériés
```

---

## Sécurité — 10 règles

1. **Zéro credential dans le code**. Tout via os.getenv() avec validation au boot. Pas de fallback hardcodé pour mots de passe.
2. **SQL paramétré partout**. psycopg2 %s ou SQLAlchemy :param. Zéro f-string SQL.
3. **MLflow avec auth**. Retirer --disable-security-middleware. Basic auth ou proxy Nginx.
4. **API key obligatoire** sur FastAPI. Header X-API-Key requis. Rate limiting.
5. **Réseau interne**. Ports Docker sur 127.0.0.1 sauf Nginx. Nginx reverse proxy unique.
6. **SSH key only**. Désactiver password auth. Clé dédiée par service.
7. **Pas de secrets dans git**. .env dans .gitignore. Template .env.example sans valeurs. Gitleaks en CI.
8. **Containers non-root**. USER appuser dans Dockerfiles. Filesystem read-only si possible.
9. **RGPD**. Pas de PII dans logs. Purge auto Bronze. Page conformité dans dashboard.
10. **Fernet key Airflow** générée, pas hardcodée.

---

## Dashboard — Carte bottlenecks

Visualisation sur carte Folium:
- **Rouge**: bus ET trafic souffrent (bottleneck infrastructure)
- **Orange**: trafic congestionné seul
- **Bleu**: pistes cyclables contournant zones rouges
- **Violet**: stations métro accessibles à pied (~500m) depuis zones rouges
- **Vert**: alternatives fonctionnelles identifiées

### Pro_4_Simulateur — Sélecteur de ligne TCL (Sprint VPS-5)

Charge **toutes les lignes TCL distinctes** depuis `gold.tcl_vehicle_realtime.line_ref`
(166 lignes historiques : 9 trams T1..T7/TB11/TB12 + 157 bus). Auto-catégorisation :
`T*` → 🚊 tram, `M*` → 🚇 metro, reste → 🚌 bus. Mock fallback si DB down.

### Widget KPIs par ligne — Sort + Explore (Sprint VPS-5)

Le widget `dashboard/components/widgets/pro_tcl/line_kpis.py` expose :
- **Sélecteur "Trier par"** : 10 options (OTP↑↓, Retard↑↓, Charge↑↓, Fréq↑↓, Line ID A-Z/Z-A)
- **Slider "Top N"** : 5 → 50 lignes affichées
- **Checkbox "Détails par ligne"** : déplie chaque ligne en cards 4 KPIs
- **Tableau Streamlit** avec barres de progression sur OTP et Charge
- Tri natif Streamlit en plus (click sur les headers)

---

## Provenance des composants

| Composant | Repo source | Raison |
|-----------|-------------|--------|
| ST-GRU-GNN modèle + dataset | FinalProjet | Architecture validée, matrice adjacence H3 |
| Pipeline Medallion psycopg2 | trafficlyon | Production-proven, pas de dépendance Polars dans Airflow |
| Structure DAGs | trafficlyon | Le plus mature (13 DAGs testés) |
| Dashboard 9+ pages | trafficlyon | Le plus complet |
| src/ingestion/ collecteurs | LyonFlow | Architecture la plus propre (ABC, tenacity retry) |
| src/routing/ recommandation | LyonFlow | Multimodal scoring composite |
| FastAPI endpoints | LyonFlow | Structure API avancée |
| Evidently monitoring | trafficlyon | En production, drift reports |

### Supprimé

| Composant | Raison |
|-----------|--------|
| Kafka | Jamais utilisé réellement |
| MinIO | PostgreSQL suffit |
| 458 one-hot vélov | 9GB RAM, remplacé par label encoding |
| Orbit DLT challenger | Conflit schedule, complexité sans gain |
| AR(1) predictor fallback | Dead code |
| Ray cluster HPO | Optuna local suffit |
| TomTom API | Payant, redondant avec boucles |

---

## Déploiement

**Cible production : VPS unique** — `51.83.159.224` (Ubuntu, 6 CPU, 12 GB RAM, 100 GB SSD).
Branche `vps` = source de vérité du déploiement actif.

### Stack VPS (branche `vps`)

| Composant | Détail |
|-----------|--------|
| Reverse proxy | Nginx + TLS Let's Encrypt (Sprint VPS-1) |
| Process supervisor | systemd unit `lyonflow.service` (Sprint VPS-2) |
| Backup DB | systemd timer quotidien 03:00 → `scripts/backup.sh` (Sprint VPS-2) |
| Rollback | `make rollback-vps` (Sprint VPS-2) |
| Monitoring | Prometheus + Alertmanager + Grafana via `docker-compose.monitoring.yml` (Sprint VPS-3) |
| Exporters | node, postgres, nginx, redis (Sprint VPS-3) |
| Métriques custom | `src/api/metrics.py` — prédictions, latence, personas, DAGs, MLflow, DB (Sprint VPS-4) |
| **Pipeline trafic** | **`dags/ml/dag_live_speed_retrain.py` (Sprint VPS-5)** — train 4 XGBoost + INSERT hourly dans `gold.trafic_predictions` (baseline) |
| Stockage DB | `/opt/lyonflow/postgres_data` (volume Docker) |
| Réseau | Ports internes sur 127.0.0.1 uniquement, Nginx seul exposé 80/443 |
| Secrets | `.env` chmod 600, jamais en repo |

### ⚠️ Gotchas déploiement VPS (Sprint VPS-5)

- **`/opt/lyonflow/logs/`** doit être `chown 50000:0` récursivement après chaque
  `rsync` frais. Sinon le worker Celery crash en boucle sur
  `PermissionError: '/opt/airflow/logs/dag_id=*/run_id=*'` et l'UI Airflow devient
  incohérente (DAGs présents mais tasks stuck en queued). Fix durable TODO :
  entrypoint dans Dockerfile Airflow qui chown au boot.
- **DNS `lyonflowfull.fr` mort** (NXDOMAIN) + cert TLS Let's Encrypt expiré
  → accès par IP `https://51.83.159.224` (warning cert self-signed `CN=51.83.159.224`).
- **Mapping `dim_spatial_grid_mapping.properties_twgid` (entiers)** ≠
  **`traffic_features_live.channel_id` (format "LYO00xxx")** — JOIN impossible
  directement. Prédictions écrites avec `lat/lon=NULL` (Sprint 9+ pour réconcilier).

### Commandes déploiement VPS

```bash
make check-deploy-env       # vérifie .deploy.env (chmod 600 + vars critiques)
make deploy-vps             # rsync + restart systemd
make healthcheck-vps        # ping /api/health + TLS check
make rollback-vps           # rollback dernière release
make monitoring-up          # stack Prometheus/Grafana/Alertmanager
make tls-status             # statut cert Let's Encrypt
```

Docs détaillées :
- [docs/VPS_HARDENING.md](docs/VPS_HARDENING.md) — durcissement SSH/firewall/users
- [docs/MONITORING.md](docs/MONITORING.md) — Prometheus/Grafana/alertes
- [docs/CONTROLE_VPS_VS_CLOUD_DEMO.md](docs/CONTROLE_VPS_VS_CLOUD_DEMO.md) — isolation vs branches dormantes

### Branches dormantes (futur AWS/GCP, NE PAS MERGER)

- `kubernetes` — Phase K8s complète (Kustomize + monitoring + GPU GNN). Cible : EKS / GKE futur.
- `cloud-demo` — Phase démo Jedha (Scaleway Kapsule éphémère). Cible : POC cloud public ponctuel.

---

## Structure cible

```
lyonflowfull/
├── CLAUDE.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.ray          # si GPU GNN
├── init-db.sql
├── requirements.txt
├── pyproject.toml
├── dags/
│   ├── bronze/             # DAGs collecte
│   ├── transforms/         # DAGs silver/gold
│   ├── ml/                 # DAGs retrain
│   ├── maintenance/        # purge, quality, drift
│   └── utils/              # alerting, helpers
├── src/
│   ├── config.py
│   ├── ingestion/          # 8 collecteurs (ABC + tenacity)
│   ├── transformation/     # feature engineering
│   ├── models/             # GNN, XGBoost, delay predictor
│   ├── routing/            # recommandation multimodale
│   ├── monitoring/         # Evidently, drift
│   └── api/                # FastAPI endpoints
├── training/
│   └── stgcn/              # GNN model, dataset, train, HPO
├── scripts/                # transform, backup, utils
├── dashboard/
│   ├── Accueil.py
│   ├── pages/              # 10+ pages
│   └── components/         # data_loader, theme, sidebar
├── tests/
├── docs/
└── kubernetes/             # si K8s retenu
```

---

## Variables d'environnement

| Variable | Obligatoire | Usage |
|----------|------------|-------|
| POSTGRES_USER | oui | DB user |
| POSTGRES_PASSWORD | oui | DB password |
| POSTGRES_HOST | oui | DB host |
| POSTGRES_DB | oui | DB name |
| MLFLOW_TRACKING_URI | oui | MLflow server |
| LYONFLOW_API_KEY | oui | FastAPI auth |
| AIRFLOW_FERNET_KEY | oui | Chiffrement Airflow |
| SEQ_LEN | non (120) | Longueur séquence GNN |
| HORIZONS | non (6,12,36) | Horizons prédiction GNN |
| HIDDEN_CHANNELS | non (128) | Dimension GRU/GCN |
| WEIGHT_JAM | non (15) | Pénalité congestion (staircase loss) |
| WEIGHT_SLOW | non (5) | Pénalité ralenti |
| LYON_DEFAULT_SPEED | non (30.0) | Vitesse imputation fallback |

---

## Commandes

```bash
# Lint
ruff check . --output-format=github
ruff format --check .

# Type check (non-blocking)
mypy dags/ training/ src/ --ignore-missing-imports

# Tests
pytest tests/ -v --tb=short

# Stack complète
docker-compose up -d --build
```
