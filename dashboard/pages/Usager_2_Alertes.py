"""Page Usager — Alertes (Sprint 2 complet)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.usager import (
    render_alert_card,
    render_alert_settings,
    render_alert_timeline,
)
from src.data.mock.usager import MOCK_ALERTS

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

# Compteur d'alertes
n_alerts = len(MOCK_ALERTS)
n_critical = sum(1 for a in MOCK_ALERTS if a.get("severity") == "critical")
n_warning = sum(1 for a in MOCK_ALERTS if a.get("severity") == "warning")

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
for alert in MOCK_ALERTS:
    render_alert_card(alert)

st.markdown("---")

# Frise temporelle
st.markdown("##### 🕐 Frise chronologique")
render_alert_timeline(MOCK_ALERTS)

st.markdown("---")

# Réglages
with st.expander("⚙️ Réglages des alertes", expanded=False):
    render_alert_settings()

st.caption("LyonFlowFull · Alertes mises à jour toutes les 5 min")
