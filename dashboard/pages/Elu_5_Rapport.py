"""Page Élu — Génération rapport Conseil Municipal."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_cache import cached_bottlenecks_top, cached_elu_kpis_dict
from dashboard.components.data_status import render_data_status_banner
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
setup_auto_refresh()

st.title("📄 Rapport Conseil Municipal")
render_data_status_banner()

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
    # IMPORTANT: assigner les retours des checkboxes (sinon StreamlitAPIException)
    # + propager dans sections (sinon options cosmétiques, choix jetés)
    include_methodo = st.checkbox("Inclure méthodologie complète", value=True, key="pdf_opt_methodo")
    include_sources = st.checkbox("Inclure sources de données", value=True, key="pdf_opt_sources")
    include_limits = st.checkbox("Inclure limites et biais", value=False, key="pdf_opt_limits")
    include_annexes = st.checkbox("Inclure annexes techniques", value=False, key="pdf_opt_annexes")

st.markdown("---")

# Génération — sources live via data_loader (Sprint 8 — fail loud si DB indispo)
kpis_dict = cached_elu_kpis_dict()
bottlenecks_top = cached_bottlenecks_top()
st.markdown("##### 📥 Génération")
sections = {
    "title": f"{template['name']} — Métropole de Lyon",
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
        for i, b in enumerate(bottlenecks_top)
    ],
    "decisions": [
        f"{b.get('zone', '—')} — {b.get('gain_min', 0)} min gagnées · "
        f"{b.get('cout_M_euros', 0)} M€ · ROI {int(b.get('roi_mois', 0) or 0)} mois"
        for b in bottlenecks_top[:5]
    ],
    "include_methodo": include_methodo,
    "include_sources": include_sources,
    "include_limits": include_limits,
    "include_annexes": include_annexes,
    "slides": slides,  # propagé au PDF (sinon jeté)
    "template_name": template.get("name", "—") if template else "—",
}
render_pdf_generator(sections)

st.markdown("---")
st.caption("LyonFlowFull · Génération PDF via WeasyPrint (HTML→PDF) · Fallback reportlab si WeasyPrint indisponible")
