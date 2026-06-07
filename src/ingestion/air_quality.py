"""Collecteur — Qualité de l'air Open-Meteo Air Quality.

API : https://air-quality-api.open-meteo.com/v1/air-quality
Fréquence : 1h
Variables : PM10, PM2.5, NO2, O3, etc.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class AirQualityOpenMeteo(DataCollector):
    """Collecteur qualité de l'air Open-Meteo pour Lyon."""

    def __init__(self):
        super().__init__(
            source="air_quality_openmeteo",
            bronze_table="air_quality",
            timeout=30,
        )
        self.url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        self.lat = float(os.getenv("LYON_LATITUDE", "45.7640"))
        self.lon = float(os.getenv("LYON_LONGITUDE", "4.8357"))

    def fetch_raw(self) -> FetchResult:
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,european_aqi",
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Europe/Paris",
        }
        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch air quality: {e}") from e

        n_records = self._count_records(data)
        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(timezone.utc),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
