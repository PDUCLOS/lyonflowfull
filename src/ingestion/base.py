"""DataCollector — Classe abstraite pour tous les collecteurs LyonFlowFull.

Ce module définit la fondation (Template Method Pattern) de l'ensemble
des processus d'ingestion de données du projet.

Fonctionnement (Template Method) :
1. `fetch_raw()` : Récupère les données brutes depuis l'API (à implémenter par les enfants).
2. `validate()`  : Vérifie la cohérence minimale des données.
3. `save_raw()`  : Sauvegarde les données dans la couche Bronze (Base de données et Cloud).

Tous les collecteurs concrets (Trafic, Vélov, Météo, etc.) héritent de 
cette classe et implémentent uniquement la méthode `fetch_raw()`.

Mécanismes de robustesse intégrés :
- Relances automatiques (Retries Tenacity) avec délai exponentiel (Exponential Backoff).
- Journalisation (Logging) structurée et exhaustive.
- Traçabilité et idempotence lors de l'insertion en base de données.
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
    """Énumération des méthodes HTTP supportées."""
    GET = "GET"
    POST = "POST"


class CollectorError(Exception):
    """Exception personnalisée levée lorsqu'un collecteur rencontre un échec critique."""
    pass


@dataclass
class FetchResult:
    """Structure de données représentant le résultat d'une opération de collecte (fetch).
    
    Attributes:
        source (str): Identifiant de la source de données.
        fetched_at (datetime): Timestamp de la fin du téléchargement.
        raw_data (Any): Le payload de données brutes (JSON, listes, dicts).
        n_records (int): Nombre d'enregistrements (lignes/objets) comptés.
        bytes_fetched (int): Taille de la réponse HTTP en octets.
        status_code (int): Code statut HTTP retourné.
        duration_ms (int): Temps d'exécution total de la requête en millisecondes.
        error (str | None): Détails de l'erreur en cas d'échec.
        metadata (dict): Informations contextuelles additionnelles.
    """
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
    """Classe abstraite fondatrice pour tous les collecteurs de données.

    Exemple d'implémentation pour un collecteur concret :
        ```python
        class TraficGrandLyon(DataCollector):
            def __init__(self):
                super().__init__(source="pvotrafic", bronze_table="trafic_boucles")

            def fetch_raw(self) -> FetchResult:
                # Effectue l'appel API et retourne un FetchResult
                ...
        
        collector = TraficGrandLyon()
        result = collector.run()
        ```
    """

    def __init__(
        self,
        source: str,
        bronze_table: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Initialise la base du collecteur.
        
        Args:
            source (str): Nom unique identifiant la source (ex: "meteo_openmeteo").
            bronze_table (str): Nom de la table PostgreSQL cible dans le schéma "bronze".
            timeout (int): Temps d'attente maximum pour les requêtes HTTP (en secondes).
            max_retries (int): Nombre maximal de tentatives en cas d'erreur réseau.
        """
        self.source = source
        self.bronze_table = bronze_table
        self.timeout = timeout
        self.max_retries = max_retries
        self.s = get_settings()

        # Compteurs de métriques pour la supervision
        self.n_requests = 0
        self.n_failures = 0
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    # -------------------------------------------------------------------------
    # Méthodes abstraites et d'extension (À surcharger)
    # -------------------------------------------------------------------------

    @abc.abstractmethod
    def fetch_raw(self) -> FetchResult:
        """Méthode principale à implémenter : récupère les données brutes depuis l'API.
        
        Returns:
            FetchResult: Conteneur avec les données et les statistiques de la requête.
            
        Raises:
            CollectorError: En cas d'erreur bloquante.
        """
        raise NotImplementedError

    def validate(self, result: FetchResult) -> bool:
        """Valide la cohérence des données collectées.
        
        Par défaut, applique une validation très souple (il ne doit pas y avoir 
        de compte négatif). Les classes enfants peuvent la surcharger pour 
        appliquer des règles plus strictes.
        
        Args:
            result (FetchResult): Résultat de l'appel `fetch_raw`.
            
        Returns:
            bool: True si les données sont valides, False sinon.
        """
        return result.n_records >= 0

    # -------------------------------------------------------------------------
    # Orchestrateur (Template Method)
    # -------------------------------------------------------------------------

    def run(self) -> FetchResult:
        """Point d'entrée de l'exécution complète du collecteur.
        
        Séquence : Téléchargement (`fetch_raw`) -> Validation (`validate`) -> 
        Persistance (`_save_raw`).
        
        Gère également les erreurs globales et met à jour les métriques internes.

        Returns:
            FetchResult: Le résultat enrichi de l'exécution (inclut `error` si échec).
        """
        start = time.time()
        try:
            result = self.fetch_raw()
            result.duration_ms = int((time.time() - start) * 1000)

            if not self.validate(result):
                raise CollectorError(f"Échec de la validation des données pour {self.source}")

            self._save_raw(result)

            self.last_success_at = result.fetched_at
            self.n_requests += 1

            logger.info(
                "Collecteur %s SUCCÈS : %d enregistrements, %d octets, %d ms",
                self.source,
                result.n_records,
                result.bytes_fetched,
                result.duration_ms,
            )
            return result

        except Exception as e:
            self.n_failures += 1
            self.last_error = str(e)
            logger.exception("Collecteur %s ÉCHEC : %s", self.source, e)

            return FetchResult(
                source=self.source,
                fetched_at=datetime.now(UTC),
                raw_data=None,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    # -------------------------------------------------------------------------
    # Logique de persistance (Base de données et Cloud)
    # -------------------------------------------------------------------------

    def _save_raw(self, result: FetchResult) -> None:
        """Persiste les données brutes dans la couche Bronze.
        
        1. Base de données PostgreSQL (table `bronze.<table>`). Format natif JSONB.
        2. Google Drive (en guise d'archive froide/backup).
        
    Note ) : Assure l'idempotence de l'insertion. Si aucun enregistrement 
        n'a été trouvé, la persistance base de données est ignorée pour éviter 
        les erreurs de contraintes d'unicité, mais le backup GDrive est conservé.
        """
        # Si aucun enregistrement, on évite l'insertion DB (Idempotence)
        if result.n_records == 0 or not result.raw_data:
            logger.warning(
                "Collecteur %s : 0 enregistrements détectés. "
                "L'insertion dans la base de données Bronze est ignorée (Règle d'idempotence).",
                self.source
            )
            # Tentative de sauvegarde Drive pour conserver l'historique des requêtes "vides"
            try:
                raw_json = json.dumps(result.raw_data or {}, ensure_ascii=False, default=str)
                self._save_to_gdrive(result, raw_json)
            except Exception as e:
                logger.warning("Échec de la sauvegarde Google Drive de secours pour %s : %s", self.source, e)
            return

        # Requête paramétrée (anti-injection SQL via psycopg2)
        query = f"""
            INSERT INTO bronze.{self.bronze_table} (fetched_at, raw_data)
            VALUES (%s, %s)
        """  # nosec B608

        raw_json = json.dumps(result.raw_data, ensure_ascii=False, default=str)
        execute_query(query, (result.fetched_at, raw_json))

        # Backup asynchrone sur Google Drive
        try:
            self._save_to_gdrive(result, raw_json)
        except Exception as e:
            logger.warning("Échec de la sauvegarde Google Drive pour %s : %s", self.source, e)

        # Rétrocompatibilité : Backup MinIO (Déprécié)
        if self.s.minio.enabled:
            try:
                self._save_to_minio(result, raw_json)
            except Exception as e:
                logger.warning("Échec de la sauvegarde MinIO pour %s : %s", self.source, e)

    def _save_to_minio(self, result: FetchResult, raw_json: str) -> None:
        """Effectue une sauvegarde brute sur un serveur compatible S3 (MinIO).
        
        Note : Cette méthode est marquée comme DÉPRÉCIÉE au profit de Google Drive.
        Elle reste fonctionnelle si le paramètre MINIO_ENABLED=True.
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
            logger.debug("Librairie 'boto3' absente — Sauvegarde MinIO ignorée.")

    def _save_to_gdrive(self, result: FetchResult, raw_json: str) -> None:
        """Sauvegarde les données au format JSON dans Google Drive.
        
        Prérequis : Un projet GCP avec l'API Google Drive activée, et 
        le processus d'authentification OAuth 2.0 complété.
        """
        if not self.s.gdrive.enabled:
            return

        if not self.s.gdrive.folder_id_bronze_backup:
            logger.debug("Identifiant de dossier GDrive manquant (GDRIVE_FOLDER_ID_BRONZE). Skip.")
            return

        try:
            import os

            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaInMemoryUpload

            # Charge ou actualise le jeton (token) d'authentification
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
                        "Jeton Google Drive absent ou expiré (%s). "
                        "Veuillez exécuter le flux d'authentification OAuth.",
                        token_path
                    )
                    return
                # Persistance du token actualisé
                with open(token_path, "w") as f:
                    f.write(creds.to_json())

            # Préparation et envoi du fichier vers Google Drive
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
            logger.info("Upload GDrive réussi : %s → %s", file.get('name'), file.get('webViewLink'))

        except ImportError as e:
            logger.warning("Librairie Google API cliente non installée: %s", e)
        except Exception as e:
            logger.warning("Échec de la sauvegarde Google Drive: %s", e)

    # -------------------------------------------------------------------------
    # Utilitaires HTTP (Appels API)
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
        """Exécute une requête HTTP GET robuste avec gestion native des retries.
        
        Args:
            url (str): URL de l'API.
            params (dict | None): Paramètres d'URL (query string).
            headers (dict | None): En-têtes HTTP additionnels.
            auth (tuple[str, str] | None): Tuple d'authentification Basic (utilisateur, mot_de_passe).
            
        Returns:
            httpx.Response: Réponse de l'appel API.
            
        Raises:
            httpx.HTTPError: Si l'appel échoue après 3 tentatives ou si le code statut indique une erreur.
        """
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
        """Exécute une requête HTTP POST robuste avec gestion native des retries.
        
        Args:
            url (str): URL de l'API cible.
            json_data (dict | None): Dictionnaire de données (sera converti en JSON body).
            headers (dict | None): En-têtes HTTP additionnels.
            
        Returns:
            httpx.Response: La réponse HTTP de l'API.
        """
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=json_data, headers=headers or {})
            r.raise_for_status()
            return r

    def _count_records(self, data: Any) -> int:
        """Utilitaire interne pour dénombrer les enregistrements dans la réponse JSON.
        
        Parcourt de manière heuristique les structures courantes renvoyées par
        les API (listes directes, attributs 'features', 'data', 'results', etc.).
        
        Args:
            data (Any): Données parsées de l'API (dictionnaire ou liste).
            
        Returns:
            int: Le nombre estimé d'enregistrements (0 si aucun).
        """
        if isinstance(data, list):
            return len(data)

        if isinstance(data, dict):
            # Clés courantes utilisées par les API REST et GeoJSON
            for key in ("features", "data", "results", "records", "items", "stations"):
                if key in data and isinstance(data[key], list):
                    return len(data[key])

            # Format particulier de l'API Open-Meteo
            # Ex: {"hourly": {"time": [...], "temperature_2m": [...]}}
            for sub_val in data.values():
                if isinstance(sub_val, dict):
                    for list_val in sub_val.values():
                        if isinstance(list_val, list) and list_val:
                            return len(list_val)
            return 1

        return 0

    def __repr__(self) -> str:
        """Représentation sous forme de chaîne du collecteur (pour le logging)."""
        return f"<{self.__class__.__name__} source={self.source} requests={self.n_requests} failures={self.n_failures}>"
