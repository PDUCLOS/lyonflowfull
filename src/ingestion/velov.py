"""Collecteur — Vélo'v GBFS 3.0.

API : https://velov.grandlyon.com/gbfs/gbfs.json (découverte)
      puis https://velov.grandlyon.com/gbfs/.../station_status.json
Fréquence : 5 min
Volume : ~458 stations
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class VelovCollector(DataCollector):
    """Collecteur pour les stations Vélov' (GBFS via Grand Lyon Portal)."""

    def __init__(self):
        super().__init__(
            source="velov_gbfs",
            bronze_table="velov",
            timeout=30,
        )
        # URL directe Grand Lyon Portal (HTTP Basic auth requise depuis 2025)
        # L'ancien manifeste gbfs.json sur velov.grandlyon.com retourne du HTML.
        self.station_status_url = os.getenv(
            "VELOV_STATION_STATUS_URL",
            "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/station_status.json",
        )
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        try:
            r = self._http_get(self.station_status_url, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch Vélov: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
