"""Collecteur — Grand Lyon boucles de trafic (pvotrafic).  # noqa: RUF002

API : https://download.data.grandlyon.com/wfs/grandlyon
Fréquence : 5 min
Volume : ~1100 capteurs × 288 cycles/jour
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class TraficGrandLyon(DataCollector):
    """Collecteur pour les boucles de trafic Grand Lyon (pvotrafic)."""

    def __init__(self):
        super().__init__(
            source="pvotrafic_grandlyon",
            bronze_table="trafic_boucles",
            timeout=60,
        )
        self.wfs_url = os.getenv(
            "GRANDLYON_WFS_URL",
            "https://download.data.grandlyon.com/wfs/grandlyon",
        )
        self.typename = os.getenv("GRANDLYON_TRAFFIC_TYPENAME", "pvo_patrimoine_voirie.pvotrafic")
        # HTTP Basic Auth Grand Lyon Portal (data.grandlyon.com)
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "maxFeatures": 5000,
        }
        try:
            r = self._http_get(self.wfs_url, params=params, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch Grand Lyon trafic: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
