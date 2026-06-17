# PDUCLOS/LyonFlow — Analyse Complète

**Repo**: `PDUCLOS/LyonFlow` (local: `~/Documents/GitHub/LyonFlow`)
**Généré**: 2026-06-05

---

## 1. Architecture

Plateforme MLOps avec pattern Lambda simplifié. 5 services Docker (PostgreSQL+PostGIS, MinIO, Kafka, MLflow, Airflow). Architecture Medallion (bronze/gold schemas). Portable SSD via chemins configurables.

---

## 2. Pipeline de Données

### Sources (10+ APIs live)

| Source | Auth | Fréquence | Volume |
|--------|------|-----------|--------|
| Grand Lyon — Boucles magnétiques | Compte gratuit | 60s | ~1000 tronçons |
| Grand Lyon — Comptages mobilité | Aucune | 15 min | 291 sites, 1000 canaux |
| Grand Lyon — Chantiers | Aucune | 1x/jour | ~345 actifs |
| Grand Lyon — Permis voirie | Aucune | 1x/jour | ~1439 permis |
| Grand Lyon — Événements routiers | Compte | Temps réel | Variable |
| Vélo'v GBFS 3.0 | Aucune | 5 min | 453 stations |
| LPA Parkings | Compte | Temps réel | ~30 parkings |
| Open-Meteo Forecast | Aucune | 1h | 10 variables, 7 jours |
| Open-Meteo Air Quality | Aucune | 1h | 7 variables, 5 jours |
| Navitia (itinéraires) | Token gratuit | À la demande | TCL + vélo + marche |
| TCL GTFS (SYTRAL) | Aucune | Statique | 8862 arrêts, 653 lignes |

### Gold Construction (4 étapes)

channels_ref → meteo_seasonal → enrichissement capacité routière via PostGIS spatial join → features_traffic (~810K lignes, 22 features). Toutes opérations idempotentes.

---

## 3. Modèles ML

### XGBoost MOTORIZED (38 features)
- MAE=0.94, R²=0.990
- Target transformée avec log1p(clip(y, 263))
- Sample weights priorisent modes motorisés

### XGBoost SOFT (32 features)
- MAE=3.26, R²=0.747
- Split temporel au 2023-05-09
- Hyperparamètres Optuna-tuned

---

## 4. DAGs Airflow (3)

| DAG | Schedule | Rôle |
|-----|----------|------|
| collect_all_sources | */15 * * * * | 4 collecteurs parallèles |
| daily_retrain_congestion | daily 6h | Branching: promote/adaptive search/skip |
| refresh_calendrier_annuel | monthly | 4 tâches ref data parallèles |

---

## 5. Dashboard Streamlit

Multi-pages avec cartes Folium interactives, charts Plotly, chargement modèle XGBoost réel.

- **Carte trafic**: heatmap/layers
- **Prédictions**: feature importance
- **Recommandation multimodale**: prédictions XGBoost live
- **Monitoring modèle**: détection drift

---

## 6. Source Code (src/)

### src/ingestion/ (15 collecteurs)

Classe de base `DataCollector` (ABC, Template Method: fetch → validate → save_raw, tenacity retry 3x exponential). Collecteurs: comptages, comptages_history, trafic_boucles, velov, meteo, air_quality, chantiers (2), parkings, prix_carburants, tcl_gtfs, tcl_siri_lite, tomtom_flow, vitesse_limite, voies_lyonnaises.

### src/api/main.py

FastAPI v2.0.0. 6 endpoints: /health, /api/v1/models, POST /predict, GET /predict/hourly, GET /recommend, POST /recommend. API key optionnelle. CORS restreint. Charge modèles MOTORIZED/SOFT au startup.

### src/routing/ (8 modules)

travel_recommender.py (orchestrateur), eligibility.py (vélov exclus si enfant <14, pluie >0.5mm/h, vent >35km/h), pricing.py (voiture fuel, TCL age, vélov free <30min), navitia.py, osrm.py, eco_calculator.py, parking.py, trajectory_planner.py.

### src/models/

trainer.py, model_selection.py, hyperparameter_tuning.py.

### src/monitoring/

drift_report.py (Evidently ou PSI fallback), model_monitor.py.

---

## 7. Tests

23 tests couvrant 1 module sur ~15. Tous tests font des appels API live.

---

## 8. Docker (5 services)

PostgreSQL+PostGIS, MinIO, Kafka (Docker mais inutilisé par le code), MLflow, Airflow.

---

## 9. Notebooks (5)

01_eda_comptages, 02_verify_gold, 03_feature_engineering, 04_preparation_train_test, 05_modelisation_complete.

---

## 10. Problèmes Majeurs

1. **FastAPI module vide** (planifié, pas implémenté)
2. **Kafka et MinIO dans Docker mais inutilisés** par le code applicatif
3. **3 tâches DAG squelettes** (save_to_bronze, transform_to_gold, quality_check)
4. **model_selection.py** référencé dans DAG mais absent du repo
5. **Mot de passe Airflow admin hardcodé** dans docker-compose.yml
6. **URL miroir TCL GTFS contient API key** embarquée
7. **Dashboard utilise données démo/simulées**, pas PostgreSQL
8. **Pas de workflow CI/CD** malgré les claims README
9. **Seulement 23 tests**, tous avec appels API live

---

## 11. Docs

- architecture.md
- LyonFlow_Chef_Projet.pptx
- LyonFlow_Projet_Certification.md / .docx (v1 et v2)

---

## 12. Dépendances

requirements.txt: httpx, tenacity, polars, geopandas, shapely, pyproj, xgboost, lightgbm, scikit-learn, mlflow, optuna, fastapi, uvicorn, evidently, minio, confluent-kafka, streamlit, streamlit-folium, folium, plotly, matplotlib, pydantic, python-dotenv, pytest.
