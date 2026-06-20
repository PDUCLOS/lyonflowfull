"""DAG Airflow — Daily drift report (Evidently sur gold.mv_xgb_vs_tomtom).

Sprint 16 Axe A (2026-06-20) — Calcule le rapport de drift Evidently
quotidien sur la distribution des erreurs XGBoost vs TomTom. Persiste le
résultat dans ``gold.model_drift_reports`` pour affichage par le widget
``drift_status_badge`` (Elu_1_Synthese) et ``backtest_dashboard`` (Pro_7).

Compare :
- **Reference** = J-7 → J-1 (168h glissantes, fenêtre 6 derniers jours)
- **Current**   = dernières 24h

Features numériques : ``xgb_speed_kmh, tomtom_speed_kmh, error_abs_kmh,
error_pct, tomtom_confidence``.

Schedule : ``30 5 * * *`` (05h30 quotidien, après le refresh de
``gold.mv_xgb_vs_tomtom`` à 05h00 et le ``daily_speed_train`` à 03h00).

Voir ``docs/SPEC_SPRINT_16.md`` §A.4, §A.8, §A.11.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db.connection import raw_connection
from src.monitoring.drift_detector import persist_drift_report, run_drift_report

logger = logging.getLogger(__name__)

DAG_ID = "daily_drift_report"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def _run_and_persist(**context) -> dict:
    """Calcule le rapport de drift et l'insère dans gold.model_drift_reports."""
    report = run_drift_report()
    with raw_connection() as conn:
        ok = persist_drift_report(report, conn)
    logger.info(
        "drift_report dataset_drift=%s, n_drifted=%d, share=%.2f, persisted=%s",
        report["dataset_drift"],
        report["n_drifted_features"],
        report["share_drifted_features"],
        ok,
    )
    return {
        "dataset_drift": report["dataset_drift"],
        "n_drifted_features": report["n_drifted_features"],
        "share_drifted_features": report["share_drifted_features"],
        "n_ref": report["n_ref"],
        "n_current": report["n_current"],
        "persisted": ok,
    }


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description=(
        "Sprint 16 Axe A — Daily Evidently drift report sur XGBoost vs TomTom"
    ),
    schedule_interval="30 5 * * *",
    start_date=datetime(2026, 6, 20),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "monitoring", "drift", "sprint16"],
) as dag:
    drift = PythonOperator(
        task_id="compute_and_persist_drift",
        python_callable=_run_and_persist,
        execution_timeout=timedelta(minutes=10),
    )
