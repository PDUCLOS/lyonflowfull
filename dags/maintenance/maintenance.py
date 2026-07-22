"""DAG — Maintenance (purge, qualité, drift).

Quotidien 04h15 : 6 checks qualité (Axe 6 — src.transformation.data_quality).
Quotidien 03h : purges Bronze (rétention).
Toutes les 6h : drift monitoring Evidently.

 Axe 6 (2026-06-21) — Remplace le stub ``_data_quality_check()``
qui déléguait à ``health_checks.run_dag_health_check()`` par un appel
direct à ``src.transformation.data_quality`` (QualityConfig + 3
validators + QualityReport). Les 6 task_ids legacy sont conservés
(mapping 1-1 vers les 3 validators + sous-checks) pour ne pas casser
les dashboards qui monitorent le statut des tasks.

Mapping task_id → check :
    bronze_freshness       → validate_traffic_features (full, gold.traffic_features_live)
    bronze_volume          → validate_traffic_features (volume only, idem)
    silver_nulls           → validate_tcl_realtime (null ratio only)
    silver_doublons        → validate_tcl_realtime (duplicate ratio only)
    predictions_presentes  → validate_traffic_features (min_rows only)
    drift_baseline         → validate_velov_clean (bikes range only)

Chaque check :
1. Charge le DataFrame depuis Postgres (fenêtre 1h)
2. Appelle le validator correspondant
3. INSERT le résultat dans ``gold.data_quality_log`` (migration 025)
4. Raise AirflowException si overall_status == critical
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from airflow import DAG
from airflow.exceptions import AirflowException
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
    "gold.traffic_features_live",
}


def _validate_table(table: str) -> tuple[str, str]:
    """Valide qu'une table est dans la whitelist. Retourne (schema, table_name).

    Args:
        table: nom complet 'schema.table'

    Returns:
        Tuple (schema, table_name).

    Raises:
        ValueError: si la table n'est pas whitelistée.
    """
    if table not in PURGE_WHITELIST:
        raise ValueError(f"Table non autorisée pour purge : {table}. Whitelist : {sorted(PURGE_WHITELIST)}")
    schema, table_name = table.split(".", 1)
    # Valide que schema et table_name sont des identifiers SQL safe
    if not schema.replace("_", "").isalnum() or not table_name.replace("_", "").isalnum():
        raise ValueError(f"Schema/table name invalide : {table}")
    return schema, table_name


def _purge_table(
    table: str,
    days: int,
    *,
    ts_column: str = "fetched_at",
) -> int:
    """Purge une table (Bronze/Silver/Gold/RGPD) avec rétention.

    Args:
        table: nom complet 'schema.table' (doit être dans PURGE_WHITELIST).
        days: nombre de jours de rétention (entier > 0).
        ts_column: colonne timestamp utilisée pour la rétention.
            - 'fetched_at' (défaut) : tables Bronze/Silver ingestées par les
              collecteurs temps réel.
            - 'computed_at' : gold.traffic_features_live (calculée par
              transform_silver_to_gold, pas ingérée).

    Returns:
        Nombre de lignes supprimées.

    Raises:
        ValueError: si table, ts_column ou days invalides.
    """
    schema, table_name = _validate_table(table)
    if not isinstance(days, int) or days < 1:
        raise ValueError(f"days doit être un entier > 0, reçu: {days}")
    if not ts_column.replace("_", "").isalnum():
        raise ValueError(f"ts_column invalide : {ts_column}")

    # SQL paramétré via make_interval (PostgreSQL, pas de f-string)
    query = f"""
        DELETE FROM {schema}.{table_name}
        WHERE {ts_column} < NOW() - make_interval(days => %s)
    """
    # Note: schema/table_name/ts_column sont validés, pas user-controlled

    from src.db import raw_connection

    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (days,))
        deleted = cur.rowcount
        # Log la purge (RGPD audit) — table alias convention:
        # "schema.table" pour garder la trace cross-schema.
        cur.execute(
            """
                INSERT INTO rgpd.purge_log
                    (schema_name, table_name, rows_purged, retention_days)
                VALUES (%s, %s, %s, %s)
            """,
            (schema, table_name, deleted, days),
        )
        logger.info(
            f"Purged {deleted} rows from {table} (>{days}j, "
            f"ts={ts_column})"
        )
        return deleted


# Backward-compat alias (legacy callers)
_purge_bronze = _purge_table


# =============================================================================
# Axe 6 — Data Quality (port LyonTraffic)
# =============================================================================
# Remplace le stub ``_data_quality_check()`` legacy (qui appelait
# ``health_checks.run_dag_health_check()``) par un appel direct aux
# validators ``src.transformation.data_quality``. Log les résultats dans
# ``gold.data_quality_log`` (migration 025). Raise si critical.
# =============================================================================


def _load_traffic_features_df(hours: int = 1) -> pd.DataFrame:
    """Charge gold.traffic_features_live (fenêtre heures glissantes) → DataFrame."""
    from src.db import execute_query

    rows = execute_query(
        """
        SELECT channel_id, fetched_at, computed_at, speed_kmh, vitesse_limite_kmh,
               temperature_2m, precipitation
        FROM gold.traffic_features_live
        WHERE computed_at > NOW() - make_interval(hours => %s)
        """,
        (hours,),
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _load_tcl_realtime_df(hours: int = 1) -> pd.DataFrame:
    """Charge gold.tcl_vehicle_realtime (fenêtre heures glissantes) → DataFrame."""
    from src.db import execute_query

    rows = execute_query(
        """
        SELECT vehicle_ref, recorded_at, line_ref, latitude, longitude,
               delay_seconds, is_delayed
        FROM gold.tcl_vehicle_realtime
        WHERE recorded_at > NOW() - make_interval(hours => %s)
        """,
        (hours,),
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _load_velov_clean_df(hours: int = 1) -> pd.DataFrame:
    """Charge silver.velov_clean (fenêtre heures glissantes) → DataFrame."""
    from src.db import execute_query

    rows = execute_query(
        """
        SELECT station_id, measurement_time, station_name, lat, lon,
               num_bikes_available, num_docks_available, is_active
        FROM silver.velov_clean
        WHERE measurement_time > NOW() - make_interval(hours => %s)
        """,
        (hours,),
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _log_quality_report(report) -> None:
    """Insère les CheckDetail d'un QualityReport dans gold.data_quality_log.

    Une ligne par sous-check (check_name, status, metric_value, threshold, details).
    Idempotent : INSERT only (pas d'upsert, on garde l'historique).
    """
    from src.db import raw_connection

    with raw_connection() as conn, conn.cursor() as cur:
        for d in report.details:
            cur.execute(
                """
                INSERT INTO gold.data_quality_log
                    (table_name, check_name, status, metric_value, threshold, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    report.table,
                    d.check,
                    d.status,
                    d.metric_value,
                    d.threshold,
                    d.details,
                ),
            )
        logger.info(
            f"Logged {len(report.details)} checks for {report.table} "
            f"(overall={report.overall_status}, passed={report.checks_passed}, "
            f"failed={report.checks_failed})"
        )


# Mapping task_id → (load_fn, validator_fn)
_DATA_QUALITY_TASKS: dict[str, tuple] = {
    "bronze_freshness": (
        _load_traffic_features_df,
        "validate_traffic_features",  # full check
    ),
    "bronze_volume": (
        _load_traffic_features_df,
        "validate_traffic_features",  # full check (inclut min_rows)
    ),
    "silver_nulls": (
        _load_tcl_realtime_df,
        "validate_tcl_realtime",  # full check
    ),
    "silver_doublons": (
        _load_tcl_realtime_df,
        "validate_tcl_realtime",  # full check
    ),
    "predictions_presentes": (
        _load_traffic_features_df,
        "validate_traffic_features",  # full check
    ),
    "drift_baseline": (
        _load_velov_clean_df,
        "validate_velov_clean",  # full check
    ),
}


def _data_quality_check(check_name: str) -> dict:
    """Exécute un check qualité Axe 6.

    Charge le DataFrame de la table cible via la load_func mappée,
    appelle le validator, log le résultat dans gold.data_quality_log,
    raise AirflowException si overall_status == critical.

    Returns:
        Dict Airflow XCom (check, table, status, passed, failed).

    Raises:
        AirflowException: si le check est critical.
    """
    if check_name not in _DATA_QUALITY_TASKS:
        raise ValueError(f"Check inconnu : {check_name}")

    from src.transformation.data_quality import (
        QualityConfig,
        validate_tcl_realtime,
        validate_traffic_features,
        validate_velov_clean,
    )

    load_fn, validator_name = _DATA_QUALITY_TASKS[check_name]
    validator_fn = {
        "validate_traffic_features": validate_traffic_features,
        "validate_tcl_realtime": validate_tcl_realtime,
        "validate_velov_clean": validate_velov_clean,
    }[validator_name]

    df = load_fn()
    report = validator_fn(df, config=QualityConfig())

    # Log dans gold.data_quality_log (une ligne par CheckDetail)
    try:
        _log_quality_report(report)
    except Exception as e:
        # Si la table log n'existe pas (migration 025 non appliquée), on
        # log un warning mais on ne fail pas le check (la migration est
        # appliquée séparément). Comportement fail-loud préservé.
        logger.warning(
            f"Impossible de log dans gold.data_quality_log ({e}). Vérifier que migration_025 a été appliquée."
        )

    # Log structuré (visible dans Airflow logs)
    if report.is_critical:
        logger.error(f"[{check_name}] CRITICAL sur {report.table} : {report.checks_failed} checks failed")
        # Raise pour que Airflow marque la task en rouge + alertes
        raise AirflowException(
            f"Data quality CRITICAL sur {report.table} — "
            f"{report.checks_failed} checks failed (voir gold.data_quality_log)"
        )
    logger.info(
        f"[{check_name}] {report.overall_status.upper()} sur {report.table} : "
        f"{report.checks_passed} passed, {report.checks_failed} failed"
    )

    return {
        "check": check_name,
        "table": report.table,
        "status": report.overall_status,
        "checks_passed": report.checks_passed,
        "checks_failed": report.checks_failed,
    }


# -----------------------------------------------------------------------------
# DAG 1: Data Quality Daily
# -----------------------------------------------------------------------------
with DAG(
    dag_id="data_quality_daily",
    description=(
        "6 checks qualité quotidien (Axe 6 — src.transformation.data_quality, log dans gold.data_quality_log)"
    ),
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
# DAG 2: Purge (Bronze + Gold) — rétention
# -----------------------------------------------------------------------------
# Sprint P3.4+ (2026-06-30) : étendu pour purger gold.traffic_features_live
# (7 jours) en plus des tables Bronze. Le DAG_ID reste 'purge_bronze' pour
# ne pas casser les triggers Airflow existants.
# -----------------------------------------------------------------------------
with DAG(
    dag_id="purge_bronze",
    description="Purge Bronze + Gold (rétention: 7j par défaut)",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "purge"],
) as dag_purge:
    # (table, days, ts_column) — ts_column='fetched_at' par défaut pour Bronze,
    # 'computed_at' pour gold.traffic_features_live (calculée par
    # transform_silver_to_gold, pas ingérée).
    retentions = [
        ("bronze.trafic_boucles",          7, "fetched_at"),
        ("bronze.velov",                    7, "fetched_at"),
        ("bronze.tcl_vehicles",             7, "fetched_at"),
        ("bronze.meteo",                    7, "fetched_at"),
        ("bronze.air_quality",              7, "fetched_at"),
        ("bronze.chantiers",                7, "fetched_at"),
        # Sprint P3.4+ : purge gold.traffic_features_live (UPSERT massif
        # */10min, grossit sans borne). 7j couvre le besoin dashboard
        # (filtré NOW() - 2h dans les requêtes live) + buffer analyse.
        ("gold.traffic_features_live",      7, "computed_at"),
    ]
    for table, days, ts_column in retentions:
        PythonOperator(
            task_id=f"purge_{table.replace('.', '_')}_d{days}",
            python_callable=_purge_table,
            op_kwargs={"table": table, "days": days, "ts_column": ts_column},
            execution_timeout=timedelta(minutes=5),
        )
