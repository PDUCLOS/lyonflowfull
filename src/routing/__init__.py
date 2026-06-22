"""Routing — facade publique."""

from src.routing.eco_calculator import (
    calculate_impact,
    get_comparison,
    recommend_mode,
)
from src.routing.graph import (
    compute_route_pgrouting,
    get_nearest_osm_node,
    get_node_speed,
)
from src.routing.pathfinder import (
    Itinerary,
    ItinerarySegment,
    compute_itinerary,
)

__all__ = [
    "Itinerary",
    "ItinerarySegment",
    "calculate_impact",
    "compute_itinerary",
    "compute_route_pgrouting",
    "get_comparison",
    "get_nearest_osm_node",
    "get_node_speed",
    "recommend_mode",
]
