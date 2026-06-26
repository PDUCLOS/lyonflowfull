"""Push fichier vers MinIO via urllib3 + AWS Signature V4 manuelle.

Sprint 12+ — boto3 cassé sur airflow:2.9.3 (conflit pyOpenSSL /
cryptography : ``AttributeError: module 'lib' has no attribute
'GEN_EMAIL'``). On évite boto3 et on signe les requêtes à la main
(50 lignes de code, pas de magie).

Usage::

    from src.minio_s3v4_upload import upload_file_to_minio
    upload_file_to_minio(
        local_path="/tmp/file.parquet",
        bucket="lyonflow-bronze",
        key="silver_archive/foo/2026/06/foo.parquet",
        endpoint="minio:9000",
        access_key="minio",
        secret_key="minio123",
    )

Le ``endpoint`` est le hostname:port (pas d'URL http:// devant, on
l'ajoute en interne).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
from pathlib import Path
from urllib.parse import quote

import requests  # utilise urllib3 sous le capot

logger = logging.getLogger(__name__)

# S3 Sig V4 — algorithme de signature (cf. AWS docs)
_ALGORITHM = "AWS4-HMAC-SHA256"


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    """Dérive la clé de signature Sig V4."""
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def upload_file_to_minio(
    local_path: str,
    bucket: str,
    key: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    content_type: str = "application/octet-stream",
    region: str = "us-east-1",
) -> str:
    """Upload un fichier vers MinIO avec AWS Sig V4 manuelle.

    Args:
        local_path: chemin local du fichier à uploader.
        bucket: nom du bucket MinIO.
        key: clé S3 (chemin dans le bucket).
        endpoint: ``hostname:port`` du MinIO (ex: ``minio:9000``).
        access_key: minio root user.
        secret_key: minio root password.
        content_type: MIME type, défaut ``application/octet-stream``.
        region: région S3, défaut ``us-east-1`` (MinIO ignore).

    Returns:
        L'URL finale ``s3://bucket/key``.

    Raises:
        RuntimeError: si l'upload échoue (HTTP non-2xx, réseau down, etc.).
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier source introuvable : {local_path}")

    file_size = path.stat().st_size
    file_bytes = path.read_bytes()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # URL : on force http:// (MinIO par défaut), pas https
    endpoint_clean = endpoint.replace("http://", "").replace("https://", "")
    url = f"http://{endpoint_clean}/{bucket}/{quote(key, safe='/')}"

    # Date / timestamps
    now = datetime.datetime.now(datetime.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Canonical request
    canonical_uri = f"/{bucket}/{quote(key, safe='/')}"
    canonical_querystring = ""
    canonical_headers = (
        f"content-length:{file_size}\n"
        f"content-type:{content_type}\n"
        f"host:{endpoint_clean}\n"
        f"x-amz-content-sha256:{file_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-length;content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = (
        f"PUT\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{file_hash}"
    )

    # String to sign
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"{_ALGORITHM}\n{amz_date}\n{credential_scope}\n{hashed_canonical}"

    # Signature
    signing_key = _get_signature_key(secret_key, date_stamp, region, "s3")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Authorization header
    authorization = (
        f"{_ALGORITHM} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "Content-Length": str(file_size),
        "Host": endpoint_clean,
        "x-amz-content-sha256": file_hash,
        "x-amz-date": amz_date,
        "Authorization": authorization,
    }

    # PUT
    try:
        resp = requests.put(url, data=file_bytes, headers=headers, timeout=300)
    except requests.RequestException as e:
        raise RuntimeError(f"MinIO upload failed (network): {e}. URL: {url}") from e

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"MinIO upload failed: HTTP {resp.status_code} — {resp.text[:500]}. URL: {url}")

    s3_uri = f"s3://{bucket}/{key}"
    logger.info(
        "MinIO upload OK : %s (%.1f MB, sha256=%s)",
        s3_uri,
        file_size / 1e6,
        file_hash[:12],
    )
    return s3_uri
