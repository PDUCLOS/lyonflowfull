"""Ingestion package — DataCollector ABC + 8 collecteurs concrets.

Permet l'import direct des collecteurs :
    from src.ingestion import TraficGrandLyon, VelovCollector, ...
"""

from src.ingestion.base import DataCollector, FetchResult, CollectorError
from src.ingestion.trafic_grandlyon import TraficGrandLyon
from src.ingestion.velov import VelovCollector
from src.ingestion.meteo import MeteoOpenMeteo
from src.ingestion.air_quality import AirQualityOpenMeteo
from src.ingestion.chantiers import ChantiersGrandLyon
from src.ingestion.tcl_siri_lite import TclSiriLite
from src.ingestion.calendrier_scolaire import CalendrierScolaire
from src.ingestion.jours_feries import JoursFeries


# Instance de chaque collecteur pour itération facile
ALL_COLLECTORS = [
    TraficGrandLyon(),
    VelovCollector(),
    MeteoOpenMeteo(),
    AirQualityOpenMeteo(),
    ChantiersGrandLyon(),
    TclSiriLite(),
    CalendrierScolaire(),
    JoursFeries(),
]


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
    "ALL_COLLECTORS",
]
