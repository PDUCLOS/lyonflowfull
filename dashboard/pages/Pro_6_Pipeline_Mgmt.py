"""Page Pro TCL — Pipeline Management (DAGs + Health + Freshness)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import render_pipeline_management_page
from dashboard.components.widgets.pro_tcl.source_health_monitor import render_source_health_monitor

st.set_page_config(
    page_title="Pipeline Management — Pro TCL · LyonFlowFull",
    page_icon="🔧",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()

st.title("🔧 Pipeline Management")
render_data_status_banner()

st.caption(
    "Vue opérateur : statut DAGs Airflow · 6 health checks · fraîcheur des 8 sources Bronze. "
    "Source : Airflow REST API + PostgreSQL Gold · Sprint 8+"
)

# Sprint 16 Axe B — Monitoring multi-source (remplace les health checks séquentiels)
render_source_health_monitor()

st.markdown("---")

render_pipeline_management_page()

st.caption(
    "Pipeline Management · Pour les alertes en temps réel, configurer "
    "LYONFLOW_ALERT_WEBHOOK_URL dans .env (Slack/Discord)"
)
