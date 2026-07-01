"""DAG — Refresh */15 min de gold.mv_velov_transit_coupling (Sprint 17, 2026-06-20).

Cycle : toutes les 15 min (cohérent avec les autres vues temps réel).

Tache :
1. REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_velov_transit_coupling

Notes :
* Sprint 17 Axe 4 — Vélov ↔ TC report modal.
* La vue calcule le z-score vélos dispos par station Vélov < 300m
  d'une zone où circule une ligne TC (proxy : centre moyen des
  positions GPS de gold.tcl_vehicle_realtime). Detection d'incident
  TC : si >= 3 stations proches d'une meme ligne sont en alarme
  simultanée (z_score < -2) → report modal probable.
* CONCURRENTLY necessite UNIQUE INDEX sur (station_id, transit_line)
  (cree dans migration_023).
* En cas d'echec CONCURRENTLY, fallback REFRESH standard.
* Schedule */15 min (plus rapide que meteo_impact */jour) car la
  detection d'incident TC necessite une reactivite temps reel.
* Logs structures pour monitoring Prometheus.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _refresh_mv_velov_transit_coupling(**context) -> None:
    """Refresh gold.mv_velov_transit_coupling (Sprint 17 Axe 4, migration 023)."""
    from src.db import execute_query

    try:
        # CONCURRENTLY evite les locks en lecture. Necessite UNIQUE INDEX
        # sur (station_id, transit_line) (cree dans migration_023).
        execute_query("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_velov_transit_coupling")
        logger.info("gold.mv_velov_transit_coupling refreshed OK (CONCURRENTLY)")
    except Exception as e:
        # Si CONCURRENTLY echoue (1er run sans index unique, lock
        # concurrent, etc.), on retombe sur un REFRESH standard.
        logger.warning("CONCURRENTLY refresh failed, fallback standard: %s", e)
        execute_query("REFRESH MATERIALIZED VIEW gold.mv_velov_transit_coupling")
        logger.info("gold.mv_velov_transit_coupling refreshed OK (fallback standard)")


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="refresh_velov_transit_coupling",
    description=(
        "Sprint 17 Axe 4 — REFRESH */15 min gold.mv_velov_transit_coupling "
        "(couplage Velov x TC, z-score report modal, migration 023)"
    ),
    default_args=default_args,
    # Décalé 12,27,42,57 (au lieu de */15 pile) — évite le thundering herd
    # :00/:15/:30/:45 (cf. docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md item C1).
    schedule_interval="12,27,42,57 * * * *",
    start_date=datetime(2026, 6, 20),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "gold", "sprint17", "axe4"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_mv_velov_transit_coupling",
        python_callable=_refresh_mv_velov_transit_coupling,
        execution_timeout=timedelta(minutes=5),
    )
