"""Collecteur — TCL SIRI Lite (bus/tram positions temps réel).

API : https://download.data.grandlyon.com/siri-lite/...
Fréquence : 5 min
Volume : ~600 véhicules en circulation aux heures de pointe
Auth : aucune (open data)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class TclSiriLite(DataCollector):
    """Collecteur SIRI Lite TCL (positions bus/tram)."""

    def __init__(self):
        super().__init__(
            source="tcl_siri_lite",
            bronze_table="tcl_vehicles",
            timeout=60,
        )
        self.url = os.getenv(
            "TCL_SIRI_LITE_URL",
            "https://download.data.grandlyon.com/siri-lite/1.8/vehicle-monitoring.json",
        )
        # HTTP Basic Auth Grand Lyon Portal (depuis 2025 SIRI requiert auth)
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        try:
            r = self._http_get(self.url, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch SIRI Lite: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
