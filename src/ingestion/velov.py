"""Collecteur — Vélo'v GBFS 3.0.

API : https://velov.grandlyon.com/gbfs/gbfs.json (découverte)
      puis https://velov.grandlyon.com/gbfs/.../station_status.json
Fréquence : 5 min
Volume : ~458 stations
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class VelovCollector(DataCollector):
    """Collecteur pour les stations Vélov' (GBFS)."""

    def __init__(self):
        super().__init__(
            source="velov_gbfs",
            bronze_table="velov",
            timeout=30,
        )
        self.gbfs_url = "https://velov.grandlyon.com/gbfs/gbfs.json"

    def fetch_raw(self) -> FetchResult:
        try:
            # 1. Découvrir l'URL station_status via le manifeste GBFS
            r = self._http_get(self.gbfs_url)
            manifest = r.json()

            station_status_url = None
            for feed in manifest.get("data", {}).get("fr", {}).get("feeds", []):
                if feed.get("name") == "station_status":
                    station_status_url = feed.get("url")
                    break
            if not station_status_url:
                # Fallback : essayer en anglais
                for feed in manifest.get("data", {}).get("en", {}).get("feeds", []):
                    if feed.get("name") == "station_status":
                        station_status_url = feed.get("url")
                        break

            if not station_status_url:
                raise CollectorError("station_status URL non trouvée dans manifeste GBFS")

            # 2. Fetch station_status
            r2 = self._http_get(station_status_url)
            data = r2.json()

        except Exception as e:
            raise CollectorError(f"Erreur fetch Vélov: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r2.content),
            status_code=r2.status_code,
        )
