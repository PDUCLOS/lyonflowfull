"""Widgets Usager — module init.

Ce module expose tous les widgets du persona Usager. Permet l'import en
une ligne : `from dashboard.components.widgets import usager`.
"""

from dashboard.components.widgets.usager.alert_card import render_alert_card
from dashboard.components.widgets.usager.alert_settings import render_alert_settings
from dashboard.components.widgets.usager.alert_timeline import render_alert_timeline
from dashboard.components.widgets.usager.alternative_card import render_alternative_card
from dashboard.components.widgets.usager.favorite_list import (
    render_favorite_list,
    render_recurrent_trip_card,
)
from dashboard.components.widgets.usager.itinerary import render_itinerary_result
from dashboard.components.widgets.usager.lieux_velov_map import render_lieux_velov_map
from dashboard.components.widgets.usager.recommendation_card import (
    render_recommendation_card,
    render_steps,
)
from dashboard.components.widgets.usager.search_bar import render_search_bar
from dashboard.components.widgets.usager.traffic_widget import render_traffic_widget
from dashboard.components.widgets.usager.velov_map import (
    render_velov_map,
    render_velov_map_compact,
)
from dashboard.components.widgets.usager.velov_trip import render_velov_trip
from dashboard.components.widgets.usager.velov_widget import render_velov_widget
from dashboard.components.widgets.usager.weather_widget import render_weather_widget
from dashboard.components.widgets.usager.why_explainer import (
    render_why_explainer,
    render_why_summary,
)

__all__ = [
    "render_alert_card",
    "render_alert_settings",
    "render_alert_timeline",
    "render_alternative_card",
    "render_favorite_list",
    "render_itinerary_result",
    "render_lieux_velov_map",
    "render_recommendation_card",
    "render_recurrent_trip_card",
    "render_search_bar",
    "render_steps",
    "render_traffic_widget",
    "render_velov_map",
    "render_velov_map_compact",
    "render_velov_trip",
    "render_velov_widget",
    "render_weather_widget",
    "render_why_explainer",
    "render_why_summary",
]

_widget_map = {}
