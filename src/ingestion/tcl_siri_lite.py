"""Collecteur — Réseau TCL SIRI Lite (positions des bus et tramways).

Ingère la position en temps réel des véhicules de transport en commun 
du réseau TCL via le standard d'échange SIRI Lite.

API utilisée : https://data.grandlyon.com/siri-lite/2.0/vehicle-monitoring.json
Fréquence d'ingestion recommandée : 5 minutes
Volume estimé : ~600 véhicules en circulation aux heures de pointe
Authentification : Requiert une authentification Basic (API Grand Lyon Portal).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class TclSiriLite(DataCollector):
    """Collecteur des positions temps réel des véhicules TCL (SIRI Lite)."""

    def __init__(self):
        """Initialise le collecteur SIRI Lite.
        
        Configure l'endpoint et l'authentification HTTP Basic (obligatoire
        depuis les révisions 2025 de l'API Grand Lyon).
        """
        super().__init__(
            source="tcl_siri_lite",
            bronze_table="tcl_vehicles",
            timeout=60,
        )

        # L'endpoint v1.8 n'est plus actif. On cible la version 2.0.
        self.url = os.getenv(
            "TCL_SIRI_LITE_URL",
            "https://data.grandlyon.com/siri-lite/2.0/vehicle-monitoring.json",
        )

        # Authentification Basic pour le portail Grand Lyon
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        """Récupère la position instantanée des bus et tramways.
        
        Returns:
            FetchResult: Le document JSON SIRI Lite contenant les listes 
            de `VehicleActivity`.
            
        Raises:
            CollectorError: En cas d'erreur réseau, d'authentification ou JSON.
        """
        try:
            r = self._http_get(self.url, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération des positions SIRI Lite: {e}") from e

        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
