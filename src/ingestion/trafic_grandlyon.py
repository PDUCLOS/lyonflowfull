"""Collecteur — Boucles magnétiques de trafic Grand Lyon (pvotrafic).

Ce module est le cœur de l'ingestion temps réel du trafic automobile.
Il interroge les capteurs (boucles) intégrés à la voirie lyonnaise.

API utilisée : https://data.grandlyon.com/geoserver/metropole-de-lyon/ows
Fréquence d'ingestion recommandée : 5 minutes (selon cycle des feux)
Volume estimé : ~1100 capteurs (x 288 cycles par jour)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class TraficGrandLyon(DataCollector):
    """Collecteur principal des données trafic routier (boucles magnétiques)."""

    def __init__(self):
        """Initialise le collecteur de trafic.

        Définit l'accès WFS au GeoServer de la Métropole, ainsi que les
        identifiants de connexion (Basic Auth).
        """
        super().__init__(
            source="pvotrafic_grandlyon",
            bronze_table="trafic_boucles",
            timeout=60,
        )

        # Endpoint validé (HTTP 200) retournant des milliers d'enregistrements.
        self.wfs_url = os.getenv(
            "GRANDLYON_WFS_URL",
            "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows",
        )
        self.typename = os.getenv(
            "GRANDLYON_TRAFFIC_TYPENAME",
            "metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic",
        )

        # Authentification Basic pour le portail Grand Lyon
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        """Exécute la requête WFS GetFeature pour récupérer l'état des boucles.

        Retourne les métriques d'occupation et de débit pour chaque capteur
        configuré dans le référentiel de la voirie.

        Returns:
            FetchResult: Un objet contenant les données GeoJSON (FeatureCollection).

        Raises:
            CollectorError: En cas d'échec de la requête HTTP ou JSON.
        """
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            # Limite généreuse pour capturer l'ensemble des capteurs
            "maxFeatures": 5000,
        }

        try:
            r = self._http_get(self.wfs_url, params=params, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération du trafic Grand Lyon: {e}") from e

        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
