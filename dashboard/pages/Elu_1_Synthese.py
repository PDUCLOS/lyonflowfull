"""Page Élu — Synthèse exécutive (1 écran)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_executive_summary,
    render_kpi_cards,
    render_news_section,
    render_pdf_generator,
    render_top_decisions,
    render_trend_chart,
)
from src.data.mock.elu import BOTTLENECKS_TOP_10, KPI_12_MONTHS


st.set_page_config(
    page_title="Synthèse exécutive — Élu · LyonFlowFull",
    page_icon="📈",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()

# Pattern défensif : pm.is_widget_visible() pour chaque widget utilisé dans la page.

st.title("📈 Synthèse exécutive — Métropole de Lyon")

# Bloc narratif
render_executive_summary()

st.markdown("---")

# 5 KPI cards
render_kpi_cards()

st.markdown("---")

# 2 colonnes : tendance + décisions
col1, col2 = st.columns([3, 2])
with col1:
    st.markdown("##### 📈 Tendance — Part modale TC")
    render_trend_chart("part_modale_tc")
with col2:
    render_top_decisions(n=3)

st.markdown("---")

# Bloc À annoncer
render_news_section()

st.markdown("---")

# Bouton PDF synthèse
st.markdown("##### 📄 Génération rapport PDF")
sections = {
    "title": "Synthèse exécutive — Métropole de Lyon",
    "kpis": [
        {
            "label": k["label"],
            "value": k["current"],
            "unit": k.get("unit", ""),
            "delta_ytd": k["delta_ytd"],
        }
        for k in KPI_12_MONTHS.values()
    ],
    "bottlenecks": [
        {
            "rank": b["rank"],
            "zone": b["zone"],
            "lines_impacted": b["lines_impacted"],
            "voyageurs_jour": b["voyageurs_jour"],
            "gain_min": b["gain_min"],
            "cout_M_euros": b["cout_M_euros"],
            "roi_mois": b["roi_mois"],
        }
        for b in BOTTLENECKS_TOP_10[:5]
    ],
    "decisions": [
        f"{b['zone']} — {b['gain_min']} min gagnées, {b['cout_M_euros']} M€, ROI {int(b['roi_mois'])} mois"
        for b in BOTTLENECKS_TOP_10[:5]
    ],
}
render_pdf_generator(sections)

st.caption("LyonFlowFull · Synthèse exécutive · Données 12 mois glissants")
