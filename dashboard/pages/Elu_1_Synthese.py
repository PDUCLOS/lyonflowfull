"""Page Élu — Synthèse exécutive (1 écran)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_cache import cached_bottlenecks_top, cached_elu_kpis_dict
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.common import render_traffic_map_compact
from dashboard.components.widgets.elu import (
    render_executive_summary,
    render_kpi_cards,
    render_network_health_gauge,
    render_news_section,
    render_pdf_generator,
    render_top_decisions,
    render_trend_chart,
)
from dashboard.components.widgets.elu.data_quality_badge import render_data_quality_badge
from dashboard.components.widgets.elu.data_quality_detail import render_data_quality_detail
from dashboard.components.widgets.elu.drift_status_badge import render_drift_status_badge

st.set_page_config(
    page_title="Synthèse exécutive — Élu · LyonFlowFull",
    page_icon="📈",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

# Pattern défensif : pm.is_widget_visible() pour chaque widget utilisé dans la page.

st.title("📈 Synthèse exécutive — Métropole de Lyon")
render_data_status_banner()

# Bandeau santé réseau (Axe 5, Sprint 15+ — migration 019)
# Jauge synthétique 0-100 + 4 sous-jauges. Fail loud si DB indispo.
render_network_health_gauge()

# Sprint 16 Axe A — Drift status badge (bandeau compact 1 ligne).
# Affiche modèle stable / attention / drift détecté selon MAE 24h + drift Evidently.
render_drift_status_badge()

# Sprint 16 Axe B — Data quality badge (bandeau compact 1 ligne).
# Affiche nombre de sources healthy / stale / dead + score global.
render_data_quality_badge()

st.markdown("---")

# Sprint 17 Axe 6 — Data quality detail (drill-down data bounds).
# Affiche le détail des checks qualité (plages speed, null ratio, doublons,
# volume) sur gold.traffic_features_live, gold.tcl_vehicle_realtime,
# silver.velov_clean. Vue append-only gold.data_quality_log (migration 025).
# Complémentaire de data_quality_badge (liveness des sources vs qualité
# des valeurs). Coût léger (1 query, cache 300s), pas de button-gate.
render_data_quality_detail()

st.markdown("---")

# Bloc narratif
render_executive_summary()

st.markdown("---")

# 5 KPI cards
render_kpi_cards()

st.markdown("---")

# Carte charge trafic — synthèse exécutive (Sprint 10)
st.markdown("##### 🗺️ Charge du trafic — projection H+1h")
render_traffic_map_compact(height=340, horizon_minutes=60, key_suffix="elu")

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

# Bouton PDF synthèse — données live via data_loader (Sprint 8 — fail loud si DB indispo)
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
            "lines_impacted": b.get("lines_impacted", []) or [],
            "voyageurs_jour": b.get("voyageurs_jour", 0) or 0,
            "gain_min": b.get("gain_min", 0) or 0,
            "cout_M_euros": b.get("cout_M_euros", 0) or 0,
            "roi_mois": b.get("roi_mois", 0) or 0,
        }
        for i, b in enumerate(bottlenecks_top[:5])
    ],
    "decisions": [
        f"{b.get('zone', '—')} — {b.get('gain_min', 0)} min gagnées, "
        f"{b.get('cout_M_euros', 0)} M€, ROI {int(b.get('roi_mois', 0) or 0)} mois"
        for b in bottlenecks_top[:5]
    ],
}
render_pdf_generator(sections)

st.caption("LyonFlowFull · Synthèse exécutive · Données 12 mois glissants")
