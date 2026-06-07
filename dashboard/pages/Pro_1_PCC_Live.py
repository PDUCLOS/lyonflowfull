"""Page Pro TCL — PCC Live (vue 4 quadrants temps réel)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_alert_ticker,
    render_line_kpis,
    render_network_map,
    render_otp_heatmap_mini,
)


st.set_page_config(
    page_title="PCC Live — Pro TCL · LyonFlowFull",
    page_icon="📡",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()

# Pattern défensif : pm.is_widget_visible() pour chaque widget utilisé dans la page.
# Câblage préparé — voir dashboard/components/colors.py et config/personas.yaml.

st.title("📡 PCC Live — Réseau TCL")

# Ticker en haut
render_alert_ticker()

st.markdown("---")

# 4 quadrants
q1, q2 = st.columns(2)
with q1:
    st.markdown("##### 🗺️ NW — Carte réseau live")
    render_network_map(height=350)
with q2:
    st.markdown("##### ⚠️ NE — Alertes live (détail)")
    from src.data.mock.pro_tcl import PREDICTED_ALERTS
    severity_colors = {"critical": "#E74C3C", "warning": "#FF9800", "info": "#2196F3"}
    for alert in PREDICTED_ALERTS:
        severity = alert.get("severity", "info")
        color = severity_colors.get(severity, "#666")
        st.markdown(
            f"""
            <div style="background:#1A1D24;border-left:4px solid {color};
                        border-radius:6px;padding:0.6rem;margin:0.4rem 0;">
                <div style="font-weight:600;font-size:0.9rem;">
                    {alert.get('line_icon')} {alert.get('title')}
                </div>
                <div style="font-size:0.75rem;opacity:0.7;margin-top:0.2rem;">
                    {alert.get('description')}
                </div>
                <div style="font-size:0.75rem;color:#4CAF50;margin-top:0.3rem;">
                    💡 {alert.get('recommendation')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

q3, q4 = st.columns(2)
with q3:
    st.markdown("##### 📊 SW — Heatmap OTP")
    render_otp_heatmap_mini(height=280)
with q4:
    st.markdown("##### 🎯 SE — Top bottlenecks")
    from src.data.mock.pro_tcl import TOP_BOTTLENECKS
    for b in TOP_BOTTLENECKS[:5]:
        st.markdown(
            f"""
            <div style="background:#1A1D24;border-radius:6px;padding:0.5rem 0.7rem;
                        margin:0.3rem 0;font-size:0.85rem;">
                <div style="font-weight:600;">#{b['rank']} {b['zone']}</div>
                <div style="opacity:0.7;font-size:0.75rem;">
                    {len(b['lines'])} lignes · {b['voyageurs_jour']:,} voy/j · ROI {b['roi_mois']} mois
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("---")

# Ligne KPIs (toutes lignes)
st.markdown("##### 📈 KPIs par ligne")
render_line_kpis()

st.caption("PCC Live · Mode démonstration · Données simulées · Sprint 6+ : branchement PostgreSQL Gold")
