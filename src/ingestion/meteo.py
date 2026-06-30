"""Collecteur — Prévisions Météo (Open-Meteo).

Ce module ingère les prévisions et archives météorologiques pour la
région lyonnaise, qui constituent des 'features' essentielles pour
le modèle de prédiction du trafic (XGBoost / STGCN).

API utilisée : https://api.open-meteo.com/v1/forecast
Fréquence d'ingestion recommandée : 1 heure
Variables collectées : Température, humidité, précipitations, vitesse du vent,
                     et codes météorologiques (WMO).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class MeteoOpenMeteo(DataCollector):
    """Collecteur des conditions météorologiques Open-Meteo centré sur Lyon."""

    def __init__(self):
        """Initialise le collecteur météo.

        Configure l'URL de l'API et charge les coordonnées géographiques depuis
        l'environnement (par défaut, le centre de Lyon).
        """
        super().__init__(
            source="meteo_openmeteo",
            bronze_table="meteo",
            timeout=30,
        )
        self.url = "https://api.open-meteo.com/v1/forecast"
        self.lat = float(os.getenv("LYON_LATITUDE", "45.7640"))
        self.lon = float(os.getenv("LYON_LONGITUDE", "4.8357"))

    def fetch_raw(self) -> FetchResult:
        """Récupère les relevés horaires météo (1 jour passé, 2 jours futurs).

        Returns:
            FetchResult: Conteneur avec le payload brut JSON renvoyé par Open-Meteo.

        Raises:
            CollectorError: En cas d'erreur de connexion ou de format inattendu.
        """
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            # Variables météo pertinentes pour la modélisation des mobilités
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Europe/Paris",
        }

        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération de la météo: {e}") from e

        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
