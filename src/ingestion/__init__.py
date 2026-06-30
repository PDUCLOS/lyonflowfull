"""Package Ingestion — Classes DataCollector de base et collecteurs concrets.

Ce module expose les collecteurs sous forme de CLASSES (et non d'instances)
afin d'éviter tout effet de bord (requêtes HTTP, lecture de variables
d'environnement) lors de l'importation. L'instanciation doit se faire
uniquement à la demande, typiquement au sein des DAGs Airflow.
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

# Liste des collecteurs à fréquence d'exécution rapide/temps-réel
REALTIME_COLLECTORS: list[type[DataCollector]] = [
    TraficGrandLyon,
    VelovCollector,
    MeteoOpenMeteo,
    AirQualityOpenMeteo,
    ChantiersGrandLyon,
    TclSiriLite,
    # (2026-06-18) — TomTomTrafficFlow réactivé.
    # Wrapper DataCollector autour de collect_lyon_tiles() et
    # save_lyon_tiles_to_bronze(). Le DAG collect_tomtom_traffic s'exécute
    # désormais toutes les 15 minutes sur 12 tuiles de Lyon.
    TomTomTrafficFlow,
]

# Liste des collecteurs à fréquence mensuelle/annuelle
MONTHLY_COLLECTORS: list[type[DataCollector]] = [
    CalendrierScolaire,
    JoursFeries,
]

# Agrégation de l'ensemble des classes de collecteurs
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
