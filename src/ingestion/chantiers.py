"""Collecteur — Chantiers Métropole du Grand Lyon (data.grandlyon.com).

Ce module ingère les données des chantiers perturbants sur la voirie du
Grand Lyon, informations cruciales pour le calcul des itinéraires et
la prédiction des embouteillages.

API utilisée : https://download.data.grandlyon.com/wfs/grandlyon (GeoServer WFS)
Fréquence d'ingestion recommandée : 1 fois par jour
Volume estimé : ~345 chantiers actifs (GeoJSON de ~350KB)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class ChantiersGrandLyon(DataCollector):
    """Collecteur des chantiers et perturbations voirie du Grand Lyon."""

    def __init__(self):
        """Initialise le collecteur de chantiers.

        Configure le point d'accès WFS (Web Feature Service) du GeoServer
        de la Métropole de Lyon. Gère également l'authentification HTTP Basic
        si les identifiants sont fournis en variables d'environnement.
        """
        super().__init__(
            source="chantiers_grandlyon",
            bronze_table="chantiers",
            timeout=60,
        )

        # Point d'accès WFS GeoServer pour les chantiers perturbants.
        # Testé fonctionnel sans authentification (retourne HTTP 200).
        self.wfs_url = os.getenv(
            "GRANDLYON_CHANTIERS_WFS_URL",
            "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows",
        )
        self.typename = os.getenv(
            "GRANDLYON_CHANTIERS_TYPENAME",
            "metropole-de-lyon:pvo_patrimoine_voirie.pvochantierperturbant",
        )

        # Configuration de l'authentification Basic (optionnelle)
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        """Récupère les objets cartographiques (FeatureCollection) des chantiers.

        Exécute une requête standard OGC WFS `GetFeature` et demande un format
        de sortie JSON (GeoJSON), limité à 2000 éléments.

        Returns:
            FetchResult: Conteneur des données GeoJSON brutes et des métadonnées.

        Raises:
            CollectorError: Si le serveur WFS retourne une erreur ou est injoignable.
        """
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",  # Conversion automatique en WGS84
            "maxFeatures": 2000,
        }

        try:
            r = self._http_get(self.wfs_url, params=params, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération des chantiers: {e}") from e

        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
