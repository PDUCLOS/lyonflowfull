# `dags/ml/` — DAGs Machine Learning

DAGs Airflow qui pilotent l'entraînement, l'inférence et le suivi qualité
des modèles ML du projet LyonFlow.

## DAGs (état 2026-10-03)

| DAG | Schedule | Rôle | Modèles concernés |
|-----|----------|------|-------------------|
| `build_xgb_training_set` | `30 2 * * *` (02h30) | Matérialise `gold.xgb_training_set` | upstream training |
| `dag_daily_speed_train` | `38 3 * * *` (03h38) | Entraînement quotidien XGBoost Speed H+1h, enregistré et promu en Production dans MLflow | `xgboost_speed_h60` |
| `dag_inference_xgboost` | `*/15 * * * *` | Inférence pure (pas de fit) → `gold.trafic_predictions` | `xgboost_speed_h60` |
| `retrain_xgboost_velov` | `50 * * * *` (hourly :50) | Retrain XGBoost Vélov H+1h | `xgboost_velov_h60` |
| `dag_inference_velov` | `4,19,34,49 * * * *` | Inférence Vélov | `xgboost_velov_h60` |
| `daily_drift_report` | `30 5 * * *` (05h30) | Drift Evidently / PSI quotidien → `gold.model_drift_reports` | `xgboost_speed_h60` |
| `refresh_xgb_vs_tomtom` | `5,35 * * * *` | Backtest H+1h : prédiction vs vitesse Grand Lyon observée 1 h plus tard (nom historique, TomTom mis de côté le 2026-09-28) | `xgboost_speed_h60` |
| `retrain_xgboost_speed` | `25 * * * *` — **EN PAUSE depuis le 2026-07-01** | Ancien retrain horaire, H+1h seul | `xgboost_speed_h60` |

> **`retrain_xgboost_speed` en pause, volontairement** : il entraîne le même
> modèle H+1h que `dag_daily_speed_train`, sur la même table
> `gold.xgb_training_set`, qui n'est reconstruite qu'une fois par jour (02h30).
> Le relancer toutes les heures produisait des runs MLflow identiques (mêmes
> métriques à 12 décimales sur 24 runs) et occupait le pool `ml_training`
> (1 slot, partagé avec `retrain_xgboost_velov` et `dag_daily_speed_train`).
> Pour réentraîner à la demande : `airflow dags trigger dag_daily_speed_train`.
>
> `retrain_gnn` a été archivé (`archive/legacy/gnn/retrain_gnn.py`).

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
