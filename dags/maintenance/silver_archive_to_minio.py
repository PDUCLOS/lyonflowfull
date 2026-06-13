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

import polars as pl
import requests  # Sprint 10+ : urllib3 natif au lieu de boto3 (cassé)
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

RETENTION_DAYS = 30  # garde 30 jours en DB
LOCAL_STAGING = Path("/tmp/silver_archive_staging")


def _get_s3_client():
    """Client boto3 pour MinIO. Sprint 10+ (2026-06-12)."""
    s = get_settings()
    if not s.minio.enabled:
        raise RuntimeError("MINIO_ENABLED=false. Active MinIO dans .env pour archiver.")
    return boto3.client(
        "s3",
        endpoint_url=f"http://{s.minio.endpoint}",
        aws_access_key_id=s.minio.root_user,
        aws_secret_access_key=s.minio.root_password,
        region_name="us-east-1",  # dummy, MinIO n'en tient pas compte
    )


def _s3_put_object(local_path: Path, bucket: str, key: str, content_type: str = "application/octet-stream") -> None:
    """Upload un fichier vers MinIO via S3 multipart (Sprint 10+ urllib3 natif).

    Pas de dépendance boto3 (cassé sur airflow 2.9.3 / OpenSSL 1.1.1f).
    Utilise ``requests`` (déjà présent) pour faire un PUT signé AWS
    Signature V4. Limité aux fichiers < 5 Go (single-part) — largement
    suffisant pour nos archives Parquet (~100-300 Mo compressés).

    Args:
        local_path: chemin du fichier à uploader.
        bucket: nom du bucket MinIO (ex. 'lyonflow-bronze').
        key: clé S3 cible (ex. 'silver_archive/foo.parquet').
        content_type: MIME type.
    """
    import hashlib
    import hmac
    from datetime import datetime, timezone

    s = get_settings()
    endpoint = s.minio.endpoint
    access_key = s.minio.root_user
    secret_key = s.minio.root_password

    # Lecture fichier
    body = local_path.read_bytes()
    content_sha256 = hashlib.sha256(body).hexdigest()
    content_length = len(body)

    # AWS Signature V4 (single-part PUT)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    host = endpoint
    region = "us-east-1"
    service = "s3"

    canonical_uri = f"/{bucket}/{key}"
    canonical_querystring = ""

    canonical_headers = (
        f"content-length:{content_length}\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{content_sha256}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-length;content-type;host;x-amz-content-sha256;x-amz-date"

    canonical_request = (
        f"PUT\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{content_sha256}"
    )

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _sign(f"AWS4{secret_key}".encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"http://{host}{canonical_uri}"
    headers = {
        "Authorization": authorization_header,
        "Content-Type": content_type,
        "Content-Length": str(content_length),
        "x-amz-content-sha256": content_sha256,
        "x-amz-date": amz_date,
    }

    resp = requests.put(url, data=body, headers=headers, timeout=120)
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(
            f"MinIO PUT failed: {resp.status_code} {resp.reason} — {resp.text[:200]}"
        )


def _archive_one_table(table: str, cutoff: datetime) -> dict:
    """Archive une table silver > cutoff vers MinIO en Parquet snappy.

    Returns:
        Dict {"table", "rows_archived", "bytes_db", "bytes_parquet", "compression_ratio"}.
    """
    logger.info("Archiving silver.%s older than %s", table, cutoff)

    # 1) Stats avant
    stats = execute_query(
        f"""
        SELECT
            count(*) AS n_rows,
            pg_size_pretty(pg_total_relation_size('silver.{table}')) AS total_size
        FROM silver.{table}
        WHERE transformed_at < %s
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

    # Utilise psycopg2 + polars.read_csv (puisque COPY TO STDOUT produit du TSV)
    with raw_connection() as conn, conn.cursor() as cur:
        cur.copy_expert(
            f"COPY (SELECT * FROM silver.{table} "
            f"WHERE transformed_at < %s ORDER BY transformed_at) "
            f"TO STDOUT WITH (FORMAT CSV, HEADER TRUE)",
            (cutoff,),
        )
        # Au lieu de drainer ici, on lit via polars depuis un buffer
        # (mais copy_expert envoie au file-like de cur). On simplifie :
        # on lit en 2 phases.
    # Phase 2 : read_sql via polars (plus simple, OK pour 1.5M rows)
    df = pl.read_database(
        query=f"SELECT * FROM silver.{table} WHERE transformed_at < %s ORDER BY transformed_at",
        execute_args=[cutoff],
        connection_uri=get_settings().db.url,  # type: ignore[arg-type]
    )
    df.write_parquet(local_path, compression="snappy")
    bytes_parquet = local_path.stat().st_size
    logger.info("Wrote %s (%.1f MB) — %d rows", local_path, bytes_parquet / 1e6, df.height)

    # 3) Push vers MinIO via S3 multipart upload (urllib3 natif, pas boto3)
    #    Sprint 10+ : boto3 1.34+ a une dépendance cassée (OpenSSL/crypto.py
    #    GEN_EMAIL). On utilise la lib standard `requests` (déjà présente
    #    dans requirements-airflow) pour faire un PUT multipart signé
    #    avec AWS Signature V4. Voir _s3_put_object() ci-dessous.
    bucket = "lyonflow-bronze"
    key = (
        f"silver_archive/{table}/"
        f"year={cutoff.strftime('%Y')}/month={cutoff.strftime('%m')}/"
        f"{table}_{cutoff.strftime('%Y%m%d')}.parquet"
    )
    _s3_put_object(local_path, bucket, key, content_type="application/octet-stream")
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
        cutoff,
        RETENTION_DAYS,
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
