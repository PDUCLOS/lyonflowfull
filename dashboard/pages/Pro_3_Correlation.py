"""Page Pro TCL — Corrélation bus × trafic (USP technique)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_cause_analysis,
    render_coherence_scatter,
    render_correlation_matrix,
    render_line_selector,
    render_multimodal_heatmap,
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
setup_auto_refresh()

st.title("Corrélation bus × trafic routier")
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
    st.markdown("##### Table des segments")
    render_segment_table(line_id=target_line, height=350)
with col2:
    st.markdown("##### Analyse causale (1er segment problématique)")
    from dashboard.components.data_cache import cached_infra_bottlenecks

    bn_df = cached_infra_bottlenecks(top=500)
    if not bn_df.empty:
        if target_line:
            bn_df = bn_df[bn_df["line_ref"] == target_line]
        infra_rows = bn_df[bn_df["diagnosis"] == "infra"] if "diagnosis" in bn_df.columns else bn_df.iloc[:0]
        if not infra_rows.empty:
            row = infra_rows.iloc[0]
            delay_s = row.get("bus_delay_seconds", 0) or 0
            render_cause_analysis({
                "line_id": row.get("line_ref", "?"),
                "name": row.get("segment_id", "—"),
                "bus_state": "delayed" if delay_s > 120 else "on_time",
                "traffic_state": "jammed" if (row.get("traffic_speed_kmh", 50) or 50) < 25 else "fluid",
                "diagnosis": row.get("diagnosis", "ok"),
                "delay_min": round(delay_s / 60, 1),
            })
        else:
            render_cause_analysis(None)
    else:
        render_cause_analysis(None)

st.markdown("---")

# Sprint 13+ (2026-06-18) — Cross-validation TomTom ↔ Grand Lyon
# Détecte les capteurs HS (delta > 20 km/h vs source indépendante GPS flottes).
st.markdown("##### Cohérence TomTom × Grand Lyon (cross-validation sources)")
render_coherence_scatter()

st.markdown("---")

# Sprint 15+ (2026-06-19) — Axe 1 du SPEC_OPTIMISATION_INTERDEPENDANCES
# Grille multimodale 0.01° (trafic + TCL + Vélov + météo fusionnés) — carte
# chaleur avec score 0-10 et diagnostic dominant par cellule. Vue
# gold.mv_multimodal_grid (migration 17), refresh DAG */10 min.
st.markdown("##### Vue multimodale grille 0.01° (trafic + TCL + Vélov + météo)")
render_multimodal_heatmap()

st.caption(
    "Corrélation bus × trafic · Données : SIRI Lite + boucles Grand Lyon. "
    "Cohérence TomTom × GL · Données : TomTom Flow (DAG collect_tomtom_traffic */15) + "
    "jointure spatiale gold.channels_ref < 200 m (PostGIS ST_DWithin). "
    "Grille multimodale · Données : fusion gold.traffic_features_live × "
    "gold.tcl_vehicle_realtime × silver.velov_clean × silver.meteo_hourly "
    "sur gold.mv_multimodal_grid (refresh */10)."
)
