"""DataCollector — classe abstraite pour tous les collecteurs LyonFlowFull.

Pattern Template Method :
- fetch_raw() : récupère les données brutes depuis l'API (à override)
- validate() : valide la structure (par défaut, schémas souples)
- save_raw() : persiste en Bronze (DB + MinIO)

Tous les collecteurs concrets (Trafics, Vélov, Météo, etc.) héritent
de cette classe et implémentent uniquement fetch_raw().

Robustesse :
- Tenacity retry 3x exponential
- Logging structuré (timestamp, source, status, n_records)
- Métriques Prometheus (n_requests, n_failures, last_success_at)
"""

from __future__ import annotations

import abc
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_settings
from src.db import execute_query

logger = logging.getLogger(__name__)


class HTTPMethod(StrEnum):
    GET = "GET"
    POST = "POST"


class CollectorError(Exception):
    """Erreur remontée par un collecteur."""

    pass


@dataclass
class FetchResult:
    """Résultat d'un fetch brut."""

    source: str
    fetched_at: datetime
    raw_data: Any
    n_records: int = 0
    bytes_fetched: int = 0
    status_code: int = 200
    duration_ms: int = 0
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class DataCollector(abc.ABC):
    """Classe abstraite pour tous les collecteurs.

    Usage :
        class TraficGrandLyon(DataCollector):
            def __init__(self):
                super().__init__(source="pvotrafic", bronze_table="trafic_boucles")

            def fetch_raw(self) -> FetchResult:
                # implémenter ici l'appel API
                ...

        collector = TraficGrandLyon()
        result = collector.run()
    """

    def __init__(
        self,
        source: str,
        bronze_table: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.source = source
        self.bronze_table = bronze_table
        self.timeout = timeout
        self.max_retries = max_retries
        self.s = get_settings()
        # Compteurs métriques
        self.n_requests = 0
        self.n_failures = 0
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    # -------------------------------------------------------------------------
    # À override
    # -------------------------------------------------------------------------
    @abc.abstractmethod
    def fetch_raw(self) -> FetchResult:
        """Méthode principale : récupérer les données brutes depuis l'API."""
        raise NotImplementedError

    def validate(self, result: FetchResult) -> bool:
        """Valide la structure des données. Retourne True si OK.

        Par défaut : validation souple (n_records >= 0).
        Override pour validation stricte.
        """
        return result.n_records >= 0

    # -------------------------------------------------------------------------
    # Template method
    # -------------------------------------------------------------------------
    def run(self) -> FetchResult:
        """Point d'entrée : fetch + validate + save_raw.

        Returns:
            FetchResult enrichi (avec error si KO).
        """
        start = time.time()
        try:
            result = self.fetch_raw()
            result.duration_ms = int((time.time() - start) * 1000)

            if not self.validate(result):
                raise CollectorError(f"Validation failed for {self.source}")

            self._save_raw(result)
            self.last_success_at = result.fetched_at
            self.n_requests += 1
            logger.info(
                f"Collector {self.source} OK: {result.n_records} records, "
                f"{result.bytes_fetched} bytes, {result.duration_ms}ms"
            )
            return result

        except Exception as e:
            self.n_failures += 1
            self.last_error = str(e)
            logger.exception(f"Collector {self.source} FAILED: {e}")
            return FetchResult(
                source=self.source,
                fetched_at=datetime.now(UTC),
                raw_data=None,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------
    def _save_raw(self, result: FetchResult) -> None:
        """Persiste en Bronze DB + Google Drive (optionnel).

        - DB : bronze.<table> avec fetched_at + raw_data JSONB
        - Google Drive : backup objet dans dossier partagé
        """
        # DB Bronze
        query = f"""
            INSERT INTO bronze.{self.bronze_table} (fetched_at, raw_data)
            VALUES (%s, %s)
        """  # nosec B608
        raw_json = json.dumps(result.raw_data, ensure_ascii=False, default=str)
        execute_query(query, (result.fetched_at, raw_json))

        # Google Drive backup (optionnel — ne pas faire échouer si KO)
        try:
            self._save_to_gdrive(result, raw_json)
        except Exception as e:
            logger.warning(f"GDrive backup failed for {self.source}: {e}")

        # MinIO backup (DEPRECATED, conservé si explicitement activé)
        if self.s.minio.enabled:
            try:
                self._save_to_minio(result, raw_json)
            except Exception as e:
                logger.warning(f"MinIO backup failed for {self.source}: {e}")

    def _save_to_minio(self, result: FetchResult, raw_json: str) -> None:
        """Sauvegarde dans MinIO bucket bronze (clé temporelle).

        DEPRECATED : on utilise Google Drive désormais (cf. _save_to_gdrive).
        Conservé pour compat si MinIO_ENABLED=True.
        """
        if not self.s.minio.enabled:
            return
        try:
            import boto3
            from botocore.client import Config

            s = self.s
            s3 = boto3.client(
                "s3",
                endpoint_url=s.minio.url,
                aws_access_key_id=s.minio.root_user,
                aws_secret_access_key=s.minio.root_password,
                config=Config(signature_version="s3v4"),
            )
            key = f"{self.source}/{result.fetched_at.strftime('%Y/%m/%d/%H%M%S')}_{self.source}.json"
            s3.put_object(
                Bucket=s.minio.bucket_bronze,
                Key=key,
                Body=raw_json.encode("utf-8"),
                ContentType="application/json",
                Metadata={
                    "source": self.source,
                    "n_records": str(result.n_records),
                    "fetched_at": result.fetched_at.isoformat(),
                },
            )
        except ImportError:
            logger.debug("boto3 not installed — MinIO backup skipped")

    def _save_to_gdrive(self, result: FetchResult, raw_json: str) -> None:
        """Sauvegarde l'artifact dans Google Drive (dossier partagé).

        Structure : GDRIVE_FOLDER_ID_BRONZE/<source>/<date>/<filename>.json

        Setup :
        1. Créer un projet GCP + activer Drive API
        2. OAuth 2.0 credentials → gdrive_credentials.json
        3. Premier lancement : flow OAuth → gdrive_token.json
        4. Créer un dossier Drive et noter son ID
        """
        if not self.s.gdrive.enabled:
            return
        if not self.s.gdrive.folder_id_bronze_backup:
            logger.debug("GDRIVE_FOLDER_ID_BRONZE non configuré, skip")
            return
        try:
            import os

            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaInMemoryUpload

            # Charge ou refresh le token
            creds = None
            token_path = self.s.gdrive.token_path
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(
                    token_path,
                    scopes=["https://www.googleapis.com/auth/drive.file"],
                )
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    logger.warning(
                        f"GDrive token absent ou expiré : {token_path}. Lancez le flow OAuth au premier démarrage."
                    )
                    return
                # Sauvegarde token rafraîchi
                with open(token_path, "w") as f:
                    f.write(creds.to_json())

            # Upload
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
            file_name = f"{result.fetched_at.strftime('%Y%m%d_%H%M%S')}_{self.source}.json"
            parent_id = self.s.gdrive.folder_id_bronze_backup

            file_metadata = {
                "name": file_name,
                "parents": [parent_id],
                "description": (
                    f"LyonFlowFull Bronze artifact | source={self.source} "
                    f"| n_records={result.n_records} | "
                    f"fetched_at={result.fetched_at.isoformat()}"
                ),
            }
            media = MediaInMemoryUpload(
                raw_json.encode("utf-8"),
                mimetype="application/json",
                resumable=False,
            )
            file = service.files().create(body=file_metadata, media_body=media, fields="id,name,webViewLink").execute()
            logger.info(f"GDrive upload OK: {file.get('name')} → {file.get('webViewLink')}")
        except ImportError as e:
            logger.warning(f"google-api-python-client non installé: {e}")
        except Exception as e:
            logger.warning(f"GDrive upload failed: {e}")

    # -------------------------------------------------------------------------
    # HTTP helper
    # -------------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _http_get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        auth: tuple[str, str] | None = None,
    ) -> httpx.Response:
        """GET request avec retry. `auth` = tuple (user, password) pour HTTP Basic."""
        with httpx.Client(timeout=self.timeout, auth=auth) as client:
            r = client.get(url, params=params, headers=headers or {})
            r.raise_for_status()
            return r

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _http_post(self, url: str, json_data: dict | None = None, headers: dict | None = None) -> httpx.Response:
        """POST request avec retry."""
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=json_data, headers=headers or {})
            r.raise_for_status()
            return r

    def _count_records(self, data: Any) -> int:
        """Helper : compte le nombre d'enregistrements dans une réponse API.

        Formats courants : list, dict avec 'features', 'data', 'results'.
        """
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for key in ("features", "data", "results", "records", "items", "stations"):
                if key in data and isinstance(data[key], list):
                    return len(data[key])
            return 1
        return 0

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source={self.source} requests={self.n_requests} failures={self.n_failures}>"
