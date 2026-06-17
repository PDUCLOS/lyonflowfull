"""Page Usager — Alertes (Sprint 2 complet)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_recent_alerts
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.usager import (
    render_alert_card,
    render_alert_settings,
    render_alert_timeline,
)

st.set_page_config(
    page_title="Alertes — LyonFlowFull",
    page_icon="🔔",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()

st.title("🔔 Mes alertes")
render_data_status_banner()

# Charge live (DB Gold uniquement, fail loud via DashboardDataError)
alerts_df = cached_recent_alerts(hours=6, limit=30)
alerts_list = alerts_df.to_dict("records") if not alerts_df.empty else []

# Compteur d'alertes
n_alerts = len(alerts_list)
n_critical = sum(1 for a in alerts_list if a.get("severity") == "critical")
n_warning = sum(1 for a in alerts_list if a.get("severity") == "warning")

cols = st.columns(3)
with cols[0]:
    st.metric("Alertes actives", n_alerts)
with cols[1]:
    st.metric("Critiques", n_critical, delta_color="inverse")
with cols[2]:
    st.metric("Warnings", n_warning)

st.markdown("---")

# Alertes en cartes
st.markdown("##### 📋 Liste des alertes")
if not alerts_list:
    st.info("Aucune alerte active sur les 6 dernières heures.")
else:
    for alert in alerts_list:
        # Normalise les champs absents en DB (line_icon, action)
        alert.setdefault("line_icon", "⚠️")
        alert.setdefault("title", alert.get("description", "Alerte"))
        alert.setdefault("action", alert.get("action") or "—")
        render_alert_card(alert)

st.markdown("---")

# Frise temporelle
st.markdown("##### 🕐 Frise chronologique")
render_alert_timeline(alerts_list)

st.markdown("---")

# Réglages
with st.expander("⚙️ Réglages des alertes", expanded=False):
    render_alert_settings()

st.caption("LyonFlowFull · Alertes mises à jour toutes les 5 min")
