"""DAG Airflow — Archive les tables silver > 30j vers MinIO (Parquet snappy).

Sprint 10+ Optimisation (2026-06-12) — ``silver.trafic_vitesse_propre``
fait 28 Go et continue à grossir (~500 Mo/jour). 80% de ces données ont
> 30 jours et ne sont plus utilisées par les modèles (fenêtre Gold :
2 jours). On les archive :

1. Export en **Parquet snappy** (compression ~10x vs raw text/JSON)
2. Push dans ``s3://lyonflow-bronze/silver_archive/<table>/YYYY/MM/``
3. DELETE Postgres (libère ~25 Go)

**Ratio attendu** : 28 Go → 2.8 Go en Parquet snappy, puis DELETE.

**Stratégie Parquet** : on dump avec COPY TO STDOUT (Postgres natif) puis
on parse avec polars qui sait lire du TSV/csv. Alternative : utiliser
``pyarrow.parquet`` directement + ``read_sql`` via SQLAlchemy. On opte
pour polars.read_database + write_parquet (vectorisé, simple).

Schedule : quotidien 04h00 (après dag_daily_speed_train 03h00).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import polars as pl
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.config import get_settings
from src.db.connection import execute_query, raw_connection

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

# Tables silver à archiver > 30 jours (rétention or / Gold)
SILVER_TABLES = [
    "trafic_vitesse_propre",  # 28 Go, 1.5M rows, top priorité
    # "tcl_vehicles_clean",  # 260 Mo, à faire Sprint 11+
    # "velov_clean",  # 282 Mo, à faire Sprint 11+
]

RETENTION_DAYS = 7  # garde 7 jours en DB (était 30 avant P2-ter, mais oldest
                   # row = 13j donc 0 archive — baisse pour activer)
LOCAL_STAGING = Path("/tmp/silver_archive_staging")


def _get_s3_client():
    """Client boto3 pour MinIO. Sprint 10+ (2026-06-12)."""
    s = get_settings()
    if not s.minio.enabled:
        raise RuntimeError(
            "MINIO_ENABLED=false. Active MinIO dans .env pour archiver."
        )
    return boto3.client(
        "s3",
        endpoint_url=f"http://{s.minio.endpoint}",
        aws_access_key_id=s.minio.root_user,
        aws_secret_access_key=s.minio.root_password,
        region_name="us-east-1",  # dummy, MinIO n'en tient pas compte
    )


def _archive_one_table(table: str, cutoff: datetime) -> dict:
    """Archive une table silver > cutoff vers MinIO en Parquet snappy.

    Returns:
        Dict {"table", "rows_archived", "bytes_db", "bytes_parquet", "compression_ratio"}.
    """
    logger.info("Archiving silver.%s older than %s", table, cutoff)

    # 1) Stats avant
    stats = execute_query(f"""
        SELECT
            count(*) AS n_rows,
            pg_size_pretty(pg_total_relation_size('silver.{table}')) AS total_size
        FROM silver.{table}
        WHERE transformed_at < %s
    """, (cutoff,))
    if not stats or stats[0]["n_rows"] == 0:
        logger.info("silver.%s — no rows to archive", table)
        return {"table": table, "rows_archived": 0}

    n_rows = int(stats[0]["n_rows"])
    logger.info("silver.%s — %s rows to archive (size: %s)",
                table, n_rows, stats[0]["total_size"])

    # 2) Export en Parquet via polars.read_database
    #    Note: on chunk par 50k rows pour éviter OOM sur gros volumes.
    LOCAL_STAGING.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_STAGING / f"{table}_{cutoff.strftime('%Y%m%d')}.parquet"

    # Lecture via polars (psycopg2 + pl.read_database_uri).
    # Le code copiait avant avec cur.copy_expert(TO STDOUT) mais
    # psycopg2 v3 exige un file-like object en argument et le résultat
    # était ignoré de toute façon (Phase 2 lit via polars). Bloc mort
    # supprimé. Sprint P2-ter (2026-06-16).
    #
    # polars 1.41+ a séparé read_database() (Connection object) et
    # read_database_uri() (string URI). On utilise la nouvelle API.
    df = pl.read_database_uri(
        query=f"SELECT * FROM silver.{table} WHERE transformed_at < %s ORDER BY transformed_at",
        uri=get_settings().db.url,  # type: ignore[arg-type]
        execute_options={"parameters": [cutoff]},
    )
    df.write_parquet(local_path, compression="snappy")
    bytes_parquet = local_path.stat().st_size
    logger.info("Wrote %s (%.1f MB) — %d rows",
                local_path, bytes_parquet / 1e6, df.height)

    # 3) Push vers MinIO
    s3 = _get_s3_client()
    bucket = "lyonflow-bronze"
    key = (
        f"silver_archive/{table}/"
        f"year={cutoff.strftime('%Y')}/month={cutoff.strftime('%m')}/"
        f"{table}_{cutoff.strftime('%Y%m%d')}.parquet"
    )
    s3.upload_file(
        str(local_path), bucket, key,
        ExtraArgs={"ContentType": "application/octet-stream"},
    )
    logger.info("Uploaded s3://%s/%s (%.1f MB)", bucket, key, bytes_parquet / 1e6)

    # 4) DELETE Postgres (libère l'espace DB)
    execute_query(
        f"DELETE FROM silver.{table} WHERE transformed_at < %s",
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
        cutoff, RETENTION_DAYS,
    )

    results = []
    for table in SILVER_TABLES:
        try:
            r = _archive_one_table(table, cutoff)
            results.append(r)
        except Exception as e:
            logger.exception("Failed to archive silver.%s: %s", table, e)
            results.append({"table": table, "error": str(e)})

    total_rows = sum(r.get("rows_archived", 0) for r in results)
    total_bytes = sum(r.get("bytes_parquet", 0) for r in results)
    logger.info(
        "=== DONE: %d rows archived across %d tables (%.1f MB Parquet) ===",
        total_rows, len(results), total_bytes / 1e6,
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
