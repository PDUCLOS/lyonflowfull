"""Page Élu — Génération rapport Conseil Municipal."""

from __future__ import annotations

import streamlit as st
from src.data.mock.elu import BOTTLENECKS_TOP_10, KPI_12_MONTHS

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_pdf_generator,
    render_slide_builder,
    render_template_selector,
)

st.set_page_config(
    page_title="Rapport CM — Élu · LyonFlowFull",
    page_icon="📄",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()

st.title("📄 Rapport Conseil Municipal")

st.caption("Génération de rapports PDF pour présentation au conseil municipal.")

st.markdown("---")

# Sélection du template
template = render_template_selector()

st.markdown("---")

# Slides à inclure
slides = render_slide_builder()

st.markdown("---")

# Options avancées
with st.expander("🔧 Options avancées", expanded=False):
    st.checkbox("Inclure méthodologie complète", value=True, key="pdf_opt_methodo")
    st.checkbox("Inclure sources de données", value=True, key="pdf_opt_sources")
    st.checkbox("Inclure limites et biais", value=False, key="pdf_opt_limits")
    st.checkbox("Inclure annexes techniques", value=False, key="pdf_opt_annexes")

st.markdown("---")

# Génération
st.markdown("##### 📥 Génération")
sections = {
    "title": f"{template['name']} — Métropole de Lyon",
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
        for b in BOTTLENECKS_TOP_10
    ],
    "decisions": [
        f"{b['zone']} — {b['gain_min']} min gagnées · {b['cout_M_euros']} M€ · ROI {int(b['roi_mois'])} mois"
        for b in BOTTLENECKS_TOP_10[:5]
    ],
}
render_pdf_generator(sections)

st.markdown("---")
st.caption("LyonFlowFull · Génération PDF via WeasyPrint (HTML→PDF) · Fallback reportlab si WeasyPrint indisponible")
