"""Page Pro TCL — PCC Live (vue 4 quadrants temps réel)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_alert_ticker,
    render_line_kpis,
    render_network_map,
    render_otp_heatmap_mini,
    render_traffic_map,
)

st.set_page_config(
    page_title="PCC Live — Pro TCL · LyonFlowFull",
    page_icon="📡",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()

# Pattern défensif : pm.is_widget_visible() pour chaque widget utilisé dans la page.
# Câblage préparé — voir dashboard/components/colors.py et config/personas.yaml.

st.title("📡 PCC Live — Réseau TCL")
render_data_status_banner()

# Ticker en haut
render_alert_ticker()

st.markdown("---")

# 4 quadrants
q1, q2 = st.columns(2)
with q1:
    st.markdown("##### 🗺️ NW — Carte live")
    # Sprint 15+ audit (P0-2) : st.tabs ne diffère PAS le calcul — les 2 maps
    # pydeck s'exécutaient en séquentiel à chaque auto-refresh 30s. Switch
    # vers st.radio → 1 seul rendu par cycle, gain ~50% sur ce quadrant.
    map_choice = st.radio(
        "Carte",
        ["🚌 Bus GPS", "🚗 Charge trafic"],
        horizontal=True,
        key="pro1_map_choice",
        label_visibility="collapsed",
    )
    if map_choice == "🚌 Bus GPS":
        render_network_map(height=320)
    else:
        render_traffic_map(
            height=320,
            horizon_default=60,  # Sprint 8+ : focus H+1h
            show_horizon_selector=True,
            show_legend=True,
            show_caption=False,
            key_suffix="pro1",
        )
with q2:
    st.markdown("##### ⚠️ NE — Alertes live (détail)")
    from dashboard.components.colors import STATUS_COLORS
    from dashboard.components.data_cache import cached_recent_alerts

    alerts_df = cached_recent_alerts(hours=24, limit=10)
    if alerts_df.empty:
        st.info("Aucun chantier actif ni alerte en cours.")
    else:
        for _, alert in alerts_df.iterrows():
            severity = alert.get("severity", "info")
            color = STATUS_COLORS.get(severity, STATUS_COLORS["info"])
            line_ref = alert.get("line_ref", "—")
            st.markdown(
                f"""
                <div class="lyonflow-card" style="border-left-color:{color};padding:0.6rem;">
                    <div style="font-weight:600;font-size:0.9rem;">
                        🚦 [{line_ref}] {alert.get("title", "Alerte")}
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.7;margin-top:0.2rem;">
                        {alert.get("description", "")}
                    </div>
                    <div class="lyf-sublabel" style="color:var(--status-ok);margin-top:0.3rem;">
                        💡 {alert.get("action", "—")}
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
    from dashboard.components.data_cache import cached_bottlenecks_top

    top_bottlenecks = cached_bottlenecks_top()
    if not top_bottlenecks:
        st.info("Aucun bottleneck détecté actuellement.")
    else:
        for i, b in enumerate(top_bottlenecks[:5]):
            rank = b.get("rank", i + 1)
            zone = b.get("zone", "—")
            lines = b.get("lines") or b.get("lines_impacted") or []
            voy = b.get("voyageurs_jour", 0)
            roi = b.get("roi_mois", 0)
            st.markdown(
                f"""
                <div class="lyonflow-card-flat lyf-detail" style="padding:0.5rem 0.7rem;">
                    <div style="font-weight:600;">#{rank} {zone}</div>
                    <div class="lyf-sublabel" style="opacity:0.7;">
                        {len(lines)} lignes · {voy:,} voy/j · ROI {roi} mois
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("---")

# Ligne KPIs (toutes lignes)
st.markdown("##### 📈 KPIs par ligne")
render_line_kpis()

st.caption("PCC Live · Source : PostgreSQL Gold · Sprint 8+")
