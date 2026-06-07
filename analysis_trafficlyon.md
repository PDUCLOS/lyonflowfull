# PDUCLOS/lyontraffic (trafficlyon) — Analyse Complète

**Repo**: `PDUCLOS/LyonFlow` (local: `~/Documents/trafficlyon`)
**Remote VPS**: `ssh://ubuntu@51.83.159.224/opt/lyonflow`
**Généré**: 2026-06-05

---

## 1. Architecture

Plateforme MLOps complète pour prédiction trafic multimodal (véhicules, vélos, piétons, transit) sur Métropole de Lyon. Cycle complet: ingestion API temps réel → Medallion → ML training → Dashboard Streamlit.

### Stack

Airflow 2.9 (8080) | PostgreSQL 16 + PostGIS (5432) | MinIO S3 (9000/9001) | MLflow 2.12 (5000) | FastAPI (8000) | Streamlit (8501) | Nginx (80) | XGBoost + Orbit DLT | Evidently AI | psycopg2 + Polars | Python 3.12.

### Sources données actives (8)

Grand Lyon pvotrafic (2403 segments, 15min), CRITER boucles (294 capteurs, 15min), Vélo'v GBFS (458 stations, 5min), TCL SIRI Lite (5min), Open-Meteo weather (horaire), Open-Meteo air quality (horaire), Grand Lyon chantiers (daily), vitesse limite (weekly).

---

## 2. Pipeline Medallion

### Bronze (9 tables)

| Table | Lignes est. | Rétention |
|-------|------------|-----------|
| bronze.trafic_boucles | ~25M | 45j |
| bronze.pvotrafic_snapshots | ~2.4M | 30j |
| bronze.velov | ~1.6M | 14j |
| bronze.tcl_vehicles | ~573k | 7j |
| bronze.meteo | ~3.2k | — |
| bronze.air_quality | ~7.8k | — |
| bronze.chantiers | ~682 | — |
| bronze.comptages | ~352k (gelé 2023) | — |
| bronze.vitesse_limite_ref | ~5.4k | — |

Deux vues capteurs sains filtrent capteurs bloqués.

### Silver (4 tables)

trafic_boucles_clean, velov_clean, meteo_hourly, tcl_vehicle_clean. Transformés par transform_to_silver.py via dag_transform_bronze_to_silver toutes les 5 min. DISTINCT ON dédup, filtrage capteurs sains.

### Gold (10+ tables/vues)

| Table | Lignes | Description |
|-------|--------|-------------|
| traffic_features_live | ~1.96M | 29 colonnes: lags/deltas/temporel/channel_hash/météo |
| velov_features_live | ~887 | ~487 features avec 458 station one-hot |
| trafic_predictions | ~53k | rétention 48h |
| tcl_vehicle_realtime | ~635k | positions GPS bus |
| channels_ref | — | référentiel capteurs |
| tarifs_modes | — | tarification multimodale |
| model_drift_reports | 14 | rapports Evidently |
| predictions_vs_actuals | ~457k | backtesting |
| multimodal_status_grid | vue | grille status multimodal |
| boucles_tomtom_compare | vue | comparaison boucles/TomTom |

Transformation: psycopg2 pur (pas Polars — container Airflow n'a pas Polars). Pattern: CREATE IF NOT EXISTS → TRUNCATE → SELECT avec feature engineering SQL → INSERT via executemany (50k traffic / 5k velov par batch).

---

## 3. Modèles ML

### XGBoost Live Speed (4 horizons) — ACTIF

Source: gold.traffic_features_live. 23 features. Retrain horaire à :20.

| Horizon | MAE | R² | Fichier |
|---------|-----|-----|---------|
| H+5min | 1.962 km/h | 0.947 | model_live_speed.pkl |
| H+1h | 2.428 km/h | 0.929 | model_live_speed_h1.pkl |
| H+3h | 2.424 km/h | 0.922 | model_live_speed_h3.pkl |
| H+6h | 2.326 km/h | 0.917 | model_live_speed_h6.pkl |

Pipeline training: Load gold → recalcule channel_hash Polars (xxhash seed=42 % 1M, incompatible avec SQL hashtext) → join météo T+H → target via shift(-steps).over("channel_id") → temporal quantile split → XGBRegressor early stopping 30 rounds → quality gate MAE ≤ prev × 1.15 → save .pkl + _meta.json.

### XGBoost Vélo'v Availability (3 horizons) — ACTIF

Source: bronze.velov (bypass silver/gold). ~490 features (22 temporel + 458 station one-hot + 7 lags + 3 rolling). Retrain horaire à :40. Lookback: 7 jours.

| Horizon | MAE | R² |
|---------|-----|-----|
| H+1h | 4.203 bikes | 0.331 |
| H+3h | 4.312 bikes | 0.299 |
| H+6h | 4.724 bikes | 0.192 |

### Orbit DLT — Challenger

Bayesian structural time series. Compare XGBoost MAE vs Orbit sMAPE pour H+1h et H+3h. Winner stocké model_winners.json (cache 6h). DAG: dag_live_orbit_retrain à :20.

---

## 4. DAGs Airflow (13 actifs)

| DAG | Schedule | Rôle |
|-----|----------|------|
| collect_all_sources | */5 * * * * | Ingestion multi-source → MinIO bronze → PostgreSQL bronze |
| collect_pvotrafic | */15 * * * * | PVO traffic snapshots (2403 segments) |
| dag_collect_meteo_hourly | 0 * * * * | Open-Meteo weather → bronze.meteo |
| dag_collect_siri_lite | */5 * * * * | TCL SIRI Lite GPS positions (BashOperator) |
| collect_chantiers_daily | 0 6 * * * | Chantiers Grand Lyon |
| dag_transform_bronze_to_silver | */5 * * * * | 4 transforms parallèles (boucles, velov, meteo, tcl) |
| dag_transform_silver_to_gold | 15,30,45,55 * * * * | 2 parallèles (traffic, velov). **PAUSED sur VPS** |
| dag_live_speed_retrain | 20 * * * * | Retrain 4 XGBoost speed + store predictions |
| dag_live_orbit_retrain | 20 * * * * | XGBoost vs Orbit comparison + winner |
| dag_velov_availability_retrain | 40 * * * * | Retrain 3 Vélo'v models (30min timeout, 9GB) |
| dag_data_quality_daily | 15 4 * * * | 6 checks: freshness, volume, NULLs, doublons, prédictions |
| dag_model_drift_monitoring | 0 */6 * * * | Evidently DataDriftPreset → gold.model_drift_reports |
| dag_purge_bronze | 0 3 * * * | 5 purges parallèles par rétention |

### Séquence horaire

:00 météo → :05 bronze.* → :10 silver.* → :15 gold.* → :20 ML speed → :40 ML vélov

### Archivés (6)

dag_backfill_meteo, dag_collect_carburants, dag_daily_retrain, dag_data_quality_daily (old), dag_dbt_bronze_to_gold, dag_refresh_calendrier_annuel.

Tous les DAGs utilisent on_failure_callback (log + webhook Slack/Discord).

---

## 5. Dashboard Streamlit (9 + Accueil)

Entrée: dashboard/Accueil.py. Thème dark "control room" (Space Grotesk/Inter).

| Page | Contenu |
|------|---------|
| Accueil | 5 KPI cards, carte Folium preview, prédictions H+1/3/6, évolution 12h, top 10 congestion, ticker live |
| 1 - Carte Trafic | Folium avec flèches SVG (bearings OSM), vue temporelle RT/H+1/3/6, overlay chantiers |
| 2 - Prédictions | 4 métriques vitesse depuis gold.traffic_features_live |
| 3 - Vélo'v | 458 stations, historique 72h, prédictions H+1/3/6, alternatives Haversine, alertes < 3 vélos |
| 4 - Suivi | Historique métriques modèles, rapports drift |
| 5 - RGPD | Conformité GDPR |
| 6 - TCL Temps Réel | Carte Folium bus/tram GPS coloré par retard |
| 7 - Synergie Multimodale | HeatMap score 0-10 par zone ~1km |
| 8 - Analyse Fiabilité | Backtesting prédictions vs actuals |
| 9 - Recommandation Trajet | Planificateur multimodal, profil, badges éligibilité, scoring composite (50% temps + 30% coût + 20% éco). Mode démo sans Navitia |

Composants: data_loader.py, sidebar_nav.py, theme.py.

---

## 6. Scripts (~20 actifs)

| Script | Rôle |
|--------|------|
| train_live_speed_model.py | 4 XGBoost speed, quality gate MAE×1.15 |
| train_velov_availability_model.py | 3 Vélo'v models |
| store_live_speed_predictions.py | Scoring + storage, clamp max(0, pred) |
| store_orbit_predictions.py | Dispatch winner model, CI si Orbit |
| transform_to_silver.py | --boucles/--velov/--meteo/--tcl |
| transform_silver_to_gold.py | --traffic/--velov, psycopg2 pur |
| process_tcl_siri_lite.py | Parse SIRI JSON → bronze + gold |
| precompute_sensor_bearings.py | Bearings OSM pour carte |
| backup_postgres.sh / restore_postgres.sh | Backup/restore DB |
| create_multimodal_view.py | Vue multimodale |

---

## 7. Source Code (src/)

### src/config.py (510 lignes)

16 URLs API, 28 axes TomTom, 8 dataclasses config, coordonnées Lyon.

### src/ingestion/ (15 collecteurs)

Classe de base DataCollector (ABC, Template Method, tenacity retry 3x). Collecteurs: comptages, trafic_boucles (HTTP Basic), velov, meteo, air_quality, chantiers, parkings, prix_carburants, tcl_gtfs (API key), tcl_siri_lite, tomtom_flow (API key), vitesse_limite, voies_lyonnaises.

### src/api/main.py

FastAPI v2.0.0. /health, /api/v1/models, /predict, /predict/hourly, /recommend. API key optionnelle. Charge MOTORIZED/SOFT au startup.

### src/routing/ (8 modules)

Orchestrateur recommandation: météo/AQI → Navitia → éligibilité → pricing → score composite.

### src/monitoring/

DriftReportGenerator: Evidently ou PSI fallback. Seuils configurables (30% WARNING, 50% CRITICAL). Storage cascade: MLflow → MinIO → local.

---

## 8. Tests (5 fichiers)

test_live_speed_model.py (37 tests), test_ingestion.py (~10, API live), test_tcl_siri_lite.py (5), test_transform_silver.py, test_data_freshness.py. CI utilise PostGIS 16 service container.

---

## 9. CI/CD

ci-cd.yml: Push main, PR main. Pipeline: Lint (ruff) | Security (pip-audit + bandit + gitleaks) → Test (pytest + PostGIS) → Build → Deploy (SSH VPS: git reset --hard + docker compose up -d --build + nginx reload + migrations + smoke test).

---

## 10. Docker (7 services)

postgres (PostGIS 16), minio, mlflow (1G), airflow (9G — pic Vélo'v retrain), api (512M), streamlit (300M→900M), nginx. Ports sauf 80 liés à 127.0.0.1. Kafka désactivé.

---

## 11. Notebooks

Principal (6): EDA comptages, verify gold, feature engineering, train/test prep, modélisation complète, live speed model. MLOps Vélo'v validation (5): EDA, feature engineering, model comparison, feature importance, retraining validation.

---

## 12. Documentation

architecture_complete, ROADMAP, pipeline_reference, 8 guides opérations, 4 code reviews, 18 docs historiques, 10 docs MLOps validation, présentations certification.

---

## 13. Monitoring Evidently

- DAG (chaque 6h): référence 7j-6h vs courant 6h, Evidently DataDriftPreset ou drift manuel
- Module: DriftReportGenerator, seuils 30%/50%, storage cascade MLflow→MinIO→local
- Qualité (daily 4h15): 6 checks freshness/volume/NULLs/doublons/prédictions

---

## 14. Problèmes / Dette Technique

### Ouverts
- SEC-004: pas d'auth API sans LYONFLOW_API_KEY
- BUG-003: Silver→Gold DAG pausé sur VPS
- BUG-004: token Navitia vide
- QD-006: channel_hash mismatch SQL (hashtext) vs Polars (xxhash)

### Dette technique
1. Conflit schedule :20 (2 DAGs retrain speed)
2. SQL injection dans purge DAG (f-string table names)
3. channel_hash incohérent Gold SQL vs Polars
4. Bare except dans Accueil.py
5. Pression mémoire (8.7GB Vélo'v retrain sur 11GB VPS)
6. Données démo dans API channels endpoint
7. Import Literal manquant dans api/main.py
8. IP VPS hardcodée dans docker-compose.yml
9. Ruff ignores permissifs
10. Pas de model registry formel
11. TRUNCATE+INSERT = fenêtre Gold vide
12. 458 colonnes one-hot station pour Vélo'v

---

## 15. VPS Deployment

- IP: 51.83.159.224, Path: /opt/lyonflow, User: ubuntu
- SSH key: ~/.ssh/lyonflow_deploy
- Deploy: GitHub Actions → SSH → git reset --hard → docker compose up -d --build → nginx reload → migrations → smoke test
- Accès: Dashboard :80, Airflow /airflow, API /api, MLflow :5001
- Secrets dans /opt/lyonflow/.env (jamais commité)

---

## Résumé

13 DAGs | 9+1 pages dashboard | 7 modèles ML production | 15 collecteurs | 7 services Docker | 5 fichiers test | 9 bronze + 4 silver + 10+ gold tables | ~30 env vars | ~15k+ lignes Python
