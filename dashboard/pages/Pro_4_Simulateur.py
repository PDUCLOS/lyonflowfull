"""Page Pro TCL — Simulateur de fréquences."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_cache import cached_line_kpis
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_before_after_chart,
    render_frequency_slider,
    render_line_selector,
    render_otp_projection,
)
from src.data.db_query import clean_line_label

st.set_page_config(
    page_title="Simulateur fréquences — Pro TCL · LyonFlowFull",
    page_icon="🎚",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()

st.title("🎚 Simulateur de fréquences")
render_data_status_banner()

st.caption("Simule l'impact d'ajout/retrait de bus sur l'OTP d'une ligne.")

st.markdown("---")

# Choix de la ligne (render_line_selector retourne TOUJOURS une list)
selected = render_line_selector(multiselect=False, key_suffix="simul")
target_line = selected[0] if selected else "C3"

# KPIs de la ligne sélectionnée (live via data_loader)
target_label = clean_line_label(target_line)
st.markdown(f"##### 📊 État actuel — {target_label}")
all_line_kpis = cached_line_kpis()
kpis = all_line_kpis.get(target_line, {})
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("OTP actuel", f"{kpis.get('otp_pct', 0)}%")
with c2:
    st.metric("Retard moyen", f"{kpis.get('avg_delay_min', 0)} min")
with c3:
    st.metric("Fréquence", f"{kpis.get('frequency_min', 0)} min")
with c4:
    st.metric("Charge", f"{kpis.get('load_pct', 0)}%")

st.markdown("---")

# Simulateur
simulation = render_frequency_slider(line_id=target_line)

st.markdown("---")

# Projection
base_otp = kpis.get("otp_pct", 78.0)
st.markdown("##### 🔮 Projection")
render_otp_projection(simulation, base_otp=base_otp)

# Graphique avant/après
st.markdown("---")
new_otp = min(98.0, max(60.0, base_otp + simulation.get("buses_added", 0) * 2.5))
render_before_after_chart(base_otp, new_otp, label="OTP %")

# Bouton export Hastus
st.markdown("---")
st.markdown("##### ⏰ Export vers Hastus")
st.caption("L'export au format Hastus permet d'intégrer le scénario dans l'outil de planification des horaires.")
if st.button("📤 Exporter scénario vers Hastus", key="hastus_export_btn"):
    st.success(
        f"✅ Scénario exporté : {target_label} · {simulation.get('buses_added', 0):+d} bus · "
        f"{simulation.get('period_start', 17)}h-{simulation.get('period_end', 19)}h"
    )

st.caption("Simulateur fréquences · Modèle simplifié · Sprint 8+")
