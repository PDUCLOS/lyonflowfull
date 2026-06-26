"""Collecteur — Calendrier scolaire officiel (data.education.gouv.fr).

Module chargé de récupérer les données du calendrier scolaire (vacances).
Focalisé spécifiquement sur la Zone A (incluant l'académie de Lyon).

API utilisée : https://data.education.gouv.fr/api/records/1.0/search/...
Fréquence d'ingestion recommandée : 1 fois par mois
Volume estimé : ~50 enregistrements (périodes de vacances par zone par année)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class CalendrierScolaire(DataCollector):
    """Collecteur du calendrier scolaire français (focus Zone A / Lyon).
    
    Permet d'alimenter les modèles d'apprentissage (ML) avec les informations
    de vacances scolaires, qui impactent fortement le flux de trafic.
    """

    def __init__(self):
        """Initialise le collecteur du calendrier scolaire.
        
        Définit l'URL de base et le dataset `fr-en-calendrier-scolaire`.
        """
        super().__init__(
            source="calendrier_scolaire",
            bronze_table="calendrier_scolaire",
            timeout=30,
        )
        self.url = os.getenv(
            "EDUCATION_GOUV_API_URL",
            "https://data.education.gouv.fr/api/records/1.0/search/",
        )
        self.dataset = "fr-en-calendrier-scolaire"

    def fetch_raw(self) -> FetchResult:
        """Récupère les données brutes de vacances depuis l'API gouvernementale.
        
        Construit la requête pour filtrer uniquement la Zone A ou spécifiquement
        la région de Lyon, avec un tri décroissant sur la date de début.
        
        Returns:
            FetchResult: Conteneur standard avec les données brutes (vacances).
            
        Raises:
            CollectorError: Si l'appel API ou le décodage JSON échoue.
        """
        params = {
            "dataset": self.dataset,
            # Filtrage explicite pour l'académie concernée
            "q": "zones='Lyon' OR zones='Zone A'",
            "rows": 1000,
            "sort": "-start_date",
        }

        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération du calendrier scolaire: {e}") from e

        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
