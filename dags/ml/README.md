# `dags/ml/` — DAGs Machine Learning

DAGs Airflow qui pilotent l'entraînement, l'inférence et le suivi qualité
des modèles ML du projet LyonFlow.

## DAGs actifs (Sprint 22+)

| DAG | Schedule | Rôle | Modèles concernés |
|-----|----------|------|-------------------|
| `dag_daily_speed_train` | `0 3 * * *` (03h00 daily) | Entraînement quotidien XGBoost Speed | `xgboost_speed_h60` |
| `dag_inference_xgboost` | `*/15 * * * *` | Inférence pure (pas de fit) | `xgboost_speed_h60` |
| `build_xgb_training_set` | `30 2 * * *` (02h30 daily) | Matérialise `gold.xgb_training_set` | upstream training |
| `retrain_xgboost_speed` | `25 * * * *` (hourly :25) | Retrain XGBoost Speed — **🟡 voir TODO ci-dessous** | `xgboost_speed_h5/h60/h180/h360` |
| `retrain_xgboost_velov` | `50 * * * *` (hourly :50) | Retrain XGBoost Vélov (2 horizons) | `xgboost_velov_h30`, `xgboost_velov_h60` |
| `retrain_gnn` | `0 3 * * *` | Train ST-GCN GNN — toggle `LYONFLOW_STGCN_TRAINING` | (PyTorch state_dict) |
| `daily_drift_report` | `30 5 * * *` (05h30 daily) | Drift Evidently quotidien | Tous |
| `refresh_xgb_vs_tomtom` | `*/30 * * * *` | Backtest XGBoost vs TomTom | `xgboost_speed_h60` vs TomTom |

> **🟡 TODO Sprint 22+ — Incohérence H+1h strict** : `retrain_xgboost_speed`
> tourne encore hourly avec **4 horizons** (5min, 1h, 3h, 6h) — en
> contradiction avec la règle projet (Sprint VPS-6 : focus H+1h strict).
> Le DAG `dag_daily_speed_train` (1×/jour 03h00) le remplace fonctionnellement
> pour H+1h, mais `retrain_xgboost_speed` n'a pas été désactivé/archivé.
> **Action recommandée Sprint 22+** : ajouter toggle `LYONFLOW_XGBOOST_TRAINING`
> effectif (déjà câblé dans `_is_xgboost_dag_enabled()`) pour skip le DAG,
> ou déplacer le fichier vers `archive/dags_disabled/`.

## DAGs archivés

| DAG (ancien path) | Archive path | Raison |
|-------------------|--------------|--------|
| `_disabled_dag_live_speed_retrain.py` | `archive/dags_disabled/dag_live_speed_retrain_disabled.py` | Sprint 9+ — training/inf séparés (`dag_daily_speed_train` 1×/jour + `dag_inference_xgboost` */15) |

**Convention** : déplacer (jamais supprimer) vers `archive/dags_disabled/`
pour traçabilité RNCP 38777. Préfixe `_` ignoré par Airflow = le DAG
n'apparaît pas dans l'UI, mais le fichier reste dans le repo.

## Toggles d'activation

| Toggle env | Effet si False |
|-----------|----------------|
| `LYONFLOW_XGBOOST_TRAINING` | `retrain_xgboost_speed` + `retrain_xgboost_velov` skip (XGBoost non réentraîné) |
| `LYONFLOW_STGCN_TRAINING` | `retrain_gnn` skip (GNN non réentraîné) |
| `LYONFLOW_DASHBOARD_GNN_MAP` | `render_gnn_map_section` affiche bandeau désactivé |
| `LYONFLOW_DASHBOARD_MODEL_MONITORING` | `render_model_monitoring_page` affiche bandeau désactivé |

## Stack MLflow

* Tracking URI : `MLFLOW_TRACKING_URI` (défaut `http://localhost:5000`)
* Expériences par modèle (séparation = bonne pratique) :
  * `xgboost_speed` — XGBoost Speed
  * `xgboost_velov` — XGBoost Vélov
* Pas de default global "lyonflow-traffic" (supprimé Sprint 22+)
