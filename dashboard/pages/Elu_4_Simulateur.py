"""Page Élu — Simulateur d'aménagement."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_cost_estimate,
    render_impact_projection,
    render_map_painter,
)

st.set_page_config(
    page_title="Simulateur aménagement — Élu · LyonFlow",
    page_icon="✏️",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("Simulateur d'aménagement")
render_data_status_banner()

st.caption(
    "Sélectionnez une zone sur la carte pour projeter l'impact d'un "
    "nouvel aménagement (couloir bus, piste cyclable, réaménagement). "
    "Composant deck.gl+MapboxDraw interactif en développement."
)

st.markdown("---")

# Carte
selected = render_map_painter(height=400)
zone = selected.get("selected_zone")

st.markdown("---")

# Projection + coût
if zone:
    col1, col2 = st.columns(2)
    with col1:
        render_impact_projection(zone)
    with col2:
        render_cost_estimate(zone)

st.caption("LyonFlow · Sprint 5 ajoutera component React deck.gl + MapboxDraw")
