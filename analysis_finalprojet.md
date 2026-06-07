# FinalProjet — Analyse Complète

**Repo**: `caroheymes/Architect-IA-final-project`
**Généré**: 2026-06-05

---

## 1. Architecture

Plateforme MLOps end-to-end pour prédiction vitesse trafic Grand Lyon (~1100 segments, ~1520 nœuds GNN, ~9540 arêtes).

### Services Docker (8 containers)

| Service | Port | Image | Ressources |
|---------|------|-------|-----------|
| PostgreSQL 15 | 5432 | postgres:15-alpine | 0.5 CPU, 2 GB |
| MLflow | 5000 | ghcr.io/mlflow/mlflow | 1.0 CPU, 2 GB |
| Ray Head | 8265, 10001, 6379 | lyonflow-ray (custom) | 1.0 CPU, 3 GB |
| Ray Worker | — | lyonflow-ray (custom) | 1.0 CPU, 9 GB + 1 GPU |
| Airflow Init | — | lyonflow-app | — |
| Airflow Webserver | 8080 | lyonflow-app | 0.5 CPU, 1.5 GB |
| Airflow Scheduler | — | lyonflow-app | 0.5 CPU, 1.5 GB |
| Streamlit | 8501 | lyonflow-app | 0.25 CPU, 1 GB |

Total: 4.75 CPUs, 20.5 GB RAM, 1 GPU. PostgreSQL sert 3 bases (lyonflow, airflow, mlflow) via init-db.sql. Airflow LocalExecutor.

---

## 2. Pipeline de Données (Medallion)

### Bronze: `bronze.trafic_vitesse_brute`

```sql
CREATE TABLE IF NOT EXISTS bronze.trafic_vitesse_brute (
    id SERIAL PRIMARY KEY,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB NOT NULL
);
```

Source: Grand Lyon WFS API. Stocke la FeatureCollection GeoJSON complète par cycle d'ingestion.

### Silver: `silver.trafic_vitesse_propre`

Colonnes: id_rue, properties_twgid, properties_gid, properties_libelle, properties_sens, properties_etat, properties_vitesse (float), properties_last_update, properties_est_a_jour, speed_category, speed_color_map, geometry_wgs84_wkt (WKT EPSG:4326), points_json (interpolés 7m), hexes_json (H3 res.13), merged_h3_geometry_json, transformed_at.

**Transformations**: Flatten JSON → filtrer est_a_jour → LineString (2154) → interpoler 7m → reprojeter 4326 → H3 index (res.13) → merger polygones H3 → nettoyer vitesse → imputer NaN avec moyenne par rue → catégoriser → export CSV+GeoJSON → append Silver.

### Gold: 3 tables + 1 par inférence

- **`gold.dim_spatial_grid_mapping`**: node_idx, properties_twgid, matrix_i, matrix_j, h3_id, updated_at. Mappe capteurs → indices nœuds séquentiels via h3.cell_to_local_ij().
- **`gold.dim_gnn_adjacency`**: node_u, node_v, is_connected, updated_at. Arêtes non-dirigées via H3 partagés dans K=2 grid_disk.
- **`gold.fact_traffic_series`**: timestamp, node_idx, properties_vitesse, imputed. Une ligne par capteur par timestamp. Imputation: mesuré → moyenne historique → LYON_DEFAULT_SPEED (30 km/h).
- **`gold.fact_predictions_traffic`**: prediction_timestamp, target_timestamp, horizon_minutes, node_idx, predicted_speed, real_speed, geometry_wgs84_wkt.

Stratégie d'écriture: Transaction atomique — TRUNCATE dimensions + DELETE/INSERT facts. Capteurs avec < 90% NaN inclus.

---

## 3. Modèle ML: ST-GRU-GNN

### Architecture (model.py, 76 lignes)

Classe `SpatioTemporalGCN(nn.Module)` — PAS le STGCN de Yu et al. (2018). Hybride récurrent-spatial:

1. **GRU** (input=5, hidden=hidden_channels, 1 couche, batch_first) → dernier hidden state `h_temp [B*N, hidden]`
2. **GCNConv** (hidden, hidden) + LeakyReLU(0.2) + skip connection (+h_temp) → h_space1
3. **GCNConv** (hidden, hidden) + LeakyReLU(0.2) + skip connection (+h_space1) → h_space2
4. **Linear** (hidden, out_channels) → prédictions `[B*N, out_channels]`

### Dataset (dataset.py, 243 lignes)

5 canaux par timestep par nœud: speed (StandardScaler), hour_sin, hour_cos, day_sin, day_cos. Fenêtre glissante, split chronologique 80/20. Graphe: arêtes bidirectionnelles + self-loops → edge_index [2, 2*E + N].

### Training (train_stgcn.py, 469 lignes)

Défauts: SEQ_LEN=120 (10h), BATCH_SIZE=2, HIDDEN=128, LR=0.001, EPOCHS=100. **Staircase weighted MSE**: WEIGHT_JAM=15 (<10 km/h), WEIGHT_SLOW=5 (10-30), WEIGHT_NORMAL=1 (>30). Gradient clipping max_norm=1.0. Early stopping patience=10 sur test MAE. Post-training: analyse erreur stratifiée (bins 10 km/h) + figure 4 panels → MLflow.

### HPO (hpo_stgcn.py, 247 lignes)

Optuna Bayesian TPE. Espace: lr [1e-4,1e-2], hidden {64,128,256}, weight_decay [1e-6,1e-4], seq_len {6,12,18,24}, batch_size {8,16}, weight_jam [5,20], weight_slow [2,8]. MedianPruner, 15 epochs/trial, 20 trials. PostgreSQL RDBStorage. **Problème**: HPO utilise out_channels=1, production utilise 3 horizons.

### Inférence (predict_stgcn.py, 344 lignes)

Charge 120 derniers timesteps, normalise, forward pass, dé-normalise, clip [1,130], sauve CSV + insert DB. Horizons par défaut: 6,12,36 (30min, 1h, 3h).

### Backfill (backfill_predictions.py, 327 lignes)

Remplit prédictions manquantes pour tous les timestamps historiques. Batch insert tous les 15 timestamps.

### Best Params (get_best_params.py, 156 lignes)

Priorité: Optuna DB → MLflow API → défauts hardcodés. Force seq_len=120, cap batch_size à 16.

---

## 4. DAGs Airflow

### `lyonflow_traffic_pipeline` (toutes les 5 min)

```
ingest_grand_lyon_traffic → spatial_transformation_and_mapping → materialize_gold_layer → export_gold_to_csv → stgcn_predict_on_ray
```

Chaîne linéaire. Retries=2, delay=30s, max_active_runs=1, catchup=False. Job Ray via REST POST ray-head:8265, poll 10s.

### `lyonflow_monitoring_pipeline` (daily 11:00)

Tâche unique: soumet monitoring_evidently.py à Ray. Credentials via Airflow connection postgres_default.

---

## 5. Dashboard Streamlit

### Page principale (app.py, 532 lignes)

Carte trafic temps réel (Pydeck ScatterplotLayer ~1100 segments), HexagonLayer 3D optionnel, prédictions multi-horizon AR(3) (30min/1h/3h), filtre catégorie, 5 KPI cards, tooltips enrichis PVO, table détail, explainer méthodologie. Données: PostgreSQL Gold ou CSV fallback.

### Page 1: Analyse d'Erreur Stratifiée

Sélecteur run MLflow experiment "7", télécharge PNG artefact analyse erreur, affiche 4 métriques globales (MAE, RMSE, MAPE, R2).

### Page 2: Courbes d'Apprentissage

Historiques métriques MLflow train_loss_std et test_mae_kmh, chart Plotly 2 panels.

### Page 3: Pipeline Status

Connexion PostgreSQL + tailles tables, runs MLflow (10 derniers), healthcheck Airflow HTTP, métriques environnement.

---

## 6. Tests (23 cas, 7 fichiers)

| Fichier | Cas | Couverture |
|---------|-----|----------|
| test_ingest.py | 2 | Ingestion success + API failure (mocké) |
| test_transform.py | 4 | Speed category, interpolation, H3 merge, pipeline Silver |
| test_stgcn_model.py | 7 | Init modèle, forward shape, gradients, staircase loss, dataset |
| test_migrate_historical.py | 2 | Migration success + dossier vide |
| test_bronze_fields.py | 3 | Intégration Bronze (nécessite DATABASE_URL) |
| test_cache_hits.py | 3 | Cache H3 merge |
| test_super_cache.py | 2 | Super cache + sérialisation WKT |

**Non couvert**: predictor.py, traffic_data.py, ui_helpers.py, export/import, monitoring, predict, backfill, HPO, pages Streamlit.

---

## 7. CI/CD

### CI (ci.yml)

Push/PR main/master. Jobs: lint (ruff, bloquant), typecheck (mypy, non-bloquant), tests (pytest, bloquant), docker-build (Dockerfile + Dockerfile.ray), security-scan (Trivy, exit-code 0).

### CD (cd.yml — supprimé dans working tree)

Push main. Jobs: build-push (GHCR), tag (semver auto-bump), deploy-staging (kubectl apply K8s), smoke-test (pg_isready, airflow, ray, DAG list).

### ML Training (ml-training.yml — supprimé dans working tree)

Manuel + cron dimanche 3h. Jobs: test-model, export-data (Gold→CSV), HPO (GPU self-hosted), train-champion (epochs=100, horizons=6,12,36), promote (MAE gate + GitHub Release).

---

## 8. Kubernetes (6 manifests)

postgres (1 replica, 5432), mlflow (1 replica, 5000), ray-head + ray-worker (1 chacun), airflow-webserver + scheduler (1 chacun, 8080), streamlit (1 replica, 8501), secrets-template. Health probes uniquement PostgreSQL et MLflow.

---

## 9. Utilitaires

| Fichier | Rôle |
|---------|------|
| predictor.py | Fallback AR(1) median-reversion pour dashboard. _fit_ar3_coefficients() = dead code |
| traffic_data.py | Loaders cachés (Gold DB ou CSV), catégorisation vitesse |
| ui_helpers.py | Composants Streamlit partagés, CSS, health checks |
| export_db_to_csv.py | Gold → CSV (node_mapping, edges, traffic_series) |
| import_gold_from_csv.py | CSV → Gold via psycopg2 COPY, CLI --dry-run/--no-truncate |
| inspect_silver.py | Inspecteur schéma Silver (credentials hardcodés) |
| monitoring_evidently.py | Evidently comparaison pic matin (J-1 vs J) |

---

## 10. Configuration

- **pyproject.toml**: Python 3.12, ruff (line-length 120), mypy (non-blocking)
- **requirements.txt**: 18 deps. 5 pinned (geospatial+plotly+pydantic), 13 unpinned
- **docker-compose.yml**: YAML anchors Airflow, LocalExecutor, GPU Ray worker

---

## 11. Problèmes / Dette Technique (22 items)

1. HPO/Training mismatch horizons (1 vs 3)
2. MLflow experiment ID "7" hardcodé
3. Fallback run ID hardcodé
4. Dead code _fit_ar3_coefficients()
5. Inconsistance mot de passe (lyonflow_password vs lyonflow)
6. Credentials hardcodés dans inspect_silver.py
7. Références trash/ dans pages
8. CD manque image tag lyonflow-app
9. Pas de health probes K8s pour Airflow/Ray/Streamlit
10. Fernet key hardcodée docker-compose
11. MLflow --disable-security-middleware
12. Data leakage: StandardScaler fit avant split
13. HORIZONS inconsistant ("1" training vs "6,12,36" inférence)
14. f-string SQL dans predict_stgcn.py
15. Pas de déduplication Bronze sur retry DAG
16. GPU requis sans fallback CPU
17. CD + ml-training workflows supprimés du working tree

---

## 12. Dépendances

18 packages Python. 5 pinned, 13 unpinned. Manque explicite: python-dotenv, matplotlib, scikit-learn (transitifs disponibles).
