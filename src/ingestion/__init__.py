"""Ingestion package — DataCollector ABC + 8 collecteurs concrets.

Les collecteurs sont exposés en CLASSES (pas en instances) : aucune
side-effect au chargement du module (HTTP, env, etc.). Instanciation à
la demande dans les DAGs Airflow.
"""

from src.ingestion.base import CollectorError, DataCollector, FetchResult
from src.ingestion.trafic_grandlyon import TraficGrandLyon
from src.ingestion.velov import VelovCollector
from src.ingestion.meteo import MeteoOpenMeteo
from src.ingestion.air_quality import AirQualityOpenMeteo
from src.ingestion.chantiers import ChantiersGrandLyon
from src.ingestion.tcl_siri_lite import TclSiriLite
from src.ingestion.calendrier_scolaire import CalendrierScolaire
from src.ingestion.jours_feries import JoursFeries


REALTIME_COLLECTORS: list[type[DataCollector]] = [
    TraficGrandLyon,
    VelovCollector,
    MeteoOpenMeteo,
    AirQualityOpenMeteo,
    ChantiersGrandLyon,
    TclSiriLite,
]

MONTHLY_COLLECTORS: list[type[DataCollector]] = [
    CalendrierScolaire,
    JoursFeries,
]

ALL_COLLECTOR_CLASSES: list[type[DataCollector]] = (
    REALTIME_COLLECTORS + MONTHLY_COLLECTORS
)


__all__ = [
    "DataCollector",
    "FetchResult",
    "CollectorError",
    "TraficGrandLyon",
    "VelovCollector",
    "MeteoOpenMeteo",
    "AirQualityOpenMeteo",
    "ChantiersGrandLyon",
    "TclSiriLite",
    "CalendrierScolaire",
    "JoursFeries",
    "REALTIME_COLLECTORS",
    "MONTHLY_COLLECTORS",
    "ALL_COLLECTOR_CLASSES",
]
