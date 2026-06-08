"""Page Pro TCL — Corrélation bus × trafic (USP technique)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_cause_analysis,
    render_correlation_matrix,
    render_line_selector,
    render_segment_table,
)

st.set_page_config(
    page_title="Corrélation bus × trafic — Pro TCL · LyonFlowFull",
    page_icon="🔗",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()

st.title("🔗 Corrélation bus × trafic routier")
render_data_status_banner()

st.caption("L'USP technique de LyonFlowFull — croise retards bus et congestion routière par segment.")

st.markdown("---")

# Sélecteur de ligne
selected_lines = render_line_selector(multiselect=True, key_suffix="corr")
target_line = selected_lines[0] if selected_lines else None

st.markdown("---")

# Matrice de corrélation
render_correlation_matrix(line_id=target_line)

st.markdown("---")

# Détail par segment
col1, col2 = st.columns([3, 2])
with col1:
    st.markdown("##### 📋 Table des segments")
    render_segment_table(line_id=target_line, height=350)
with col2:
    st.markdown("##### 🧠 Analyse causale (1er segment problématique)")
    # Trouver le 1er segment infra
    from src.data.mock.pro_tcl import SEGMENTS

    segments = SEGMENTS
    if target_line:
        segments = [s for s in segments if s["line_id"] == target_line]
    infra_seg = next((s for s in segments if s.get("diagnosis") == "infra"), None)
    if infra_seg:
        render_cause_analysis(infra_seg)
    else:
        render_cause_analysis(None)

st.caption("Corrélation bus × trafic · Données : SIRI Lite + boucles Grand Lyon")
