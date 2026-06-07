"""Page Élu — Bottlenecks prioritaires."""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_bottleneck_map,
    render_bottleneck_ranking,
    render_roi_calculator,
)

st.set_page_config(
    page_title="Bottlenecks prioritaires — Élu · LyonFlowFull",
    page_icon="🎯",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()

st.title("🎯 Bottlenecks prioritaires — Investissements")

st.caption(
    "Classement par impact voyageurs × gain estimé × ROI. Critères SYTRAL : accessibilité, ponctualité, report modal."
)

st.markdown("---")

# Carte
st.markdown("##### 🗺️ Carte des 10 bottlenecks")
render_bottleneck_map(height=400)

st.markdown("---")

# Tableau ranké
st.markdown("##### 📊 Classement par ROI")
render_bottleneck_ranking()

st.markdown("---")

# Calculateur ROI
render_roi_calculator()

st.caption("LyonFlowFull · ROI calculé : voyageurs × gain × valeur temps × 250 jours / coût")
