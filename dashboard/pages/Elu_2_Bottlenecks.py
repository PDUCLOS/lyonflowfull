"""Page Élu — Bottlenecks prioritaires.

 (2026-06-25) — Fix 9 bugs du SPEC_FIX_ELU2_BOTTLENECKS.md :
* Carte alimentée par les vraies coordonnées GPS (gold.mv_bus_traffic_spatial)
* Économie dérivée de la DB (gain = demi-retard bus, coût par diagnostic)
* ROI unifié entre ranking et calculateur
* Voyageurs estimés depuis n_observations (1 obs ≈ 36 voyageurs)
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_bottleneck_map,
    render_bottleneck_ranking,
    render_roi_calculator,
)

st.set_page_config(
    page_title="Bottlenecks prioritaires — Élu · LyonFlow",
    page_icon="🎯",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("🎯 Bottlenecks prioritaires — Investissements")
render_data_status_banner()

st.caption(
    "Classement par impact voyageurs × gain estimé × ROI. "
    "Données : gold.mv_bus_traffic_spatial (MV spatiale 0.001° ≈ 100 m, "
    "JOIN bus×trafic par zone, refresh */15 min)."
)

st.markdown("---")

# Carte
st.markdown("##### 🗺️ Carte des 10 bottlenecks")
render_bottleneck_map(height=400)

st.markdown("---")

# Tableau ranké
st.markdown("##### 📊 Classement par diagnostic + ROI")
render_bottleneck_ranking()

st.markdown("---")

# Calculateur ROI
render_roi_calculator()

st.caption(
    "LyonFlow · ROI = voyageurs × gain × valeur temps × 2 (aller-retour) × "
    "250 jours ouvrés / coût. Voyageurs estimés depuis SIRI Lite "
    "(n_obs × 36 : 1 obs ≈ 1 bus × ~80 passagers × ~45% occupation SYTRAL)."
)
