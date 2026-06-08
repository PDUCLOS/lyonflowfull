"""Page Élu — Synthèse exécutive (1 écran)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_bottlenecks_top, cached_elu_kpis_dict
from dashboard.components.data_status import render_data_status_banner
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
render_data_status_banner()

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

# Bouton PDF synthèse — données live (fallback mock auto via data_loader)
st.markdown("##### 📄 Génération rapport PDF")
kpis_dict = cached_elu_kpis_dict()
bottlenecks_top = cached_bottlenecks_top()
sections = {
    "title": "Synthèse exécutive — Métropole de Lyon",
    "kpis": [
        {
            "label": k.get("label", "—"),
            "value": k.get("current", 0),
            "unit": k.get("unit", ""),
            "delta_ytd": k.get("delta_ytd", 0),
        }
        for k in kpis_dict.values()
    ],
    "bottlenecks": [
        {
            "rank": b.get("rank", i + 1),
            "zone": b.get("zone", "—"),
            "lines_impacted": b.get("lines_impacted", []),
            "voyageurs_jour": b.get("voyageurs_jour", 0),
            "gain_min": b.get("gain_min", 0),
            "cout_M_euros": b.get("cout_M_euros", 0),
            "roi_mois": b.get("roi_mois", 0),
        }
        for i, b in enumerate(bottlenecks_top[:5])
    ],
    "decisions": [
        f"{b.get('zone', '—')} — {b.get('gain_min', 0)} min gagnées, "
        f"{b.get('cout_M_euros', 0)} M€, ROI {int(b.get('roi_mois', 0))} mois"
        for b in bottlenecks_top[:5]
    ],
}
render_pdf_generator(sections)

st.caption("LyonFlowFull · Synthèse exécutive · Données 12 mois glissants")
