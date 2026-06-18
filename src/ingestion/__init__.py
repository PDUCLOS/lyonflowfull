"""Ingestion package — DataCollector ABC + 8 collecteurs concrets.

Les collecteurs sont exposés en CLASSES (pas en instances) : aucune
side-effect au chargement du module (HTTP, env, etc.). Instanciation à
la demande dans les DAGs Airflow.
"""

from src.ingestion.air_quality import AirQualityOpenMeteo
from src.ingestion.base import CollectorError, DataCollector, FetchResult
from src.ingestion.calendrier_scolaire import CalendrierScolaire
from src.ingestion.chantiers import ChantiersGrandLyon
from src.ingestion.jours_feries import JoursFeries
from src.ingestion.meteo import MeteoOpenMeteo
from src.ingestion.tcl_siri_lite import TclSiriLite
from src.ingestion.tomtom_traffic import TomTomTrafficFlow
from src.ingestion.trafic_grandlyon import TraficGrandLyon
from src.ingestion.velov import VelovCollector

REALTIME_COLLECTORS: list[type[DataCollector]] = [
    TraficGrandLyon,
    VelovCollector,
    MeteoOpenMeteo,
    AirQualityOpenMeteo,
    ChantiersGrandLyon,
    TclSiriLite,
    # Sprint 13+ (2026-06-18) — TomTomTrafficFlow réactivé.
    # Wrapper DataCollector autour de collect_lyon_tiles() +
    # save_lyon_tiles_to_bronze(). DAG collect_tomtom_traffic tourne
    # désormais toutes les 15 min sur 12 tuiles Lyon.
    TomTomTrafficFlow,
]

MONTHLY_COLLECTORS: list[type[DataCollector]] = [
    CalendrierScolaire,
    JoursFeries,
]

ALL_COLLECTOR_CLASSES: list[type[DataCollector]] = REALTIME_COLLECTORS + MONTHLY_COLLECTORS


__all__ = [
    "ALL_COLLECTOR_CLASSES",
    "MONTHLY_COLLECTORS",
    "REALTIME_COLLECTORS",
    "AirQualityOpenMeteo",
    "CalendrierScolaire",
    "ChantiersGrandLyon",
    "CollectorError",
    "DataCollector",
    "FetchResult",
    "JoursFeries",
    "MeteoOpenMeteo",
    "TclSiriLite",
    "TomTomTrafficFlow",
    "TraficGrandLyon",
    "VelovCollector",
]
