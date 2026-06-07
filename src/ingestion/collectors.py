"""Ingestion module — facade avec tous les collecteurs.

Permet d'instancier tous les collecteurs en une ligne :
    from src.ingestion import ALL_COLLECTORS
    for c in ALL_COLLECTORS:
        c.run()
"""

from src.ingestion.base import DataCollector, FetchResult
from src.ingestion.trafic_grandlyon import TraficGrandLyon
from src.ingestion.velov import VelovCollector
from src.ingestion.meteo import MeteoOpenMeteo
from src.ingestion.air_quality import AirQualityOpenMeteo
from src.ingestion.chantiers import ChantiersGrandLyon
from src.ingestion.tcl_siri_lite import TclSiriLite
from src.ingestion.calendrier_scolaire import CalendrierScolaire
from src.ingestion.jours_feries import JoursFeries


# Tous les collecteurs instanciés
ALL_COLLECTORS: list[DataCollector] = [
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
