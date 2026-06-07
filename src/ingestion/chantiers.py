"""Collecteur — Chantiers Grand Lyon (data.grandlyon.com).

API : https://download.data.grandlyon.com/wfs/grandlyon
Fréquence : 1x/jour
Volume : ~345 chantiers actifs
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class ChantiersGrandLyon(DataCollector):
    """Collecteur chantiers Grand Lyon."""

    def __init__(self):
        super().__init__(
            source="chantiers_grandlyon",
            bronze_table="chantiers",
            timeout=60,
        )
        self.wfs_url = os.getenv(
            "GRANDLYON_WFS_URL",
            "https://download.data.grandlyon.com/wfs/grandlyon",
        )
        self.typename = os.getenv(
            "GRANDLYON_CHANTIERS_TYPENAME",
            "adr_voie_liee.adrchantier",
        )

    def fetch_raw(self) -> FetchResult:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "maxFeatures": 2000,
        }
        try:
            r = self._http_get(self.wfs_url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch chantiers: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
