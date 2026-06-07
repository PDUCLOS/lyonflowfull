"""Collecteur — Météo Open-Meteo (forecast + archive).

API : https://api.open-meteo.com/v1/forecast
Fréquence : 1h
Variables : temperature, humidity, rain, wind, weather_code
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class MeteoOpenMeteo(DataCollector):
    """Collecteur météo Open-Meteo pour Lyon."""

    def __init__(self):
        super().__init__(
            source="meteo_openmeteo",
            bronze_table="meteo",
            timeout=30,
        )
        self.url = "https://api.open-meteo.com/v1/forecast"
        self.lat = float(os.getenv("LYON_LATITUDE", "45.7640"))
        self.lon = float(os.getenv("LYON_LONGITUDE", "4.8357"))

    def fetch_raw(self) -> FetchResult:
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Europe/Paris",
        }
        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch météo: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
