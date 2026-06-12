# CLAUDE.md — LyonFlowFull

> Mémoire projet — **dernière mise à jour : 2026-06-12, Sprint 8** (zéro mock + ingestion Bronze + focus H+1h).

## Projet

LyonFlowFull est une plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois repos sources (caroheymes/Architect-IA-final-project, PDUCLOS/LyonFlow, PDUCLOS/lyontraffic) en un projet unifié.

**Auteur** : Patrice DUCLOS — Senior Data Analyst, Jedha RNCP 38777 (Architecte en IA)
**Repo** : PDUCLOS/lyonflowfull
**Cible production** : **VPS unique** `51.83.159.224` (Ubuntu, 6 CPU, 12 Go RAM, **2× 100 Go SSD** : sda = OS + services, sdb = PostgreSQL + MinIO).

**Version actuelle** : **v0.6.3** (Sprints 1-7 + VPS 1-8) — branche `vps` ACTIVE
**Statut** : production VPS stable. Voir [SPRINT_VPS-8_REPORT.md](SPRINT_VPS-8_REPORT.md) pour le dernier sprint.

### État au 2026-06-12

- 18 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · **10 DAGs Airflow** (8 actifs + 1 cron backfill + 1 TomTom no-op)
- 9 endpoints API · 3 modèles ML (2 XGBoost H+1h + SpatioTemporalGCN) · RGPD complet
- 150 fichiers Python · ~19 500 lignes · **150 tests verts / 9 SKIP / 7 deselected (integration)** · ruff clean
- Couche data complète (db_query + data_loader) — `gold.trafic_predictions` repeuplée toutes les 30 min
- Sprint 8 (2026-06-12) — **3 dettes critiques résolues** :
  - **ZÉRO MOCK DANS LE PROJET** : suppression complète de `src/data/mock/` (déplacé dans `tests/fixtures/mock_data/`). Tous les widgets, data_loader, db_query, airflow_client fail loud via `DashboardDataError`. 18 fallbacks mock virés.
  - **Focus H+1h** (Sprint VPS-6) : features XGBoost réduites de 14 à 9 (1 modèle H+1h au lieu de 4), DAG `dag_live_speed_retrain` toutes les 30 min, scheduler backfill `*/5min` sur lat/lon.
  - **Ingestion Bronze stable** : `air_quality` (72 records) et `chantiers` (428 records) débloqués (dette schéma UNIQUE INDEX sur colonnes extracted). Healthcheck `scripts/healthcheck-vps.sh` 20/20 OK.
- Sprint 8+ : durcissement Prometheus/Grafana/Alertmanager (config YAML cassée depuis v2.54, restart-loop résolu). Backups offsite (Sprint VPS-2) toujours actifs.

### Phases

- ✅ Phase 1 — Production-ready local (branche `main`, Sprints 1-7)
- ✅ **Phase 2 — Déploiement VPS production (branche `vps`, ACTIVE)** — Sprints VPS 1-8
- ⏸ Phase 3 (futur, AWS/GCP) — Kubernetes (branche `kubernetes`, dormante)
- ⏸ Phase 4 (futur, AWS/GCP) — Cloud démo Jedha (branche `cloud-demo`, dormante)

Voir [AGENTS.md](AGENTS.md) pour les conventions et la mémoire projet.

---

## Règles projet

- **Pas de changement de repo/commit/push sans accord explicite de l'utilisateur**
- **Déploiement : VPS unique (51.83.159.224)** — branche `vps` = cible production
- **Pas de merge `kubernetes` ni `cloud-demo` dans `vps` ou `main`** (dormantes, futur AWS/GCP)
- **🔴 BACKUP OFFSITE OBLIGATOIRE** (Sprint VPS-2) — Ne JAMAIS laisser de backup persistant sur sdb. Stream pur vers Google Drive via rclone ou serveur SSH distant. Cf. `scripts/backup-offsite.sh`. Disque sda1 à 80% (19 Go libres sur 96 Go) — surveiller.
- Langue : français pour pipeline/docs, anglais pour code modèle
- **SQL paramétré partout**, zéro f-string dans les requêtes (`psycopg2 %s`)
- **🔴 ZÉRO MOCK DANS LE PROJET** (Sprint 8, 2026-06-12) — Variable d'env `LYONFLOW_DEMO_MODE=0` obligatoire en prod. Toute source de données indisponible (PostgreSQL, Airflow, MLflow) lève `DashboardDataError` et le widget affiche `st.error`. Mode démo **supprimé** (helper `_is_demo_mode()` retourne toujours `False` — déprécié, à retirer Sprint 9+). Plan détaillé : [docs/PLAN_NO_MOCK_VPS.md](docs/PLAN_NO_MOCK_VPS.md).
- **🔴 RÉFÉRENTIEL LIEUX EN DB** (Sprint VPS-6) — Tables `referentiel.lieux_lyon` (21 lieux emblématiques), `referentiel.lieux_transports` (56 liaisons), `referentiel.lieux_calendrier` (223 cadences weekday). Plus de mock codé en dur.
- **🔴 BACKFILL lat/lon obligatoire** (Sprint 8) — Le DAG `maintenance_backfill_dim_spatial_lat_lon` tourne toutes les 5 min et dérive les coords depuis `h3_id` (h3-py 4.5). Trigger SQL `trg_dim_spatial_has_lat_lon` refuse les INSERT avec lat/lon NULL pour les canaux `real_string`.
- **Fiabilité VPS** (Sprint 8+) — DAGs critiques ont `retries=0` (le cycle suivant rattrape). Prometheus + Alertmanager + Grafana UP. Healthcheck `scripts/healthcheck-vps.sh` 20 checks.

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Orchestration | Apache Airflow 2.9 (8 DAGs actifs + 1 cron backfill + 1 no-op TomTom) |
| Base de données | PostgreSQL 16 + PostGIS (3 schémas : bronze/silver/gold + referentiel) |
| ML Tracking / Registry | MLflow 2.12 |
| ML Trafic (spatial) | ST-GRU-GNN (PyTorch Geometric) — **daily 03h** |
| ML Trafic (réactif) | XGBoost **H+1h uniquement** (1 modèle, focus fiabilité VPS) — toutes les 30 min |
| ML Vélov | XGBoost (label encoding, 2 horizons H+30min + H+1h) — toutes les heures :50 |
| ML Bus | XGBoost delay (phase analyse — collecte SIRI Lite en prod) |
| API | FastAPI |
| Dashboard | Streamlit multi-pages (18 pages × 3 personas) |
| Monitoring | Prometheus + Alertmanager + Grafana (stack monitoring Sprint 8+) |
| Transformation | psycopg2 pur (pas de Polars dans Airflow) |
| CI/CD | GitHub Actions |
| Infra | Docker Compose (2 fichiers : `docker-compose.yml` + `docker-compose.monitoring.yml`) |
| Reverse proxy | Nginx 1.27 |

---

## 4 Piliers ML

### 1. Trafic routier : GNN + XGBoost en tandem

| Modèle | Rôle | Retrain | Force |
|--------|------|---------|-------|
| ST-GRU-GNN | Spatial — propagation congestion entre segments | Daily 03h | Dépendances spatiales, horizons longs |
| XGBoost speed H+1h | Réactif — changements récents | Toutes les 30 min | Météo/vacances/lags, focus fiabilité |

**Architecture GNN** (SpatioTemporalGCN) :
- GRU (5 canaux input, hidden_channels) → dernier hidden state
- 2× GCNConv + LeakyReLU + skip connections
- Linear → prédictions multi-horizon
- Graphe : ~1520 nœuds (H3 res 13), ~9540 arêtes K=2

**Ensemble** : les deux prédictions conservées. Recommandation trajet utilise le meilleur par segment (MAE comparé dans `gold.predictions_vs_actuals`).

### 2. Bus : Analyse → Prédiction

**Phase 1 — Analyse** (collecte SIRI Lite, Sprint 7+ en prod) :
- Retard agrégé par tronçon de ligne, tranche horaire, jour, météo, vacances
- Détection accumulation retard sur le parcours

**Phase 2 — Croisement infrastructure** :
- Bus retard + trafic congestionné = problème infrastructure
- Bus retard + trafic fluide = problème opérationnel
- Trafic congestionné + bus OK = voie dédiée fonctionnelle

**Phase 3 — Prédiction** (quand données suffisantes) :
- XGBoost delay : prédire `delay_seconds` par ligne/segment/heure
- Features : heure, jour, vacances, météo, vitesse trafic adjacente, historique retard

### 3. Vélov : 2 horizons, économe

- **H+30min et H+1h uniquement** (focus H+1h comme le trafic)
- Label encoding stations (pas 458 one-hot → économie RAM de 9GB à ~500MB)
- **Features Sprint 8+ (référentiel schema v0.3.1)** : `station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos, temperature_c, rain_mm, is_vacances, is_ferie`
- Retrain **hourly :50**

### 4. Recommandation trajet multimodale

Pour chaque mode (voiture, bus/tram, vélov, marche, métro) :
- **Voiture** : Dijkstra sur graphe routier H3 (Sprint 8 hotfix 2) — `compute_itinerary()` lit `gold.dim_spatial_grid_mapping` + `gold.dim_gnn_adjacency`
- **Bus/Tram** : prédiction retard SIRI → temps ajusté
- **Vélov** : smart routing (Sprint VPS-6) — `plan_velov_trip()` avec scoring composite (distance + vélos/docks dispo), alternatives si borne #1 VIDE/PLEINE, maillage voisines < 200m
- **Marche** : distance (toujours disponible)
- **Métro** : GTFS (fiable, peu de retard)

**Scoring composite** : 50% temps + 30% coût + 20% éco (CO2)

---

## Pipeline de Données — Architecture Medallion

### Bronze (Ingestion — 8 sources, Sprint 8+ toutes fonctionnelles)

| Source | Fréquence | Table | Statut |
|--------|-----------|-------|--------|
| Grand Lyon boucles (pvotrafic OGC) | */5 min | `bronze.trafic_boucles` | ✅ 12/h |
| TCL SIRI Lite | */5 min | `bronze.tcl_vehicles` | ✅ 11/h |
| Vélo'v GBFS | */5 min | `bronze.velov` | ✅ 11/h |
| Open-Meteo weather | */1h | `bronze.meteo` | ✅ 13/h |
| Open-Meteo air quality | */1h | `bronze.air_quality` | ✅ 72 records/test (Sprint 8 fix) |
| Grand Lyon chantiers | 1x/jour | `bronze.chantiers` | ✅ 428 records (Sprint 8 fix) |
| Vitesse limite ref | 1x/semaine | `bronze.vitesse_limite_ref` | ✅ |
| Pistes cyclables + GTFS | 1x/semaine | `bronze.infra_ref` | ✅ |
| TomTom Traffic Flow | */15 min | `bronze.tomtom_traffic` | ⏸ NO-OP (module incomplet, réactivation Sprint 12+) |

Tables référentielles (peuplées mensuellement) :
- `bronze.calendrier_scolaire` (Zone A, data.education.gouv.fr)
- `bronze.jours_feries` (calendrier.api.gouv.fr)

Chaque table Bronze : `fetched_at TIMESTAMPTZ` + `raw_data JSONB` + colonnes extracted (nullable). Immutable. Rétention par purge (7j→45j selon volume).

### Silver (Nettoyage — 5 tables)

| Table | Source | Transformation |
|-------|--------|---------------|
| `silver.trafic_boucles_clean` | bronze.trafic_boucles | Dédup DISTINCT ON, capteurs sains, géo 4326+2154 |
| `silver.tcl_vehicles_clean` | bronze.tcl_vehicles | Parse SIRI, delay_seconds, line_ref, dédup |
| `silver.velov_clean` | bronze.velov | Dédup, stations actives |
| `silver.meteo_hourly` | bronze.meteo | Dédup par measurement_time |
| `silver.chantiers_actifs` | bronze.chantiers | Filtre date_debut ≤ now ≤ date_fin |

### Gold (Features + Analytique — 3 domaines)

**Domaine Trafic** (schéma v0.3.1) :

| Table | Rôle |
|-------|------|
| `gold.traffic_features_live` | Features ML : `channel_id, computed_at, speed_kmh, vitesse_limite_kmh, lag_h1/h2/h3, delta_h1, rolling_mean_h1, sin_hour, cos_hour, sin_dow, cos_dow, temperature_2m, precipitation, is_vacances, is_ferie, lat, lon` |
| `gold.dim_spatial_grid_mapping` | Capteurs → nœuds GNN (H3 res.13, cell_to_local_ij). ~1520 nœuds, PK = `properties_twgid` (Sprint 8 hotfix 5 : backfill lat/lon via h3-py 4.5) |
| `gold.dim_gnn_adjacency` | Arêtes graphe (K=2 grid_disk, bidirectionnel + self-loops) |
| `gold.fact_traffic_series` | Séries temporelles normalisées (5 canaux) |
| **`gold.trafic_predictions`** | Prédictions pré-calculées. Schéma v0.3.1 : `axis_key, horizon_h (1), calculated_at, speed_pred, etat_pred, color, vitesse_limite_kmh, label, model_version, lat, lon`. Alimentée toutes les 30 min par `dag_live_speed_retrain` (focus H+1h depuis Sprint VPS-6) |
| `gold.predictions_vs_actuals` | Backtesting pour comparaison modèles |

> **Dette schéma Sprint 5 — RÉSOLUE Sprint 8+** : `src/models/xgboost_speed.py` référençait `speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time` qui n'existaient plus. Refacto Sprint 8+ : alignement complet sur schéma v0.3.1 avec convention focus H+1h (`lag_h1`, `rolling_mean_h1`, etc.).

**Domaine Bus** :

| Table | Rôle |
|-------|------|
| `gold.bus_delay_segments` | Retard agrégé par tronçon/ligne/heure/jour/météo/vacances |
| `gold.infrastructure_bottlenecks` | Croisement retard bus × congestion trafic → diagnostic infra |
| `gold.mv_line_kpis_live` | Vue matérialisée KPIs par ligne (155 lignes) — Sprint 7 |
| `gold.mv_otp_heatmap` | Heatmap OTP triplets (4416 lignes×date×hour) — Sprint 7 |

**Domaine Vélov** :

| Table | Rôle |
|-------|------|
| `gold.velov_features` | station_id label-encoded, temporel, météo, vacances, lags, rolling |
| `gold.velov_predictions` | H+30min, H+1h |

---

## Scheduling Airflow — Sans conflit

```
:00  Collecte bronze (boucles + AQ + chantiers)
:02  Collecte bronze (SIRI Lite + Vélov)
:05  Transform bronze → silver (5 parallèles)
:15  Transform silver → gold (3 domaines parallèles)
:20  dag_live_speed_retrain (Sprint VPS-5, focus H+1h) — train XGBoost H+1h + INSERT gold.trafic_predictions
*/30  Idem, toutes les 30 min (cf. v0.6.3 — focus H+1h)
*/5   backfill_dim_spatial_lat_lon (Sprint 8 cron, idempotent)
:25  Retrain XGBoost trafic (legacy, 4 horizons, ~10 min)
:50  Retrain Vélov (2 horizons : H+30min, H+1h, ~5 min)
03h  Retrain GNN daily (lourd, GPU si dispo)
04h  Data quality daily (6 checks) + bottleneck analysis
06h  Drift monitoring Evidently
1er du mois: refresh calendrier scolaire + jours fériés
```

---

## Sécurité — 10 règles

1. **Zéro credential dans le code**. Tout via `os.getenv()` avec validation au boot. Pas de fallback hardcodé.
2. **SQL paramétré partout**. `psycopg2 %s`. Zéro f-string SQL.
3. **MLflow avec auth** (Basic auth via Nginx).
4. **API key obligatoire** sur FastAPI. Header `X-API-Key`. Rate limiting.
5. **Réseau interne**. Ports Docker sur `127.0.0.1` sauf Nginx. Nginx reverse proxy unique.
6. **SSH key only**. Désactiver password auth. Clé `~/.ssh/lyonflow_deploy`.
7. **Pas de secrets dans git**. `.env` dans `.gitignore`. Gitleaks en CI.
8. **Containers non-root**. USER `appuser` dans Dockerfiles.
9. **RGPD**. Pas de PII dans logs. Purge auto Bronze. Page conformité dans dashboard.
10. **Fernet key Airflow** générée, pas hardcodée.

---

## Dashboard — Architecture 3 personas

**18 pages × 3 personas** (Usager, Pro TCL, Élu) + Accueil.

### Couleurs bottlenecks (carte Folium)

- **Rouge** : bus ET trafic souffrent (bottleneck infrastructure)
- **Orange** : trafic congestionné seul
- **Bleu** : pistes cyclables contournant zones rouges
- **Violet** : stations métro accessibles à pied (~500m) depuis zones rouges
- **Vert** : alternatives fonctionnelles identifiées

### Pro_4_Simulateur — Sélecteur de ligne TCL (Sprint VPS-5)

Charge **toutes les lignes TCL distinctes** depuis `gold.tcl_vehicle_realtime.line_ref` (155 lignes via `gold.mv_line_kpis_live` + 10 emblématiques via `src/data/tcl_lines.py`). Auto-catégorisation : `T*` → 🚊 tram, `M*` → 🚇 metro, reste → 🚌 bus. **Sprint 8+ : pas de mock fallback**.

### Widget KPIs par ligne — Sort + Explore (Sprint VPS-5)

Le widget `dashboard/components/widgets/pro_tcl/line_kpis.py` expose :
- **Sélecteur "Trier par"** : 10 options (OTP↑↓, Retard↑↓, Charge↑↓, Fréq↑↓, Line ID A-Z/Z-A)
- **Slider "Top N"** : 5 → 50 lignes affichées
- **Checkbox "Détails par ligne"** : déplie chaque ligne en cards 4 KPIs
- **Tableau Streamlit** avec barres de progression sur OTP et Charge
- Tri natif Streamlit (click sur les headers)

---

## Provenance des composants

| Composant | Repo source | Raison |
|-----------|-------------|--------|
| ST-GRU-GNN modèle + dataset | FinalProjet | Architecture validée, matrice adjacence H3 |
| Pipeline Medallion psycopg2 | trafficlyon | Production-proven, pas de Polars dans Airflow |
| Structure DAGs | trafficlyon | Le plus mature (10 DAGs testés) |
| Dashboard 18+ pages | trafficlyon | Le plus complet |
| src/ingestion/ collecteurs | LyonFlow | Architecture la plus propre (ABC, tenacity retry) |
| src/routing/ recommandation | LyonFlow | Multimodal scoring composite |
| FastAPI endpoints | LyonFlow | Structure API avancée |
| Pathfinding H3 Dijkstra | LyonFlow | Sprint 8 hotfix 2 — graphe routier Sprint 5 |

### Supprimé (Sprint 8)

| Composant | Raison |
|-----------|--------|
| Kafka | Jamais utilisé réellement |
| MinIO | PostgreSQL suffit (sdb dédié) |
| 458 one-hot vélov | 9GB RAM, remplacé par label encoding |
| Orbit DLT challenger | Conflit schedule, complexité sans gain |
| AR(1) predictor fallback | Dead code |
| Ray cluster HPO | Optuna local suffit |
| **TomTom API** | Module incomplet (helpers sans classe). **No-op Sprint 8**, réactivation Sprint 12+ (dette : coder `TomTomTrafficFlow(DataCollector)`) |
| **Mode démo / mocks** | **VIRÉ Sprint 8**. Politique "zéro mock" — `src/data/mock/` → `tests/fixtures/mock_data/` |

---

## Déploiement

**Cible production : VPS unique** — `51.83.159.224` (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD).
Branche `vps` = source de vérité du déploiement actif.

### Stack VPS (branche `vps`)

| Composant | Détail |
|-----------|--------|
| Reverse proxy | Nginx 1.27 (Sprint VPS-1) — DNS `lyonflowfull.fr` mort, accès par IP `https://51.83.159.224` |
| Process supervisor | systemd unit `lyonflow.service` (Sprint VPS-2) |
| Backup DB | systemd timer quotidien 03:00 → `scripts/backup.sh` (Sprint VPS-2) + offsite `scripts/backup-offsite.sh` |
| Rollback | `make rollback-vps` (Sprint VPS-2) |
| Monitoring | Prometheus + Alertmanager + Grafana via `docker-compose.monitoring.yml` (Sprint 8 : tous UP) |
| Exporters | node, postgres, nginx, redis (Sprint VPS-3) |
| Métriques custom | `src/api/metrics.py` — prédictions, latence, personas, DAGs, MLflow, DB (Sprint VPS-4) |
| **Pipeline trafic** | `dags/ml/dag_live_speed_retrain.py` (Sprint VPS-5) — train XGBoost H+1h + INSERT `*/30` dans `gold.trafic_predictions` |
| **Backfill lat/lon** | `dags/maintenance/backfill_dim_spatial_lat_lon.py` (Sprint 8) — `*/5min`, dérive depuis `h3_id` |
| **Healthcheck** | `scripts/healthcheck-vps.sh` (Sprint 8) — 20 checks (containers, disque, CPU/RAM, DB, endpoints) |
| Stockage DB | `/opt/lyonflow/postgres_data` (volume Docker, disque sdb) |
| Réseau | Ports internes sur 127.0.0.1 uniquement, Nginx seul exposé 80/443 |
| Secrets | `.env` chmod 600, jamais en repo |

### ⚠️ Gotchas déploiement VPS (mis à jour Sprint 8)

- **`/opt/lyonflow/logs/`** doit être `chown 50000:0` récursivement après chaque `rsync` frais. Sinon le worker Celery crash en boucle sur `PermissionError` (Sprint VPS-5).
- **DNS `lyonflowfull.fr` mort** (NXDOMAIN) + cert TLS Let's Encrypt expiré → accès par IP `https://51.83.159.224` (warning cert self-signed).
- **Disque sda1 à 80%** (19 Go libres) — migration des volumes Airflow/MLflow/Grafana/Prometheus vers sdb recommandée (Sprint 8+ à faire).
- **Cache Python .pyc** dans les containers Airflow : purger `find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +` après chaque modification de `src/`. Sinon les DAGs chargent l'ancienne version (Sprint 8+ leçon apprise).
- **Mapping `dim_spatial_grid_mapping.properties_twgid`** (entiers ou strings) ≠ `traffic_features_live.channel_id` (format LYO000xx) — **Sprint 8+ : backfill via h3-py résout lat/lon mais le mapping d'identité est toujours à réconcilier**.

### Commandes déploiement VPS

```bash
make check-deploy-env       # vérifie .deploy.env (chmod 600 + vars critiques)
make deploy-vps             # rsync + restart systemd
./scripts/healthcheck-vps.sh  # 20 checks (Sprint 8+)
make rollback-vps           # rollback dernière release
make monitoring-up          # stack Prometheus/Grafana/Alertmanager
make tls-status             # statut cert Let's Encrypt
```

### Branches dormantes (futur AWS/GCP, NE PAS MERGER)

- `kubernetes` — Phase K8s complète (Kustomize + monitoring + GPU GNN). Cible : EKS / GKE futur.
- `cloud-demo` — Phase démo Jedha (Scaleway Kapsule éphémère). Cible : POC cloud public ponctuel.

---

## Structure cible

```
lyonflowfull/
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── .env.example
├── .deploy.env
├── .gitignore
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── Dockerfile
├── pyproject.toml
├── dags/
│   ├── bronze/             # 3 DAGs (collect_bronze, collect_calendriers_monthly, collect_tomtom_traffic no-op)
│   ├── transforms/         # 2 DAGs (transform_bronze_to_silver, transform_silver_to_gold, build_spatial_mapping)
│   ├── ml/                 # 2 DAGs (dag_live_speed_retrain, retrain_xgboost, retrain_gnn)
│   ├── maintenance/        # 3 DAGs (maintenance.py, backfill_dim_spatial_lat_lon, refresh_lieux_calendrier)
│   └── legacy_github/      # BLOQUÉ par .airflowignore (Sprint 8 audit writers)
├── src/
│   ├── config.py
│   ├── data/
│   │   ├── data_loader.py      # fail loud via DashboardDataError
│   │   ├── db_query.py         # helpers SQL, fallbacks mock virés
│   │   ├── airflow_client.py   # fail loud via DashboardDataError
│   │   ├── exceptions.py       # DashboardDataError
│   │   ├── labels.py           # NOUVEAU Sprint 8 : référentiels statiques
│   │   └── tcl_lines.py        # NOUVEAU Sprint 8 : 10 lignes TCL emblématiques
│   ├── ingestion/          # 8 collecteurs (DataCollector ABC)
│   ├── transformation/     # feature engineering
│   ├── models/             # GNN, XGBoost H+1h focus, delay predictor
│   ├── routing/            # pathfinder_multimodal (Vélov smart + voiture Dijkstra)
│   ├── monitoring/         # Evidently, drift
│   └── api/                # FastAPI endpoints
├── training/
│   └── stgcn/              # GNN model, dataset, train, HPO
├── scripts/
│   ├── sql/                # 20+ migrations (referentiel, vues matérialisées, audit)
│   ├── maintenance/        # backfill scripts
│   └── healthcheck-vps.sh  # NOUVEAU Sprint 8
├── dashboard/              # 18 pages × 3 personas
├── tests/
│   ├── conftest.py             # NOUVEAU Sprint 8 : MockDB + 3 fixtures
│   ├── data/                   # tests unitaires data_loader/db_query
│   ├── ml/                     # tests modèles
│   ├── persona/                # tests widgets
│   ├── integration/            # tests intégration (skippés par défaut)
│   ├── e2e/                    # tests e2e (skippés)
│   └── fixtures/mock_data/     # NOUVEAU Sprint 8 : mocks déplacés ici
├── docs/
│   ├── ADR/                # 4 ADRs (architecture, personas, docker, psycopg2)
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATA_GOVERNANCE.md
│   ├── DEPLOYMENT.md
│   ├── DASHBOARD_PAGES.md
│   ├── MONITORING.md
│   ├── VPS_HARDENING.md
│   ├── RUNBOOK.md
│   ├── PLAN_NO_MOCK_VPS.md
│   ├── PROJECT_STATUS_AND_GOALS.md
│   ├── REPO_STRUCTURE.md
│   ├── GIT_STRUCTURE.md
│   └── CONTROLE_VPS_VS_CLOUD_DEMO.md
├── SPRINT_*.md             # 8 rapports de sprint
└── kubernetes/             # Phase 3 dormante
```

---

## Variables d'environnement

| Variable | Obligatoire | Usage |
|----------|-------------|-------|
| `POSTGRES_USER` | oui | DB user |
| `POSTGRES_PASSWORD` | oui | DB password |
| `POSTGRES_HOST` | oui | DB host |
| `POSTGRES_DB` | oui | DB name |
| `MLFLOW_TRACKING_URI` | oui | MLflow server |
| `LYONFLOW_API_KEY` | oui | FastAPI auth |
| `AIRFLOW_FERNET_KEY` | oui | Chiffrement Airflow |
| `LYONFLOW_DEMO_MODE` | oui (Sprint 8) | **Doit être `0` en prod** (helper retourne toujours False) |
| `SEQ_LEN` | non (120) | Longueur séquence GNN |
| `HORIZONS` | non (6,12,36) | Horizons prédiction GNN |
| `HIDDEN_CHANNELS` | non (128) | Dimension GRU/GCN |
| `WEIGHT_JAM` | non (15) | Pénalité congestion (staircase loss) |
| `WEIGHT_SLOW` | non (5) | Pénalité ralenti |
| `LYON_DEFAULT_SPEED` | non (30.0) | Vitesse imputation fallback |
| `LYON_LATITUDE` | non (45.7640) | Latitude centre Lyon (collecteurs Open-Meteo, chantiers) |
| `LYON_LONGITUDE` | non (4.8357) | Longitude centre Lyon |
| `TOMTOM_API_KEY` | non | TomTom free tier (Sprint 12+ réactivation) |

---

## Commandes

```bash
# Lint
ruff check . --output-format=github
ruff format --check .

# Type check (non-blocking)
mypy dags/ training/ src/ --ignore-missing-imports

# Tests (Sprint 8+ : addopts inclut "-m not integration")
pytest tests/ -v --tb=short
pytest tests/ -m integration  # pour les tests qui ont besoin du stack

# Healthcheck VPS (Sprint 8+)
./scripts/healthcheck-vps.sh

# Stack complète
docker-compose up -d --build
docker compose -f docker-compose.monitoring.yml up -d  # monitoring
```
