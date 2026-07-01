"""DAG cron : snapshot du score de santé réseau dans gold.network_health_history.

 P4.3 (2026-06-22) — Peuple l'historique des scores de santé réseau
(Axe 5) pour alimenter la sparkline 24h du widget Élu `network_health_gauge`.

Stratégie :
    Tourne toutes les 15 min (*/15), appelle gold.fn_network_health_score() qui
    retourne 1 ligne avec le score global 0-100 + 4 flags de disponibilité,
    puis INSERT dans gold.network_health_history avec ON CONFLICT DO NOTHING
    (idempotent — la PK est recorded_at).

    Les 4 sous-scores détaillés (traffic_score, tcl_score, velov_score,
    meteo_score) restent NULL pour l'instant : la fonction SQL
    fn_network_health_score() (migration 019) ne les expose pas encore.
    Migration 031 (TODO) les ajoutera si le besoin se fait sentir pour debug.

Rétention : 7 jours (purge auto par la 2ème task, cf. maintenance.py).
Volume : 96 snapshots/jour * 7 jours = 672 rows (négligeable).  # noqa: RUF002 — multiplication sign intentional

Usage:
    Auto-chargé par Airflow scheduler.
    Fréquence : */15 * * * * (toutes les 15 min)
    Dépendances : aucune (DAG feuille).
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Permet d'importer src.* depuis le DAG (Airflow worker)
sys.path.insert(0, "/opt/airflow")

from src.db.connection import execute_query

logger = logging.getLogger(__name__)
DAG_ID = "maintenance_record_network_health"


def _record_health() -> int:
    """Lit le score de santé réseau actuel et l'insère dans l'historique.

    Returns:
        1 si INSERT réussi, 0 si fonction SQL ne retourne rien (sources indispo).
    """
    rows = execute_query("SELECT * FROM gold.fn_network_health_score()")
    if not rows:
        logger.warning("gold.fn_network_health_score() ne retourne aucune ligne")
        return 0

    r = dict(rows[0])
    score = float(r["score"])

    # Liste des sources actives au moment du snapshot (pour debug redistribution poids)
    available_sources = []
    if r.get("traffic_available"):
        available_sources.append("trafic")
    if r.get("tcl_available"):
        available_sources.append("tcl")
    if r.get("velov_available"):
        available_sources.append("velov")
    if r.get("meteo_available"):
        available_sources.append("meteo")

    # INSERT idempotent : PK = recorded_at, ON CONFLICT DO NOTHING
    # si 2 DAG runs tombent dans la même minute (rare, mais safe).
    execute_query(
        """
        INSERT INTO gold.network_health_history
            (recorded_at, score, traffic_score, tcl_score, velov_score, meteo_score, available_sources)
        VALUES (%s, %s, NULL, NULL, NULL, NULL, %s)
        ON CONFLICT (recorded_at) DO NOTHING
        """,
        (r["computed_at"], score, available_sources),
    )
    logger.info(
        "network_health snapshot inséré: score=%.1f sources=%s",
        score,
        available_sources,
    )
    return 1


def _purge_old() -> int:
    """Purge les snapshots > 7 jours (rétention Gold).

    Returns:
        Nombre de rows supprimées.
    """
    cutoff = datetime.now(UTC) - timedelta(days=7)
    execute_query(
        "DELETE FROM gold.network_health_history WHERE recorded_at < %s",
        (cutoff,),
    )
    logger.info("network_health_history: rows < %s purgées", cutoff.isoformat())
    return 1


# DAG Airflow
default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,  # le cycle */15 min suivant rattrape (cf. )
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=2),  # fonction SQL rapide (~1s)
}

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Snapshot 15-min du score santé réseau (Axe 5) → gold.network_health_history",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 6, 22, tzinfo=UTC),
    catchup=False,  # pas de backfill des snapshots passés
    max_active_runs=1,  # 1 seule exécution concurrente (évite ON CONFLICT)
    tags=["maintenance", "sprint-21", "p4.3", "network-health"],
) as dag:
    record = PythonOperator(
        task_id="record_health",
        python_callable=_record_health,
    )
    purge = PythonOperator(
        task_id="purge_old_7d",
        python_callable=_purge_old,
    )
    record >> purge
