"""Routing — facade publique."""

from src.routing.eco_calculator import (
    calculate_impact,
    get_comparison,
    recommend_mode,
)
from src.routing.graph import (
    CACHE_TTL_SECONDS,
    build_routing_graph,
    get_nearest_node,
    get_node_speed,
)
from src.routing.pathfinder import (
    Itinerary,
    ItinerarySegment,
    compute_itinerary,
    shortest_path,
)

__all__ = [
    "CACHE_TTL_SECONDS",
    "Itinerary",
    "ItinerarySegment",
    "build_routing_graph",
    "calculate_impact",
    "compute_itinerary",
    "get_comparison",
    "get_nearest_node",
    "get_node_speed",
    "recommend_mode",
    "shortest_path",
]
