"""Métriques Prometheus personnalisées pour l'API LyonFlow.

Expose les métriques suivantes :
- `lyonflow_predictions_total` : Compteur des prédictions par modèle et par horizon temporel.
- `lyonflow_prediction_latency_seconds` : Histogramme de la latence d'inférence.
- `lyonflow_persona_requests_total` : Compteur des requêtes par persona (Usager, Pro TCL, Élu).
- `lyonflow_dag_runs_total` : Compteur des exécutions de DAGs Airflow (succès/échecs).
- `lyonflow_mlflow_active_runs` : Jauge (Gauge) des runs MLflow actuellement actifs.
- `lyonflow_db_query_duration_seconds` : Histogramme de la durée d'exécution des requêtes vers la base de données.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# -----------------------------------------------------------------------------
# Prédictions ML
# -----------------------------------------------------------------------------
PREDICTIONS_TOTAL = Counter(
    "lyonflow_predictions_total",
    "Nombre de prédictions par modèle + horizon",
    ["model", "horizon_minutes", "status"],  # status = success | error
)

PREDICTION_LATENCY = Histogram(
    "lyonflow_prediction_latency_seconds",
    "Latence d'inférence par modèle",
    ["model"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# -----------------------------------------------------------------------------
# Personas
# -----------------------------------------------------------------------------
PERSONA_REQUESTS = Counter(
    "lyonflow_persona_requests_total",
    "Requêtes par persona (lu depuis JWT)",
    ["persona", "endpoint"],
)

# -----------------------------------------------------------------------------
# DAGs Airflow (push via /api/v1/dag-status depuis un callback Airflow)
# -----------------------------------------------------------------------------
DAG_RUNS_TOTAL = Counter(
    "lyonflow_dag_runs_total",
    "Runs DAGs Airflow par dag_id + state",
    ["dag_id", "state"],  # state = success | failed | running
)

# -----------------------------------------------------------------------------
# MLflow
# -----------------------------------------------------------------------------
MLFLOW_ACTIVE_RUNS = Gauge(
    "lyonflow_mlflow_active_runs",
    "Nombre de runs MLflow actifs",
    ["experiment_name"],
)

# -----------------------------------------------------------------------------
# DB
# -----------------------------------------------------------------------------
DB_QUERY_DURATION = Histogram(
    "lyonflow_db_query_duration_seconds",
    "Durée des requêtes DB",
    ["query_type"],  # SELECT | INSERT | UPDATE | DELETE
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
