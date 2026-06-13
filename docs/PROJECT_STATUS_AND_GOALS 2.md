# État d'avancement et Objectifs du Projet LyonFlowFull

<<<<<<< HEAD
**Dernière mise à jour :** Juin 2026
=======
**Dernière mise à jour : 2026-06-12 (Sprint VPS-8 livré, branche `vps`)**
>>>>>>> origin/main

Ce document récapitule l'état actuel de l'infrastructure de LyonFlowFull et fixe le cap pour le déploiement MLOps en cours.

---

## 1. Ce qui est accompli et figé (Phase de Fiabilisation)

Le socle technique et logiciel est désormais à un stade de fiabilité "Production-ready".

### Infrastructure & Déploiement (Branche `vps`)
<<<<<<< HEAD
- **Serveur Unique** : Le projet est hébergé de manière autonome sur un VPS Ubuntu (pas de dépendance AWS/GCP). L'environnement Docker est complet (PostgreSQL + MinIO + Redis + Airflow + MLflow + FastAPI + Streamlit).
- **Hardening** : Certificats TLS via Let's Encrypt (Nginx reverse proxy), firewall, et services gérés par Systemd (avec relance automatique en cas de reboot).
- **Supervision** : Stack Prometheus + Grafana configurée. Les métriques de FastAPI et du Dashboard remontent en direct.

### Fiabilité Applicative (Data & QA)
- **Data Binding Total** : Les 45 widgets du Dashboard consomment les données réelles issues de la base de données.
- **Résilience Anti-Crash** : Si la base de données subit une micro-coupure (ex: erreur `OperationalError`), l'application l'intercepte silencieusement, active un "mode hors-ligne" transparent et utilise des données de fallback (Mocks) avec un bandeau préventif. Zéro écran blanc.
- **Couverture de Tests (E2E)** : Les scénarios de navigation pour les différents Personas (notamment les accès sécurisés "Pro TCL" et "Élu") sont validés par **Playwright**.
- **Testabilité Universelle** : Grâce à `make test-docker`, toute la suite de tests s'exécute isolée de l'hôte, évitant l'enfer des dépendances locales (C++, GDAL).

---

## 2. Le cap actuel : Déploiement MLOps

Le pipeline de données (Ingestion ➡️ Bronze ➡️ Silver ➡️ Gold) fonctionne. Le prochain grand jalon consiste à automatiser l'entraînement et l'exposition des modèles prédictifs.

### Les défis à relever (En cours)

1. **Entraînement Automatisé (Airflow)** : 
   - Finaliser les DAGs d'entraînement (`retrain_xgboost.py` et `retrain_gnn.py`) pour qu'ils soient planifiés, exécutés, et qu'ils poussent leurs métriques vers le tracking server MLflow.
2. **Registre de Modèles Dynamique (MLflow)** :
   - Au lieu de lire statiquement des fichiers `.pkl`, le système doit s'appuyer sur le Model Registry de MLflow pour gérer les cycles de vie (`Staging`, `Production`, `Archived`).
3. **Serving Temps-Réel (FastAPI)** :
   - Modifier les endpoints `/api/v1/predict/` pour que l'API télécharge dynamiquement le modèle actuellement tagué "Production" dans MLflow, sans nécessiter de redéploiement de code.
4. **Modélisation Avancée** :
   - Achever l'intégration du Spatio-Temporal Graph Convolutional Network (**ST-GCN**) dans le DAG d'entraînement pour capturer la propagation de la congestion sur le réseau routier, en complément des modèles XGBoost actuels.
=======
- **Serveur Unique** : Le projet est hébergé de manière autonome sur un VPS Ubuntu (51.83.159.224, pas de dépendance AWS/GCP). L'environnement Docker est complet (PostgreSQL + MinIO + Redis + Airflow + MLflow + FastAPI + Streamlit). **2× 100 Go SSD** (sda1 = OS + services, sdb = PostgreSQL + MinIO).
- **Hardening** (Sprint VPS-1) : Certificats TLS via Let's Encrypt (Nginx reverse proxy), firewall, et services gérés par Systemd (avec relance automatique en cas de reboot).
- **Supervision** (Sprint VPS-3 + Sprint 8) : Stack Prometheus + Grafana + Alertmanager (config YAML v2.54 fixée, tous UP). Les métriques de FastAPI et du Dashboard remontent en direct.
- **Backup offsite** (Sprint VPS-2) : Timer systemd quotidien 03:00 → `scripts/backup-offsite.sh` (Google Drive via rclone OU serveur SSH). Stream pur, rien d'écrit sur le disque VPS.
- **Rollback** (Sprint VPS-2) : `make rollback-vps` ramène à la release précédente.
- **Monitoring custom** (Sprint VPS-4) : `src/api/metrics.py` — prédictions, latence, personas, DAGs, MLflow, DB.
- **Healthcheck** (Sprint 8) : `scripts/healthcheck-vps.sh` — 20 checks (containers, disque, CPU/RAM, DB responsive, counts 1h silver, endpoints HTTP). Run avant chaque deploy.

### Fiabilité Applicative (Data & QA)
- **Sprint VPS-8 (2026-06-12) — Politique "zéro mock" STRICTE** :
  - `src/data/mock/` **supprimé** (déplacé dans `tests/fixtures/mock_data/`).
  - Tous les widgets, `data_loader`, `db_query`, `airflow_client` lèvent `DashboardDataError` si DB indispo.
  - 18 fallbacks mock virés (data_loader), 17 (db_query), 2 (airflow_client), 8 widgets.
  - `LYONFLOW_DEMO_MODE=0` obligatoire en prod. `_is_demo_mode()` retourne TOUJOURS False (helper déprécié).
  - Tests `test_no_mock_vps_policy.py` (6 tests) valident la politique.
  - `make check-deploy-env` bloque le deploy si var != 0.
- **Sprint VPS-7 (2026-06-12) — KPIs TCL via vues matérialisées** :
  - `gold.mv_line_kpis_live` (155 lignes TCL avec OTP, retard, fréquence, charge).
  - `gold.mv_otp_heatmap` (4416 triplets ligne×date×hour).
  - DAG `refresh_lieux_calendrier` quotidien 5h.
- **Sprint VPS-8+1 — Focus H+1h strict** (fiabilité VPS) :
  - `xgboost_speed.py` : 14 features → 9, 4 horizons → 1 (H+1h uniquement).
  - DAG `dag_live_speed_retrain` `*/30min`, `retries=0`.
  - DAG `backfill_dim_spatial_lat_lon` `*/5min` (dette schéma `properties_twgid`).
  - Trigger SQL `trg_dim_spatial_has_lat_lon` (défense en profondeur contre lat/lon NULL).
- **Sprint VPS-8+7 — Pathfinding multimode corrigé** :
  - Voiture : Dijkstra sur `gold.dim_spatial_grid_mapping` (1543 nœuds) + `gold.dim_gnn_adjacency` (4072 arêtes K=2) au lieu de `silver.trafic_boucles_clean` (Points isolés).
  - Vélov : `plan_velov_trip` avec smart routing (alternatives + maillage voisines < 200m).
  - 4 hotfix successifs (lat/lon NULL, vitesse_kmh → speed_kmh, signature, smart routing écrasé).
- **Sprint VPS-8+8 — Ingestion Bronze débloquée** :
  - `bronze.air_quality` : 72 records/test (avant : 0 + duplicate key).
  - `bronze.chantiers` : 428 records (avant : 0 + duplicate key).
  - Cause : `UNIQUE INDEX` sur colonnes extracted NULLS (vires, vraies données dans `raw_data` JSONB).
  - `_count_records` étendu au format Open-Meteo imbriqué.
  - `_save_raw` idempotent (skip si 0 records).
- **Pathfinding multimode** (Sprint VPS-6 + VPS-8) : voiture (Dijkstra H3) + Vélov+marche (3 segments : marche → Vélov → marche, stations `silver.velov_clean`). Widget Folium avec carte + polylines colorées + diagnostics.
- **Référentiel lieux en DB** (Sprint VPS-6) : 21 lieux emblématiques Lyon + 56 liaisons transports (T*, M*, C*, bus) + 223 cadences observées par tranche horaire × type de jour. Tables `referentiel.lieux_lyon`, `referentiel.lieux_transports`, `referentiel.lieux_calendrier`. 10 lignes emblématiques extraites dans `src/data/tcl_lines.py` (référentiel statique).
- **Data Binding Total** : Les 47 widgets du Dashboard consomment les données réelles issues de la base de données (zéro mock en Sprint 8).
- **Tests** : **150 tests verts / 9 SKIP / 7 deselected (integration)** (`pytest -m "not integration"` par défaut).
- **Couverture de Tests (E2E)** : Les scénarios de navigation pour les différents Personas (notamment les accès sécurisés "Pro TCL" et "Élu") sont validés par **Playwright**.
- **Testabilité Universelle** : `conftest.py` centralisé (MockDB fixture, 3 fixtures mode démo/prod/no-db), `pyproject.toml` addopts `-m not integration`. Tests skippables en CI sans stack.

---

## 2. Le cap actuel : Stabilisation MLOps

Le pipeline de données (Ingestion ➡️ Bronze ➡️ Silver ➡️ Gold) fonctionne. Le DAG `dag_live_speed_retrain` tourne toutes les 30 min et persiste dans `gold.trafic_predictions`. Le prochain jalon : finaliser le registre MLflow et le serving dynamique.

### Les défis à relever (Sprint 9+)

1. **Registre de Modèles Dynamique (MLflow)** :
   - Au lieu de lire statiquement des fichiers `.pkl`, le système doit s'appuyer sur le Model Registry de MLflow pour gérer les cycles de vie (`Staging`, `Production`, `Archived`).
2. **Serving Temps-Réel (FastAPI)** :
   - Modifier les endpoints `/api/v1/predict/` pour que l'API télécharge dynamiquement le modèle actuellement tagué "Production" dans MLflow, sans nécessiter de redéploiement de code.
3. **Modélisation Avancée** :
   - Achever l'intégration du Spatio-Temporal Graph Convolutional Network (**ST-GCN**) dans le DAG d'entraînement pour capturer la propagation de la congestion sur le réseau routier, en complément des modèles XGBoost actuels.
4. **Migration volumes sda1 → sdb** (Sprint 9 critique) :
   - sda1 à 80% (19 Go libres sur 96 Go). Airflow, MLflow, Grafana, Prometheus, Redis logent sur sda1.
   - Migrer les volumes Docker vers sdb pour libérer de l'espace.
5. **Reconciliation mapping channel_id ↔ properties_twgid** (Sprint 9+) :
   - Le backfill lat/lon (Sprint 8+5) résout la geometrie, mais la jointure d'identité entre `traffic_features_live.channel_id` (string LYO000xx) et `dim_spatial_grid_mapping.properties_twgid` (entiers ou strings) reste à coder proprement pour géocoder les prédictions sur la carte.
6. **Tests e2e intégration** (Sprint 9) : `tests/integration/test_fail_loud_e2e.py` avec PostgreSQL en container (actuellement skippé par défaut).
7. **TomTom Traffic Flow refacto** (Sprint 12+) : coder `TomTomTrafficFlow(DataCollector)` conforme (actuellement no-op).
8. **`_is_demo_mode` déprécié à supprimer** (Sprint 9+) : helper retourne toujours False, à virer quand tous les call sites nettoyés.

---

## 3. Améliorations clés de la session 2026-06-11/12

**Sprint VPS-8 (2026-06-12) — "Zéro mock + Ingestion stable + Focus H+1h"** est l'un des sprints les plus structurants du projet. Il a résolu **3 dettes critiques** :

### A. Suppression complète du mode mock (politique "zéro mock")

**Avant** : 1650 lignes de mocks dans `src/data/mock/`, mode `_is_demo_mode()` qui retournait des données mock silencieusement si la DB était down (le widget affichait des données fake sans que l'utilisateur le sache).

**Après** : `src/data/mock/` **supprimé** (déplacé dans `tests/fixtures/mock_data/`). Tous les widgets fail loud via `DashboardDataError`. **Le projet est désormais 100% DB-driven en production**.

**Impact** : un blip DB est maintenant visible immédiatement (widget rouge + log d'erreur) au lieu d'être masqué par un mock silencieux. Prometheus alerte avant les users. La fiabilité opérationnelle passe d'opaque à transparente.

### B. Dette schéma v0.3.1 résolue

**Avant** : `src/models/xgboost_speed.py` référençait `speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time` qui n'existaient plus dans `gold.traffic_features_live` (renommés en Sprint 5). Les prédictions étaient en mode "baseline = dernière vitesse observée propagée sur 1 horizon".

**Après** : refacto complète sur schéma v0.3.1 avec convention focus H+1h (`lag_h1/h2/h3`, `delta_h1`, `rolling_mean_h1`, `sin_hour`, `temperature_2m`, `precipitation`, `channel_id` string). 14 features → 9 (calcul H+1h uniquement). Le modèle apprend enfin sur les vrais features.

### C. Ingestion Bronze débloquée (air_quality + chantiers)

**Avant** : `bronze.air_quality` (0 rows) et `bronze.chantiers` (0 rows) — les UNIQUE INDEX sur les colonnes extracted (NULL par défaut) faisaient planter en duplicate key à chaque cycle. Le widget météo utilisait donc des données incomplètes (sans qualité de l'air).

**Après** : `bronze.air_quality` ingère 72 records/cycle, `bronze.chantiers` 428 records/cycle. Le widget météo a maintenant accès à la qualité de l'air (PM10, PM2.5, NO2, O3) et la carte bottlenecks peut afficher les chantiers perturbants.

### D. Focus H+1h strict (fiabilité VPS)

**Avant** : 4 horizons XGBoost (5min, 1h, 3h, 6h) = 4 modèles entraînés 1×/h, 75% de mémoire et temps d'entraînement gaspillés sur des horizons peu utilisés.

**Après** : 1 modèle XGBoost H+1h entraîné toutes les 30 min. La prédiction s'aligne sur le cas d'usage principal (recommandation trajet dans 1h). `dag_live_speed_retrain` `*/30` au lieu de `:25` hourly. Réduction de 75% du coût compute ML.

### E. Durcissement monitoring Prometheus/Grafana

**Avant** : config YAML v2.54 cassée (`storage.tsdb.retention.time` au mauvais endroit), `--web.enable-lifecycle` déclenchait des reloads en boucle, Alertmanager webhook manquant. Les 3 services étaient en restart-loop silencieux.

**Après** : tous UP et stables. `healthcheck-vps.sh` 20/20 OK. Métriques dashboard custom intégrées.

### F. Backfill automatisé lat/lon (dette géométrique)

**Avant** : `dim_spatial_grid_mapping.properties_twgid` au format entier n'avait pas lat/lon (dette cachée), bloquant tout le pathfinding voiture.

**Après** : DAG cron `*/5min` qui dérive lat/lon depuis `h3_id` via `h3-py 4.5`. Trigger SQL refuse les INSERT avec lat/lon NULL. Le pathfinding voiture fonctionne (5 segments Dijkstra Part-Dieu → Tête d'Or).
>>>>>>> origin/main

---

> [!NOTE]
<<<<<<< HEAD
> Ce document remplace les anciens plans de migration (AWS, K8s, Sprint 6) qui ont tous été archivés pour maintenir la clarté du référentiel sur notre cible principale : un système autonome, résilient, hébergé sur VPS, piloté par Airflow et MLflow.
=======
> Ce document remplace les anciens plans de migration (AWS, K8s, Sprint 6) qui ont tous été archivés pour maintenir la clarté du référentiel sur notre cible principale : un système autonome, résilient, hébergé sur VPS, piloté par Airflow et MLflow, **zéro mock** depuis Sprint 8.
>>>>>>> origin/main
