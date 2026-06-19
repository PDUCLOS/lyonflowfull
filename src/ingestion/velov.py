"""Collecteur — Vélo'v GBFS 3.0.

API : https://velov.grandlyon.com/gbfs/gbfs.json (découverte)
      puis https://velov.grandlyon.com/gbfs/.../station_status.json
Fréquence : 5 min
Volume : ~458 stations

Sprint 10 — Grand Lyon API change (juin 2026+) :
  ``station_status.json`` ne contient plus ``name/lat/lon/address``.
  Ces champs sont dans l'endpoint séparé ``station_information.json``
  (standard GBFS). Le collecteur fetche les 2 et les fusionne dans
  ``raw_data = {"status": [...], "information": [...]}``. Le transform
  bronze→silver fait le join par ``station_id``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult


class VelovCollector(DataCollector):
    """Collecteur pour les stations Vélov' (GBFS via Grand Lyon Portal)."""

    # Endpoint de base (status seul — ne contient que les compteurs)
    STATION_STATUS_URL_DEFAULT = (
        "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/station_status.json"
    )
    # Endpoint d'information (noms, géoloc, capacity) — standard GBFS
    STATION_INFORMATION_URL_DEFAULT = (
        "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/station_information.json"
    )

    def __init__(self):
        super().__init__(
            source="velov_gbfs",
            bronze_table="velov",
            timeout=30,
        )
        # URLs (overridable via env pour les tests / changement d'API)
        self.station_status_url = os.getenv("VELOV_STATION_STATUS_URL", self.STATION_STATUS_URL_DEFAULT)
        self.station_information_url = os.getenv("VELOV_STATION_INFORMATION_URL", self.STATION_INFORMATION_URL_DEFAULT)
        # Auth Basic Grand Lyon (requise depuis 2025)
        _user = os.getenv("GRANDLYON_USERNAME") or os.getenv("API_LOGIN", "")
        _pwd = os.getenv("GRANDLYON_PASSWORD") or os.getenv("API_PASSWORD", "")
        self._auth = (_user, _pwd) if _user and _pwd else None

    def fetch_raw(self) -> FetchResult:
        """Fetch les 2 endpoints GBFS en parallèle-ish (sequential, on est à 5min).

        Returns:
            FetchResult avec raw_data = {
                "status":       [...],   # station_id, num_bikes_available, num_docks_available, ...
                "information":  [...]    # station_id, name, lat, lon, address, capacity
            }
        """
        try:
            # 1. Station status (compteurs temps réel)
            r_status = self._http_get(self.station_status_url, auth=self._auth)
            data_status = r_status.json()
        except Exception as e:
            raise CollectorError(f"Erreur fetch Vélov station_status: {e}") from e

        try:
            # 2. Station information (métadonnées stables — name, lat, lon)
            #    Tolérant : si l'endpoint tombe, on continue avec information vide
            #    (le transform fallback sur lat/lon=None et name=station_id).
            try:
                r_info = self._http_get(self.station_information_url, auth=self._auth)
                data_information = r_info.json()
            except Exception as e:
                logger_msg = f"Vélov station_information indisponible (fallback): {e}"
                # Pas critique — on stocke une liste vide, le transform survivra
                import logging

                logging.getLogger(__name__).warning(logger_msg)
                data_information = {"data": {"stations": []}}

            # Extraction des stations (format GBFS : data.stations[])
            stations_status = data_status.get("data", {}).get("stations", []) or data_status.get("stations", [])
            stations_info = data_information.get("data", {}).get("stations", []) or data_information.get("stations", [])

            # Structure unifiée — le transform fera le join
            raw_data = {
                "status": stations_status,
                "information": stations_info,
            }

            n_records = len(stations_status)

            return FetchResult(
                source=self.source,
                fetched_at=datetime.now(UTC),
                raw_data=raw_data,
                n_records=n_records,
                bytes_fetched=len(r_status.content),
                status_code=r_status.status_code,
                metadata={
                    "n_stations_status": len(stations_status),
                    "n_stations_information": len(stations_info),
                    "endpoints": ["station_status", "station_information"],
                },
            )
        except Exception as e:
            raise CollectorError(f"Erreur processing Vélov: {e}") from e
