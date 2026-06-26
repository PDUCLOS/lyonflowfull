"""Collecteur — Qualité de l'air (Open-Meteo Air Quality).

Ce module est responsable de la récupération des données de qualité de l'air
pour la région lyonnaise via l'API Open-Meteo.

API utilisée : https://air-quality-api.open-meteo.com/v1/air-quality
Fréquence d'ingestion recommandée : 1 heure
Variables collectées : PM10, PM2.5, NO2 (dioxyde d'azote), CO (monoxyde de carbone),
                     O3 (ozone), et AQI européen (European Air Quality Index).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class AirQualityOpenMeteo(DataCollector):
    """Collecteur de qualité de l'air Open-Meteo centré sur Lyon.
    
    Hérite de la classe `DataCollector` pour bénéficier du cadre standardisé
    d'ingestion (gestion des retries, insertions Bronze, etc.).
    """

    def __init__(self):
        """Initialise le collecteur de la qualité de l'air.
        
        Configure l'URL de l'API, la table cible (`air_quality`) et les 
        coordonnées géographiques par défaut de Lyon (ou celles définies
        via les variables d'environnement `LYON_LATITUDE` / `LYON_LONGITUDE`).
        """
        super().__init__(
            source="air_quality_openmeteo",
            bronze_table="air_quality",
            timeout=30,
        )
        self.url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        self.lat = float(os.getenv("LYON_LATITUDE", "45.7640"))
        self.lon = float(os.getenv("LYON_LONGITUDE", "4.8357"))

    def fetch_raw(self) -> FetchResult:
        """Récupère les données brutes depuis l'API Open-Meteo.
        
        Effectue une requête HTTP GET pour récupérer les relevés horaires des
        principaux polluants atmosphériques (passés et prévisionnels).
        
        Returns:
            FetchResult: Conteneur englobant les données brutes, les métadonnées
            de l'appel, et le statut.
            
        Raises:
            CollectorError: Si une erreur réseau ou d'API survient lors du fetch.
        """
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            # Extraction des principaux polluants et de l'indice de qualité d'air
            "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,european_aqi",
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Europe/Paris",
        }

        try:
            # Utilise _http_get() fourni par la classe de base DataCollector
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération de la qualité de l'air: {e}") from e

        # Décompte le nombre total de relevés/lignes dans la réponse JSON
        n_records = self._count_records(data)

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=n_records,
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )
