"""Collecteur — Jours fériés (calendrier.api.gouv.fr).

API : https://calendrier.api.gouv.fr/jours-feries/
Fréquence : 1x/an
Volume : ~11 jours/an
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class JoursFeries(DataCollector):
    """Collecteur jours fériés France."""

    def __init__(self):
        super().__init__(
            source="jours_feries",
            bronze_table="jours_feries",
            timeout=30,
        )
        self.url = os.getenv(
            "JOURS_FERIES_URL",
            "https://calendrier.api.gouv.fr/jours-feries/",
        )

    def fetch_raw(self) -> FetchResult:
        # L'API retourne les jours fériés par année (métropole par défaut)
        # On fetch l'année courante + N+1
        annees = [datetime.now().year, datetime.now().year + 1]
        all_data = {}
        for annee in annees:
            try:
                r = self._http_get(f"{self.url}metropole/{annee}.json")
                all_data[annee] = r.json()
            except Exception as e:
                logger.warning(f"Erreur fetch jours fériés {annee}: {e}")
                continue

        if not all_data:
            raise CollectorError("Aucune donnée jours fériés collectée")

        n_records = sum(len(v) for v in all_data.values())
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=all_data,
            n_records=n_records,
            status_code=200,
        )
