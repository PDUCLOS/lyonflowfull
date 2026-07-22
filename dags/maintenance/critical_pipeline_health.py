"""DAG — Monitoring critique pipeline (Sprint 23 — 2026-06-27).

Alerte si un DAG critique est désactivé ou si une table Gold clé est
stale > 1h. Cadence */15 min — alignée sur le cycle d'ingestion Bronze.

Pourquoi ce DAG existe :
Le 2026-06-06, les DAGs ``transform_bronze_to_silver`` et
``transform_silver_to_gold`` ont été désactivés (``is_active=False``)
suite à un incident passé. Personne ne s'en est rendu compte pendant
3 semaines — pas d'alerte. Le dashboard a affiché "Pas de données
trafic" sans qu'on sache pourquoi. Cette monitoring comble ce trou.

Critique = un DAG dont la panne bloque le dashboard temps réel.
Voir ``CRITICAL_DAGS`` et ``FRESHNESS_CHECKS`` ci-dessous.

Action en cas de panne :
- Task ``check_critical_dags`` : SELECT is_paused, is_active FROM dag.
- Task ``check_gold_freshness`` : SELECT MAX(computed_at), NOW() - MAX()
  sur les 3 tables Gold critiques (voir ``FRESHNESS_CHECKS``).
- Si anomalie → AirflowException → task failed → Alertmanager notifie.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import psycopg2
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


# DAGs dont la panne bloque le dashboard (paused OU is_active=False)
# Note : SIRI Lite est collecté via collect_bronze (REALTIME_COLLECTORS),
# pas via un DAG dédié. Le vieux dag_collect_siri_lite est un fantôme en DB.
CRITICAL_DAGS = [
    "collect_bronze",
    "transform_bronze_to_silver",
    "transform_silver_to_gold",
    "dag_inference_xgboost",
]

# Tables Gold dont la fraîcheur < 1h est requise pour le dashboard
# (table, ts_column, max_age_minutes)
#
# Sprint 24+ (2026-06-29) : gold.infrastructure_bottlenecks RETIRÉE — table
# "poids mort" (cf. SPRINT_24_FIX_GOLD_STALE.md section 7). Sa logique a été
# remplacée par gold.mv_bus_traffic_spatial (Sprint 22++). À supprimer
# définitivement quand correlation_matrix.py / segment_table.py liront la MV
# spatiale (consommateurs legacy).
FRESHNESS_CHECKS = [
    ("gold.traffic_features_live", "computed_at", 30),  # carte trafic
    ("gold.tcl_vehicle_realtime", "recorded_at", 30),  # Pro_TCL
    ("gold.trafic_predictions", "calculated_at", 90),  # H+1h
]


def _pg_conn(dbname: str | None = None):
    """Connexion PostgreSQL via env vars (Sprint 23 — pattern uniforme).

    Utilise POSTGRES_HOST/USER/PASSWORD/DB définis dans docker-compose.yml.
    Le hook Airflow ``postgres_default`` pointe sur user ``postgres`` qui
    n'est pas notre user DB — d'où l'auth fail du premier run.

    Args:
        dbname: nom de la DB. Si None, utilise POSTGRES_DB (lyonflow).
                Pour les tables Airflow metadata (``dag``, ``dag_run``),
                passer explicitement ``airflow``.
    """
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=dbname or os.getenv("POSTGRES_DB", "lyonflow"),
        user=os.getenv("POSTGRES_USER", "lyonflow"),
        password=os.environ["POSTGRES_PASSWORD"],
    )


def check_critical_dags() -> dict[str, dict[str, Any]]:
    """Vérifie que tous les DAGs critiques sont actifs et non pausés.

    Raises:
        AirflowException: si au moins un DAG critique est en panne.
    """
    with _pg_conn(dbname="airflow") as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT dag_id, is_paused, is_active FROM dag WHERE dag_id = ANY(%s)",
            (CRITICAL_DAGS,),
        )
        rows = cur.fetchall()

    state_map = {dag_id: {"is_paused": p, "is_active": a} for dag_id, p, a in rows}
    missing = [d for d in CRITICAL_DAGS if d not in state_map]
    paused = [d for d, s in state_map.items() if s["is_paused"]]
    inactive = [d for d, s in state_map.items() if not s["is_active"]]

    anomalies = []
    if missing:
        anomalies.append(f"DAGs absents du scheduler: {missing}")
    if paused:
        anomalies.append(f"DAGs en pause: {paused}")
    if inactive:
        anomalies.append(f"DAGs désactivés (is_active=False): {inactive}")

    if anomalies:
        msg = "Pipeline critique en panne ! " + " | ".join(anomalies)
        logger.error(msg)
        raise AirflowException(msg)

    logger.info("Tous les %d DAGs critiques OK (actifs, non pausés)", len(CRITICAL_DAGS))
    return state_map


def check_gold_freshness() -> dict[str, str]:
    """Vérifie que les tables Gold critiques sont fresh (< seuil)."""
    results: dict[str, str] = {}
    anomalies: list[str] = []

    with _pg_conn() as conn, conn.cursor() as cur:
        for table, ts_col, max_age_min in FRESHNESS_CHECKS:
            cur.execute(f"SELECT MAX({ts_col}), NOW() - MAX({ts_col}) FROM {table}")
            row = cur.fetchone()
            max_ts, age = row if row else (None, None)
            if max_ts is None or age is None:
                anomalies.append(f"{table}: VIDE (aucune ligne)")
                results[table] = "EMPTY"
                continue
            age_min = age.total_seconds() / 60
            if age_min > max_age_min:
                anomalies.append(f"{table}: stale ({age_min:.0f} min > {max_age_min} min)")
                results[table] = f"STALE ({age_min:.0f} min)"
            else:
                results[table] = f"OK ({age_min:.0f} min)"

    for table, status in results.items():
        logger.info("  %s: %s", table, status)

    if anomalies:
        msg = "Tables Gold critiques stale ! " + " | ".join(anomalies)
        logger.error(msg)
        raise AirflowException(msg)

    logger.info("Toutes les %d tables Gold critiques sont fresh", len(FRESHNESS_CHECKS))
    return results


default_args = {
    "owner": "lyonflow",
    "retries": 0,  # on veut une alerte par cycle, pas de retry silencieux
    "execution_timeout": timedelta(minutes=2),
}

with DAG(
    dag_id="dag_critical_pipeline_health",
    description=(
        "Sprint 23 — Monitoring */15 min des DAGs critiques + fraîcheur Gold. "
        "Alerte via AirflowException → Alertmanager → email/Slack."
    ),
    default_args=default_args,
    schedule_interval="*/15 * * * *",
    start_date=datetime(2026, 6, 27),
    catchup=False,
    max_active_runs=1,
    tags=["monitoring", "sprint23", "critical"],
) as dag:
    dags_ok = PythonOperator(
        task_id="check_critical_dags",
        python_callable=check_critical_dags,
    )
    gold_ok = PythonOperator(
        task_id="check_gold_freshness",
        python_callable=check_gold_freshness,
    )

    # Indépendantes — pas de dépendance entre les deux checks
    dags_ok  # noqa: B018  (pattern Airflow DAG : référencer l'opérateur l'enregistre)
    gold_ok  # noqa: B018  (idem)
