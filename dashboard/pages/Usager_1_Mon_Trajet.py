"""Page Usager — Mon trajet (Sprint 2 complet).

Recherche d'itinéraire multimodale. Wired up with all widgets :
- search_bar (géocodage simulé)
- recommendation_card (top reco)
- alternative_card (3 alternatives)
- why_explainer (top 3 raisons)
- weather_widget, velov_widget, traffic_widget (contexte)
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.usager import (
    render_alternative_card,
    render_itinerary_result,
    render_recommendation_card,
    render_search_bar,
    render_steps,
    render_traffic_widget,
    render_velov_widget,
    render_weather_widget,
    render_why_explainer,
)
from src.data.mock.usager import MOCK_TRIP_RESULTS


st.set_page_config(
    page_title="Mon trajet — LyonFlowFull",
    page_icon="🧭",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()

# Pattern défensif : chaque widget peut vérifier sa visibilité via pm.is_widget_visible()
# (cf. dashboard/components/colors.py pour la liste des widgets par persona)
# Pour l'instant tous les widgets usager sont visibles — câblage préparé.

st.title("🧭 Mon trajet")

# Bloc de recherche
with st.container():
    search = render_search_bar()

st.markdown("---")

# Bouton de recherche
col_btn = st.columns([1, 2, 1])
with col_btn[1]:
    search_clicked = st.button(
        "🔍 Trouver mon trajet",
        type="primary",
        use_container_width=True,
    )

st.markdown("---")

# Résultats
trip = MOCK_TRIP_RESULTS["default"]
options = trip.get("options", [])

if search_clicked or not st.session_state.get("results_loaded"):
    st.session_state["results_loaded"] = True

if st.session_state.get("results_loaded"):
    # Contexte : météo + Vélov + trafic
    st.markdown("##### 🌤 Conditions actuelles")
    ctx1, ctx2 = st.columns([1, 1])
    with ctx1:
        render_weather_widget()
    with ctx2:
        render_velov_widget(max_stations=3)

    st.markdown("##### 🚦 État du trafic routier")
    render_traffic_widget()

    st.markdown("---")

    # === ITINÉRAIRE TRAFFIC-AWARE (Sprint 6+) ===
    st.markdown("### 🛣️ Itinéraire avec trafic")
    st.caption(
        "Calcul du chemin le plus rapide basé sur les vitesses **actuelles** "
        "par tronçon. Compare avec H+30min pour anticiper."
    )

    itin_col1, itin_col2, itin_col3 = st.columns([2, 2, 1])
    with itin_col1:
        st.session_state.setdefault("itin_origin", "Part-Dieu")
        origin_input = st.text_input(
            "🟢 Départ", value=st.session_state["itin_origin"],
            key="itin_origin_input",
        )
        st.session_state["itin_origin"] = origin_input
    with itin_col2:
        st.session_state.setdefault("itin_destination", "Bellecour")
        dest_input = st.text_input(
            "🔴 Arrivée", value=st.session_state["itin_destination"],
            key="itin_dest_input",
        )
        st.session_state["itin_destination"] = dest_input
    with itin_col3:
        horizon = st.selectbox(
            "🕐 Trafic",
            [0, 30, 60, 180, 360],
            index=0,
            format_func=lambda x: "Maintenant" if x == 0 else f"H+{x}min",
            key="itin_horizon",
        )

    if st.button("🚗 Calculer l'itinéraire", type="primary",
                 use_container_width=True, key="itin_calc_btn"):
        render_itinerary_result(
            origin=st.session_state["itin_origin"],
            destination=st.session_state["itin_destination"],
            horizon_minutes=horizon,
        )

    st.markdown("---")

    # === RECOMMANDATIONS MULTIMODALES (mock) ===
    st.markdown("### ⭐ Recommandations multimodales")
    st.caption("Compare différents modes de transport (mock — Sprint 6+ : ranking traffic-aware)")

    if options:
        top = options[0]
        render_recommendation_card(top)
        render_why_explainer(top.get("why", []))
        if top.get("steps"):
            with st.expander("🧭 Voir les étapes détaillées", expanded=False):
                render_steps(top["steps"])

    # Alternatives
    if len(options) > 1:
        st.markdown("### 🔄 Autres options")
        for opt in options[1:]:
            render_alternative_card(opt)

    st.markdown("---")
    st.caption(
        "Mode démonstration · Données simulées · Sprint 6+ : branchement PostgreSQL Gold"
    )
