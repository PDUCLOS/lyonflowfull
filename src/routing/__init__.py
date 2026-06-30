"""Façade publique du module de routage et d'itinéraires.

Ce module regroupe la logique métier liée au calcul d'itinéraires multimodaux,
au routage via PostGIS/pgRouting, ainsi qu'au calcul de l'impact écologique.

Interface publique exposée :
- `Itinerary`, `ItinerarySegment` : Modèles de données pour décrire les trajets.
- `compute_route_pgrouting`, `compute_route_pgrouting_ksp` : Routage pur algorithmique
  (Dijkstra, Yen's K-Shortest Paths) exploitant la topologie OSM en base de données.
- `compute_itinerary`, `compute_itinerary_alternatives` : Orchestrateur multimodal
  combinant les réseaux (transports en commun, vélo, marche, voiture).
- `calculate_impact`, `get_comparison`, `recommend_mode` : Utilitaires pour le
  score écologique et la recommandation intelligente.
"""

from src.routing.eco_calculator import (
    calculate_impact,
    get_comparison,
    recommend_mode,
)
from src.routing.graph import (
    compute_route_pgrouting,
    compute_route_pgrouting_ksp,
    get_nearest_osm_node,
    get_node_speed,
)
from src.routing.pathfinder import (
    Itinerary,
    ItinerarySegment,
    compute_itinerary,
    compute_itinerary_alternatives,
)

__all__ = [
    "Itinerary",
    "ItinerarySegment",
    "calculate_impact",
    "compute_itinerary",
    "compute_itinerary_alternatives",
    "compute_route_pgrouting",
    "compute_route_pgrouting_ksp",
    "get_comparison",
    "get_nearest_osm_node",
    "get_node_speed",
    "recommend_mode",
]
