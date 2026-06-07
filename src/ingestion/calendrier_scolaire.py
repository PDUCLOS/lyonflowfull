"""Collecteur — Calendrier scolaire (data.education.gouv.fr).

API : https://data.education.gouv.fr/api/records/1.0/search/...
Fréquence : 1x/mois
Volume : ~50 enregistrements (vacances par zone par année)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class CalendrierScolaire(DataCollector):
    """Collecteur calendrier scolaire (vacances Zone A)."""

    def __init__(self):
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
        params = {
            "dataset": self.dataset,
            "q": "zones='Lyon' OR zones='Zone A'",
            "rows": 1000,
            "sort": "-start_date",
        }
        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch calendrier scolaire: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
