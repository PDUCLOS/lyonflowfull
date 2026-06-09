"""Collecteur — Chantiers Grand Lyon (data.grandlyon.com).

API : https://download.data.grandlyon.com/wfs/grandlyon
Fréquence : 1x/jour
Volume : ~345 chantiers actifs
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class ChantiersGrandLyon(DataCollector):
    """Collecteur chantiers Grand Lyon."""

    def __init__(self):
        super().__init__(
            source="chantiers_grandlyon",
            bronze_table="chantiers",
            timeout=60,
        )
        # Geoserver Métropole — chantiers perturbants (sans auth, fonctionne)
        # download.data.grandlyon.com/wfs/grandlyon avec adr_voie_liee.adrchantier
        # retourne 404. URL ci-dessous testée HTTP 200 (~350KB GeoJSON).
        self.wfs_url = os.getenv(
            "GRANDLYON_CHANTIERS_WFS_URL",
            "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows",
        )
        self.typename = os.getenv(
            "GRANDLYON_CHANTIERS_TYPENAME",
            "metropole-de-lyon:pvo_patrimoine_voirie.pvochantierperturbant",
        )
        # HTTP Basic Auth Grand Lyon Portal
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
            "maxFeatures": 2000,
        }
        try:
            r = self._http_get(self.wfs_url, params=params, auth=self._auth)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch chantiers: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
