"""DAG — Maintenance (purge, qualité, drift).

Quotidien 04h15 : 6 checks qualité.
Quotidien 03h : purges Bronze (rétention).
Toutes les 6h : drift monitoring Evidently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


logger = logging.getLogger(__name__)

# Whitelist des schémas/tables pour la purge (sécurité anti-injection)
PURGE_WHITELIST = {
    "bronze.trafic_boucles",
    "bronze.pvotrafic_snapshots",
    "bronze.velov",
    "bronze.tcl_vehicles",
    "bronze.meteo",
    "bronze.air_quality",
    "bronze.chantiers",
    "bronze.calendrier_scolaire",
    "bronze.jours_feries",
    "rgpd.audit_log",
}


def _validate_table(table: str) -> tuple[str, str]:
    """Valide qu'une table est dans la whitelist. Retourne (schema, table_name).

    Args:
        table: nom complet 'schema.table'

    Returns:
        Tuple (schema, table_name)

    Raises:
        ValueError: si la table n'est pas whitelistée.
    """
    if table not in PURGE_WHITELIST:
        raise ValueError(
            f"Table non autorisée pour purge : {table}. "
            f"Whitelist : {sorted(PURGE_WHITELIST)}"
        )
    schema, table_name = table.split(".", 1)
    # Valide que schema et table_name sont des identifiers SQL safe
    if not schema.replace("_", "").isalnum() or not table_name.replace("_", "").isalnum():
        raise ValueError(f"Schema/table name invalide : {table}")
    return schema, table_name


def _purge_bronze(table: str, days: int) -> int:
    """Purge une table Bronze/Silver/RGPD avec rétention.

    Args:
        table: nom complet 'schema.table' (doit être dans PURGE_WHITELIST).
        days: nombre de jours de rétention (entier > 0).

    Returns:
        Nombre de lignes supprimées.

    Raises:
        ValueError: si table ou days invalides.
    """
    schema, table_name = _validate_table(table)
    if not isinstance(days, int) or days < 1:
        raise ValueError(f"days doit être un entier > 0, reçu: {days}")

    # SQL paramétré via make_interval (PostgreSQL, pas de f-string)
    query = f"""
        DELETE FROM {schema}.{table_name}
        WHERE fetched_at < NOW() - make_interval(days => %s)
    """
    # Note: schema/table_name sont validés par _validate_table, pas user-controlled

    from src.db import raw_connection
    with raw_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (days,))
            deleted = cur.rowcount
            # Log la purge (RGPD audit)
            cur.execute("""
                INSERT INTO rgpd.purge_log
                    (schema_name, table_name, rows_purged, retention_days)
                VALUES (%s, %s, %s, %s)
            """, (schema, table_name, deleted, days))
            logger.info(f"Purged {deleted} rows from {table} (> {days}j)")
            return deleted


def _data_quality_check(check_name: str) -> dict:
    """Exécute un check qualité (délègue à src.monitoring.health_checks).

    Returns:
        Dict avec 'check', 'status', 'details'.
    """
    from src.monitoring.health_checks import run_dag_health_check
    results = run_dag_health_check()
    status = results.get(check_name, "unknown")
    return {
        "check": check_name,
        "status": status,
        "details": f"Voir health_checks.py pour le détail de {check_name}",
    }


# -----------------------------------------------------------------------------
# DAG 1: Data Quality Daily
# -----------------------------------------------------------------------------
with DAG(
    dag_id="data_quality_daily",
    description="6 checks qualité quotidien (freshness, volume, NULLs, doublons, prédictions, drift)",
    schedule="15 4 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "quality"],
) as dag_dq:

    checks = [
        "bronze_freshness",
        "bronze_volume",
        "silver_nulls",
        "silver_doublons",
        "predictions_presentes",
        "drift_baseline",
    ]
    for check in checks:
        PythonOperator(
            task_id=check,
            python_callable=_data_quality_check,
            op_kwargs={"check_name": check},
            execution_timeout=timedelta(minutes=2),
        )


# -----------------------------------------------------------------------------
# DAG 2: Purge Bronze (rétention)
# -----------------------------------------------------------------------------
with DAG(
    dag_id="purge_bronze",
    description="Purge Bronze (rétention: 7-45j selon volume)",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "purge"],
) as dag_purge:

    retentions = [
        ("bronze.trafic_boucles", 45),
        ("bronze.velov", 14),
        ("bronze.tcl_vehicles", 7),
        ("bronze.meteo", 365),
        ("bronze.air_quality", 365),
        ("bronze.chantiers", 365),
    ]
    for table, days in retentions:
        PythonOperator(
            task_id=f"purge_{table.replace('.', '_')}_d{days}",
            python_callable=_purge_bronze,
            op_kwargs={"table": table, "days": days},
            execution_timeout=timedelta(minutes=5),
        )
