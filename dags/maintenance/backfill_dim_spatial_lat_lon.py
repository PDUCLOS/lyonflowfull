"""DAG cron : backfill lat/lon pour gold.dim_spatial_grid_mapping.

 (2026-06-12) — Solution palliative à la dette schéma où un
concurrent writer (probablement dags/legacy_github/dag_pipeline.py, ou
build_spatial_mapping avec ON CONFLICT mal conçu) tronque périodiquement
la table et ré-insère les nœuds SANS backfill des colonnes lat/lon.

Stratégie : ce DAG tourne toutes les 5 min et ne fait QUE mettre à jour
les rows où lat IS NULL OR lon IS NULL, en dérivant depuis h3_id via
h3-py 4.5. Idempotent : si lat/lon sont déjà OK, ne touche à rien.

Solution durable auditer tous les writers + GRANT/REVOKE
pour que build_spatial_mapping soit le seul writer de cette table.

Usage:
    Ce DAG est auto-chargé par Airflow scheduler.
    Fréquence : */5 * * * * (toutes les 5 min)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta

import h3
from airflow import DAG
from airflow.operators.python import PythonOperator

# Permet d'importer src.* depuis le DAG (Airflow worker)
sys.path.insert(0, "/opt/airflow")

from src.db.connection import execute_query, raw_connection

logger = logging.getLogger(__name__)
DAG_ID = "maintenance_backfill_dim_spatial_lat_lon"


def _backfill() -> int:
    """Backfill lat/lon pour les rows où lat IS NULL OR lon IS NULL.

    Returns:
        Nombre de rows mises à jour.
    """
    rows = execute_query(
        """
        SELECT node_idx, h3_id
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NULL OR lon IS NULL
        """
    )
    if not rows:
        logger.info("[backfill] No rows to update")
        return 0

    logger.info("[backfill] %d rows missing lat/lon", len(rows))

    updates = []
    skipped = 0
    for r in rows:
        try:
            lat, lon = h3.cell_to_latlng(r["h3_id"])
            updates.append((lat, lon, r["node_idx"]))
        except Exception as e:
            logger.warning(
                "[backfill] skip node_idx=%s h3_id=%s: %s",
                r["node_idx"],
                r["h3_id"],
                e,
            )
            skipped += 1

    if not updates:
        logger.warning("[backfill] All %d rows failed h3→latlng, nothing to update", len(rows))
        return 0

    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow")
        cur.executemany(
            """
            UPDATE gold.dim_spatial_grid_mapping
            SET lat = %s, lon = %s
            WHERE node_idx = %s
            """,
            updates,
        )
        conn.commit()
        n_updated = cur.rowcount

    logger.info(
        "[backfill] %d rows updated, %d skipped (h3 invalid)",
        n_updated,
        skipped,
    )

    # Vérification post-cron
    after = execute_query(
        """
        SELECT count(*) AS total, count(lat) AS with_lat, count(lon) AS with_lon
        FROM gold.dim_spatial_grid_mapping
        """
    )
    logger.info("[backfill] AFTER: %s", after)

    return n_updated


with DAG(
    dag_id=DAG_ID,
    description="Backfill lat/lon pour gold.dim_spatial_grid_mapping (dette schéma)",
    start_date=datetime(2026, 6, 12),
    schedule="*/5 * * * *",  # toutes les 5 min
    catchup=False,
    max_active_runs=1,  # pas de chevauchement
    default_args={
        "owner": "patrice",
        # (2026-06-12) — Fiabilité VPS : pas de retry.
        # Le DAG tourne toutes les 5 min, on attend le prochain cycle.
        "retries": 0,
        "retry_delay": timedelta(minutes=1),
    },
    tags=["maintenance", "sprint-8-hotfix-5", "dette-schema"],
) as dag:
    PythonOperator(
        task_id="backfill_lat_lon",
        python_callable=_backfill,
    )
