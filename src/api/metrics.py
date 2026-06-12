"""Métriques Prometheus custom pour l'API LyonFlowFull (Sprint VPS-4).

Expose :
- lyonflow_predictions_total : compteur par modèle + horizon
- lyonflow_prediction_latency_seconds : histogramme latence inference
- lyonflow_persona_requests_total : compteur par persona (usager / pro_tcl / elu)
- lyonflow_dag_runs_total : compteur DAGs Airflow (success/failed)
- lyonflow_mlflow_active_runs : gauge runs MLflow actifs
- lyonflow_db_query_duration_seconds : histogramme requêtes DB
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
