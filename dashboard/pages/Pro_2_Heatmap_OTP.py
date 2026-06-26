"""Page Pro TCL — Heatmap OTP."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_line_comparison,
    render_otp_filters,
    render_otp_heatmap,
)

st.set_page_config(
    page_title="Heatmap OTP — Pro TCL · LyonFlow",
    page_icon="📊",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("📊 Heatmap OTP — Ponctualité par ligne × heure")
render_data_status_banner()

# Filtres
filters = render_otp_filters()

st.markdown("---")

# Choix période
period = filters.get("period", "Aujourd'hui")
days_map = {"Aujourd'hui": 1, "7 derniers jours": 7, "30 derniers jours": 30}
days = days_map.get(period, 1)
# "Personnalisé" = aujourd'hui par défaut (futur Sprint : date_input range)
if period == "Personnalisé":
    days = 1

col_period, col_topn = st.columns([2, 1])
with col_period:
    st.markdown(f"##### Vue : {period}")
with col_topn:
    show_all = st.checkbox("Toutes les lignes", value=False, key="otp_show_all")
    if not show_all:
        top_n = st.slider("Top N pires lignes", min_value=5, max_value=50, value=20, key="otp_top_n")
    else:
        top_n = None

render_otp_heatmap(days=days, height=600 if show_all else 500, top_n=top_n)

st.markdown("---")

# Comparaison
st.markdown("##### 🔄 Comparaison lignes")
render_line_comparison()

st.caption("Heatmap OTP · Source : SIRI Lite + GTFS planifié")
