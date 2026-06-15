# Documentation DAGs Airflow — LyonFlowFull

> **Sprint 12+** (2026-06-13) — Documentation exhaustive des 18 DAGs en production.
> Source : `airflow dags list` sur VPS + `ast` parsing des docstrings.

**Total** : 18 DAGs actifs (10 Bronze/Silver/Gold + 3 ML + 5 Maintenance/Others)
**Web UI** : http://51.83.159.224:8080/airflow/ (auth Basic Airflow)
**API** : `curl -u admin:$AIRFLOW_ADMIN_PASSWORD http://127.0.0.1:8080/airflow/api/v1/dags`

---

## Vue d'ensemble

| Catégorie | DAG | Schedule | Statut | Sprint |
|---|---|---|---|---|
| **Bronze (ingestion)** | `collect_bronze` | `*/5 * * * *` | ✅ Actif | Sprint 1+ |
| | `collect_calendriers_monthly` | mensuel | ✅ Actif | Sprint 7+ |
| | `collect_tomtom_traffic` | `*/15 * * * *` | ⏸ No-op (Sprint 8, dette réactivation Sprint 12+) | Sprint 8 |
| **Transforms** | `transform_bronze_to_silver` | (voir CLAUDE.md `:05`) | ✅ Actif | Sprint 2+ |
| | `transform_silver_to_gold` | (voir CLAUDE.md `:15`) | ✅ Actif | Sprint 2+ |
| | `build_spatial_mapping` | quotidien | ✅ Actif | Sprint 9+ |
| **ML (training + inference)** | `build_xgb_training_set` | `30 2 * * *` (02h30) | ✅ Actif (unpaused) | Sprint 9+ |
| | `dag_daily_speed_train` | `0 3 * * *` (03h00) | ✅ Actif | Sprint 9+ |
| | `dag_inference_xgboost` | `*/15 * * * *` | ✅ Actif | Sprint 9+ |
| | `dag_live_speed_retrain` | (archivé, `.bak`) | 🗑 Désactivé | Sprint VPS-5 → 9+ |
| | `retrain_xgboost_speed` | `25 * * * *` (`:25`) | ✅ Actif | Sprint 1+ |
| | `retrain_xgboost_velov` | `50 * * * *` (`:50`) | ✅ Actif (H+30min only Sprint 12+) | Sprint 1+ |
| | `retrain_gnn` | daily | ⏸ Paused (waiting OVH training, Sprint 12+) | Sprint 9+ |
| **Maintenance** | `silver_archive_to_minio` | `0 4 * * *` (04h00) | ✅ Actif (Sprint 12+ fix boto3) | Sprint 10+ |
| | `data_quality_daily` | quotidien | ✅ Actif | Sprint 1+ |
| | `purge_bronze` | quotidien | ✅ Actif | Sprint 1+ |
| | `refresh_lieux_calendrier` | `0 5 * * *` (05h00) | ✅ Actif | Sprint 7+ |
| | `maintenance_backfill_dim_spatial_lat_lon` | `*/5 * * * *` (cron) | ⏸ Paused (one-shot, dette résolue) | Sprint 8+ |
| **Routing** | `dag_refresh_road_network` | `0 3 * * *` (03h00) | ✅ Actif | Sprint 12 |

---

## 1. DAGs Bronze (ingestion)

### `collect_bronze` — `*/5 * * * *`
- **Quoi** : itère sur `REALTIME_COLLECTORS` (6 classes) et lance chaque collecteur en parallèle
- **Sources** : Grand Lyon boucles (pvotrafic OGC), Vélo'v GBFS, TCL SIRI Lite, Open-Meteo weather, Open-Meteo air quality, Grand Lyon chantiers
- **Tables** : `bronze.trafic_boucles`, `bronze.velov`, `bronze.tcl_vehicles`, `bronze.meteo`, `bronze.air_quality`, `bronze.chantiers`
- **Pourquoi** : ingestion temps réel, alimente la couche Silver puis Gold
- **Risques** : si l'API Open-Meteo ou Grand Lyon est down, les collecteurs retry (tenacity) puis lèvent

### `collect_calendriers_monthly` — mensuel
- **Quoi** : télécharge les calendriers vacances scolaires (data.education.gouv.fr) + jours fériés (calendrier.api.gouv.fr)
- **Tables** : `bronze.calendrier_scolaire`, `bronze.jours_feries`
- **Pourquoi** : changent rarement, 1x/mois suffit
- **Note** : si la table est vide, le modèle XGBoost `is_vacances=0` partout

### `collect_tomtom_traffic` — `*/15 * * * *` — ⏸ NO-OP
- **Quoi** : était censé collecter TomTom Traffic Flow (API free tier)
- **Statut** : **no-op depuis Sprint 8** (2026-06-12) — le module `src.ingestion.tomtom_traffic` n'a jamais eu la classe `TomTomTrafficFlow(DataCollector)`. Réactivation Sprint 12+ (dette)
- **Action à prendre** : coder la classe ou désactiver complètement le DAG

---

## 2. DAGs Transforms (Silver + Gold)

### `transform_bronze_to_silver` — toutes les 5min après Bronze
- **Quoi** : 5 tâches parallèles (1 par table Bronze) qui nettoient et dédoublonnent
- **Tables** : `silver.trafic_boucles_clean`, `silver.tcl_vehicles_clean`, `silver.velov_clean`, `silver.meteo_hourly`, `silver.chantiers_actifs`
- **Stratégie** : `DISTINCT ON` Postgres, capteurs sains, géo 4326+2154, parse SIRI
- **Sprint 8+** : `silver.trafic_vitesse_propre` 28 Go, archivée quotidiennement

### `transform_silver_to_gold` — toutes les 15min
- **Quoi** : 3 domaines parallèles — Trafic (5 canaux features), Bus (retards agrégés), Vélov (features stations)
- **Tables** : `gold.traffic_features_live`, `gold.bus_delay_segments`, `gold.velov_features`
- **Sprint 9+** : utilise le modèle v0.3.1 (schéma finalisé)

### `build_spatial_mapping` — quotidien
- **Quoi** : matérialise `gold.dim_spatial_grid_mapping` (capteurs → nœuds H3 res 13) + `gold.dim_gnn_adjacency` (arêtes K=2 bidirectionnel + self-loops)
- **Pourquoi** : prépare le graphe pour le GNN ST-GRU-GNN (1520 nœuds, ~9540 arêtes)
- **Sprint 9+** : backfill lat/lon via h3-py 4.5 (résout le NULL des colonnes lat/lon)

---

## 3. DAGs ML (training + inference)

### `build_xgb_training_set` — `30 2 * * *` (02h30 quotidien) ✅ ACTIF
- **Quoi** : construit `gold.xgb_training_set` matérialisé (Sprint 9+)
- **Stratégie** : self-join indexé sur `computed_at + INTERVAL '60 min'`, INSERT batch, purge 14j
- **Pourquoi** : la query `_load_training_data()` du modèle XGBoost timeout (11.5s) depuis Streamlit
- **Test 2026-06-13** : SUCCESS, 359 119 rows sur 1075 channels, mean target 23.57 km/h
- **Sprint 11+** : inclut PSI drift detection (étape 5) → persiste dans `gold.model_drift_reports`

### `dag_daily_speed_train` — `0 3 * * *` (03h00 quotidien)
- **Quoi** : entraînement XGBoost H+1h sur la table `gold.xgb_training_set`
- **Modèle** : `xgb_speed_h60.pkl` persisté sur sdb2 (`/mnt/postgres-data/models/`)
- **Sprint 9+** : `n_jobs=2`, `tree_method=hist`, sub-sample 100k rows (évite OOM)
- **Sortie** : MAE, RMSE, R² loggés dans MLflow + Model Card auto

### `dag_inference_xgboost` — `*/15 * * * *`
- **Quoi** : inférence H+1h toutes les 15min, INSERT dans `gold.trafic_predictions`
- **Lecture** : `gold.traffic_features_live` (live) + modèle pickle
- **Sprint 9+** : focus H+1h strict (1 modèle, pas 4)
- **Fail loud** : si le modèle n'est pas chargé, lève RuntimeError (politique "zéro fallback baseline")

### `dag_live_speed_retrain` — `*/30 * * * *` — 🗑 DÉSACTIVÉ
- **Statut** : archivé en `_disabled_dag_live_speed_retrain.py.bak` (Sprint 12+)
- **Remplacé par** : `dag_daily_speed_train` (03h00) + `dag_inference_xgboost` (`*/15`)
- **Action** : garder en `.bak` pour archive, ne pas réactiver

### `retrain_xgboost_speed` — `25 * * * *` (chaque heure à `:25`)
- **Quoi** : retrain XGBoost trafic (legacy, 4 horizons : 5min, 1h, 3h, 6h)
- **Toggle** : `LYONFLOW_XGBOOST_TRAINING=false` pour désactiver
- **Note** : redondant avec `dag_daily_speed_train` (Sprint 9+), à supprimer Sprint 12+

### `retrain_xgboost_velov` — `50 * * * *` (chaque heure à `:50`)
- **Quoi** : retrain XGBoost Vélov — **H+30min uniquement** (Sprint 12+, Patrice "tout en H+30min pour Vélov")
- **Modèle** : `xgb_velov_h30.pkl` (label encoding 458 stations, 11 features)
- **Features v0.3.1** : `station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos, temperature_c, rain_mm, is_vacances, is_ferie`
- **Toggle** : `LYONFLOW_XGBOOST_TRAINING=false` pour désactiver

### `retrain_gnn` — daily — ⏸ PAUSED
- **Quoi** : retrain ST-GRU-GNN (SpatioTemporalGCN PyTorch Geometric)
- **Statut** : paused (Sprint 9+), données d'entraînement sur `gold.fact_traffic_series` (889k rows × 1544 nœuds)
- **Sprint 12+** : user a créé `scripts/train_gnn_remote.py` + `Dockerfile.gnn-training` pour entraîner sur OVH (compute distant)
- **Action** : à valider avec Patrice avant unpause

---

## 4. DAGs Maintenance

### `silver_archive_to_minio` — `0 4 * * *` (04h00 quotidien) ✅ ACTIF
- **Quoi** : archive `silver.trafic_vitesse_propre` > 30j vers MinIO (Parquet snappy)
- **Ratio** : 28 Go Postgres → 2.8 Go Parquet snappy + DELETE
- **Sprint 12+** : remplace `boto3` (cassé par conflit pyOpenSSL/cryptography) par `urllib3 + AWS Sig V4 manuelle` (cf. `src/minio_s3v4_upload.py`)
- **Risque** : si MinIO down, le DAG fail et la table Postgres continue à grossir

### `data_quality_daily` — quotidien
- **Quoi** : 6 checks qualité (freshness, volume, NULLs, doublons, prédictions, drift)
- **Alerte** : si > 2 checks fail, le DAG raise (visible dans l'UI)
- **Métriques** : exposées sur Prometheus (`lyonflow_quality_check_*`)

### `purge_bronze` — quotidien
- **Quoi** : purge les tables Bronze > 7-45j (rétention selon volume)
- **Stratégie** : `DELETE FROM bronze.trafic_boucles WHERE fetched_at < NOW() - INTERVAL '7 days'` (par table)
- **Sprint 8+** : RGPD compliance

### `refresh_lieux_calendrier` — `0 5 * * *` (05h00 quotidien)
- **Quoi** : `REFRESH MATERIALIZED VIEW gold.mv_line_kpis_live + mv_otp_heatmap + lieux_calendrier`
- **Sprint 7+** : vues matérialisées pour les dashboards Pro (KPIs ligne + OTP heatmap)

### `maintenance_backfill_dim_spatial_lat_lon` — `*/5 * * * *` — ⏸ PAUSED
- **Quoi** : backfill lat/lon sur `gold.dim_spatial_grid_mapping` via h3-py 4.5 (dette schéma)
- **Statut** : paused, dette résolue (Sprint 8+)
- **Action** : one-shot fait, garder pausé

---

## 5. DAGs Routing

### `dag_refresh_road_network` — `0 3 * * *` (03h00 quotidien)
- **Quoi** : refresh du graphe routier OSM via Overpass API (Sprint 12, 2026-06-12)
- **Remplace** : ancien build H3 res 13 par graphe OSM réel
- **Sortie** : `gold.dim_gnn_adjacency` + `gold.dim_spatial_grid_mapping` (joints Sprint 12+)
- **Risque** : si Overpass down, le pathfinder Voiture fallback sur Dijkstra H3

---

## 6. Diagnostic 2026-06-13

### DAGs qui plantaient (avant fix)

| DAG | Erreur | Fix |
|---|---|---|
| `silver_archive_to_minio` | `ModuleNotFoundError: polars` | Ajout `polars>=0.20.0` + `pyarrow>=14.0.0` dans `requirements-airflow.txt` + `docker compose build airflow-*` |
| `silver_archive_to_minio` | `AttributeError: module 'lib' has no attribute 'GEN_EMAIL'` (boto3) | Remplacement `boto3` par `urllib3 + AWS Sig V4 manuelle` (cf. `src/minio_s3v4_upload.py`) |
| `dag_live_speed_retrain` | `AirflowDagDuplicatedIdException` | Renommage `_disabled_dag_live_speed_retrain.py` → `.bak` (Sprint 12+) |

### DAGs pausés volontairement

- `retrain_gnn` — waiting OVH training pipeline (Sprint 12+)
- `maintenance_backfill_dim_spatial_lat_lon` — one-shot terminé (Sprint 8+)
- `collect_tomtom_traffic` — module incomplet (Sprint 8+, dette)

### DAGs à supprimer Sprint 13+

- `retrain_xgboost_speed` (redondant avec `dag_daily_speed_train`, code legacy)
- `collect_tomtom_traffic` (no-op depuis Sprint 8, à fixer ou désactiver définitivement)

---

## 7. Commandes utiles

```bash
# Lister tous les DAGs
docker exec lyonflow-airflow airflow dags list

# Voir les import errors
docker exec lyonflow-airflow airflow dags list-import-errors

# Tester un DAG manuellement
docker exec lyonflow-airflow airflow dags test <DAG_ID> <YYYY-MM-DD>

# Voir les derniers runs d'un DAG
docker exec lyonflow-airflow airflow dags list-runs --dag-id <DAG_ID>

# Logs d'un task instance
docker exec lyonflow-airflow airflow tasks log <DAG_ID> <RUN_ID> <TASK_ID>

# Unpause / pause
docker exec lyonflow-airflow airflow dags unpause <DAG_ID>
docker exec lyonflow-airflow airflow dags pause <DAG_ID>
```

---

*Mis à jour le 2026-06-13 — Sprint 12+ (Vélov H+30min + boto3 fix + port 8080 Airflow exposé).*
