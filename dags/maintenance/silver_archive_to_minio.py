"""DAG Airflow — Archive les tables silver > 30j vers MinIO (Parquet snappy).

Sprint 10+ Optimisation (2026-06-12) — ``silver.trafic_vitesse_propre``
fait 28 Go et continue à grossir (~500 Mo/jour). 80% de ces données ont
> 30 jours et ne sont plus utilisées par les modèles (fenêtre Gold :
2 jours). On les archive :

1. Export en **Parquet snappy** (compression ~10x vs raw text/JSON)
2. Push dans ``s3://lyonflow-bronze/silver_archive/<table>/YYYY/MM/``
3. DELETE Postgres (libère ~25 Go)

**Ratio attendu** : 28 Go → 2.8 Go en Parquet snappy, puis DELETE.

**Stratégie Parquet** : on dump avec polars.read_database + write_parquet.

**Push MinIO** : Sprint 12+ — boto3 cassé sur airflow:2.9.3 (pyOpenSSL
`AttributeError: module 'lib' has no attribute 'GEN_EMAIL'` — conflit
boto3 1.34+ / cryptography 41+). On utilise ``urllib3`` + AWS Signature
V4 manuelle (``src.minio_s3v4_upload``). Pas de boto3 dans les deps.

Schedule : quotidien 04h00 (après dag_daily_speed_train 03h00).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.config import get_settings
from src.db.connection import execute_query, raw_connection
from src.minio_s3v4_upload import upload_file_to_minio

logger = logging.getLogger(__name__)

DAG_ID = "silver_archive_to_minio"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=30),
}

# Tables silver à archiver > RETENTION_DAYS.
#
# Format : (table_name, date_column). La colonne date est utilisée pour
# le filtre WHERE et l'ORDER BY. Avant, le DAG assumait `transformed_at`
# pour toutes les tables, mais tcl_vehicles_clean et velov_clean utilisent
# `fetched_at` (legacy, leur date de transformation n'est pas trackée).
#
# Sprint P2-quater (2026-06-16) — élargissement à tcl_vehicles_clean +
# velov_clean + rétention 30j → 7j (la table trafic_vitesse_propre n'a
# que 13 jours d'historique, 30j ne déclenchait jamais d'archive).
SILVER_TABLES: list[tuple[str, str]] = [
    ("trafic_vitesse_propre", "transformed_at"),  # 28 Go, 1.5M rows
    ("tcl_vehicles_clean", "fetched_at"),         # ~260 Mo
    ("velov_clean", "fetched_at"),                # ~282 Mo
]

RETENTION_DAYS = 7  # garde 7 jours en DB (Gold lit les 2 derniers jours, le reste va sur MinIO froid)
LOCAL_STAGING = Path("/tmp/silver_archive_staging")


def _archive_one_table(table: str, date_col: str, cutoff: datetime) -> dict:
    """Archive une table silver > cutoff vers MinIO en Parquet snappy.

    Args:
        table: nom de la table (sans le schema).
        date_col: nom de la colonne date utilisée pour le filtre.
        cutoff: datetime — on archive les rows < cutoff.

    Returns:
        Dict {"table", "rows_archived", "bytes_db", "bytes_parquet", "compression_ratio"}.
    """
    logger.info("Archiving silver.%s (date_col=%s) older than %s", table, date_col, cutoff)

    # 1) Stats avant
    stats = execute_query(
        f"""
        SELECT
            count(*) AS n_rows,
            pg_size_pretty(pg_total_relation_size('silver.{table}')) AS total_size
        FROM silver.{table}
        WHERE {date_col} < %s
    """,
        (cutoff,),
    )
    if not stats or stats[0]["n_rows"] == 0:
        logger.info("silver.%s — no rows to archive", table)
        return {"table": table, "rows_archived": 0}

    n_rows = int(stats[0]["n_rows"])
    logger.info("silver.%s — %s rows to archive (size: %s)", table, n_rows, stats[0]["total_size"])

    # 2) Export en Parquet via polars.read_database
    #    Note: on chunk par 50k rows pour éviter OOM sur gros volumes.
    LOCAL_STAGING.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_STAGING / f"{table}_{cutoff.strftime('%Y%m%d')}.parquet"

    # Lecture via polars directement (psycopg2 + polars.read_database).
    # Note : on n'utilise pas cur.copy_expert (qui ne sert à rien ici —
    # le résultat serait ignoré, et la signature psycopg2 v3 exige un
    # file-like object qu'on ne fournit pas). Le commentaire original
    # disait "Phase 2" mais Phase 1 (copy_expert) est supprimée.
    #
    # Sprint P2-quater — polars 1.41 a remplacé `execute_args` (list) par
    # `execute_options` (dict). On utilise la nouvelle API.
    df = pl.read_database(
        query=f"SELECT * FROM silver.{table} WHERE {date_col} < %s ORDER BY {date_col}",
        connection=get_settings().db.url,  # type: ignore[arg-type]
        execute_options={"params": [cutoff]},
    )
    df.write_parquet(local_path, compression="snappy")
    bytes_parquet = local_path.stat().st_size
    logger.info("Wrote %s (%.1f MB) — %d rows", local_path, bytes_parquet / 1e6, df.height)

    # 3) Push vers MinIO (urllib3 + AWS Sig V4 manuelle — pas de boto3)
    bucket = "lyonflow-bronze"
    key = (
        f"silver_archive/{table}/"
        f"year={cutoff.strftime('%Y')}/month={cutoff.strftime('%m')}/"
        f"{table}_{cutoff.strftime('%Y%m%d')}.parquet"
    )
    s = get_settings()
    upload_file_to_minio(
        local_path=str(local_path),
        bucket=bucket,
        key=key,
        endpoint=s.minio.endpoint,
        access_key=s.minio.root_user,
        secret_key=s.minio.root_password,
        content_type="application/octet-stream",
    )
    logger.info("Uploaded s3://%s/%s (%.1f MB)", bucket, key, bytes_parquet / 1e6)

    # 4) DELETE Postgres (libère l'espace DB)
    execute_query(
        f"DELETE FROM silver.{table} WHERE {date_col} < %s",
        (cutoff,),
    )
    logger.info("Deleted %d rows from silver.%s", n_rows, table)

    # 5) VACUUM (libère l'espace disque, hors transaction)
    with raw_connection() as conn, conn.cursor() as cur:
        # VACUUM ne peut pas tourner dans une transaction
        conn.set_isolation_level(0)  # autocommit
        cur.execute(f"VACUUM (ANALYZE) silver.{table}")
    logger.info("VACUUM silver.%s done", table)

    # 6) Cleanup local
    local_path.unlink(missing_ok=True)

    return {
        "table": table,
        "rows_archived": n_rows,
        "bytes_parquet": bytes_parquet,
        "s3_key": f"s3://{bucket}/{key}",
    }


def _archive_silver(**context) -> dict:
    """Archive les tables silver > RETENTION_DAYS vers MinIO."""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    logger.info(
        "=== Silver archive (cutoff=%s, retention=%d days) ===",
        cutoff,
        RETENTION_DAYS,
    )

    results = []
    for table, date_col in SILVER_TABLES:
        try:
            r = _archive_one_table(table, date_col, cutoff)
            results.append(r)
        except Exception as e:
            logger.exception("Failed to archive silver.%s: %s", table, e)
            results.append({"table": table, "error": str(e)})

    total_rows = sum(r.get("rows_archived", 0) for r in results)
    total_bytes = sum(r.get("bytes_parquet", 0) for r in results)
    logger.info(
        "=== DONE: %d rows archived across %d tables (%.1f MB Parquet) ===",
        total_rows,
        len(results),
        total_bytes / 1e6,
    )
    return {"results": results, "total_rows": total_rows}


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Archive silver > 30j vers MinIO (Parquet snappy) + VACUUM",
    schedule_interval="0 4 * * *",  # 04h00 quotidien
    start_date=datetime(2026, 6, 12),
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "archive", "minio", "sprint10"],
) as dag:
    archive = PythonOperator(
        task_id="archive_silver_to_minio",
        python_callable=_archive_silver,
        execution_timeout=timedelta(hours=2),
    )
