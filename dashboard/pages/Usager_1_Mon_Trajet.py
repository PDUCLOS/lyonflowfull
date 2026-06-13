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

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import render_traffic_map_compact
from dashboard.components.widgets.usager import (
    render_alternative_card,
    render_itinerary_result,
    render_recommendation_card,
    render_search_bar,
    render_steps,
    render_traffic_widget,
    render_velov_map_compact,
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
render_data_status_banner()

# Bloc de recherche
with st.container():
    search = render_search_bar()

st.markdown("---")

# Bouton de recherche
col_btn = st.columns([1, 2, 1])
with col_btn[1]:
    # Le clic set results_loaded=True, et on rerun pour afficher les résultats.
    # Avant ce fix, le bouton était mort : results_loaded passait à True au 1er
    # render et n'était jamais remis à False, donc le bloc s'affichait toujours.
    search_clicked = st.button(
        "🔍 Trouver mon trajet",
        type="primary",
        use_container_width=True,
    )

st.markdown("---")

# Résultats — la recommandation multimodale live (src.routing.pathfinder)
# necessite des coordonnees origine/destination geocodees. En attendant le
# binding complet recherche -> coords -> pathfinder, on affiche la trame demo.
st.caption(
    "ℹ️ Recommandation demo — l'integration src.routing.pathfinder requiert "
    "le geocoding origine/destination (Sprint suivant). "
    "Les options mock ne sont pas filtrées par origine/destination."
)
trip = MOCK_TRIP_RESULTS["default"]
options = trip.get("options", [])

# Init : results_loaded=False au 1er render, set True au clic bouton.
if search_clicked:
    st.session_state["results_loaded"] = True
elif "results_loaded" not in st.session_state:
    st.session_state["results_loaded"] = False

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

    # Carte trafic compacte — vitesses prédites par tronçon (Sprint 10)
    st.markdown("##### 🗺️ Carte du trafic — H+30min")
    render_traffic_map_compact(height=320, horizon_minutes=60, key_suffix="usager")  # Sprint 12+ H+1h

    # Carte Vélo'v — dispo actuelle + tooltip prédictions H+30/H+1h (Sprint 10)
    st.markdown("##### 🚲 Stations Vélo'v — dispo + prédictions")
    render_velov_map_compact(height=320, key_suffix="usager")

    st.markdown("---")

    # === ITINÉRAIRE TRAFFIC-AWARE (Sprint 6+) ===
    # Réutilise les valeurs du search_bar (cliquable) — pas de duplication d'inputs.
    st.markdown("### 🛣️ Itinéraire avec trafic")
    st.caption(
        "Calcul du chemin le plus rapide basé sur les vitesses **actuelles** "
        "par tronçon. Compare avec H+30min pour anticiper. "
        "Départ/destination repris de la barre de recherche ci-dessus."
    )

    itin_col1, itin_col2 = st.columns([3, 1])
    with itin_col1:
        st.markdown(
            f"""
            <div style="background:var(--bg-card);padding:0.8rem 1rem;border-radius:6px;
                        border-left:4px solid #4CAF50;display:flex;align-items:center;
                        gap:0.6rem;font-size:0.95rem;">
                <span style="background:#4CAF50;color:white;padding:0.2rem 0.6rem;
                             border-radius:12px;font-size:0.75rem;font-weight:600;">🟢 DÉPART</span>
                <span style="font-weight:600;">{search["origin"]}</span>
                <span style="opacity:0.4;margin:0 0.5rem;">→</span>
                <span style="background:#F44336;color:white;padding:0.2rem 0.6rem;
                             border-radius:12px;font-size:0.75rem;font-weight:600;">🔴 ARRIVÉE</span>
                <span style="font-weight:600;">{search["destination"]}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with itin_col2:
        # Sprint 12+ — focus H+1h strict (Patrice : "les autres H+1h")
        horizon = st.selectbox(
            "🕐 Trafic",
            [60],
            index=0,
            format_func=lambda x: "H+1h" if x == 60 else f"H+{x}min",
            key="itin_horizon",
        )

    if st.button(
        "🚗 Calculer l'itinéraire",
        type="primary",
        use_container_width=True,
        key="itin_calc_btn",
    ):
        render_itinerary_result(
            origin=search["origin"],
            destination=search["destination"],
            horizon_minutes=horizon,
        )

    # === QUALITÉ DE LA PRÉDICTION H+1h (Sprint 12 — feedback user) ===
    # Affiche MAE / RMSE / % fiable sur les 7 derniers jours pour que
    # l'usager sache s'il peut faire confiance à la prédiction de temps
    # de trajet. Sprint 12 — widget simple, pas de carte de caro.
    from dashboard.components.widgets.usager.prediction_quality import (
        render_prediction_quality,
    )

    with st.expander(
        "🎯 Qualité de la prédiction H+1h (est-ce que ça marche ?)",
        expanded=False,
    ):
        try:
            render_prediction_quality()
        except Exception as e:
            from dashboard.components.loading_state import data_error_to_message

            st.error(data_error_to_message(e, source="gold.predictions_vs_actuals"))

    st.markdown("---")

    # === RECOMMANDATIONS MULTIMODALES (mock) ===
    st.markdown("### ⭐ Recommandations multimodales")
    st.caption("Compare différents modes de transport (mock — Sprint 6+ : ranking traffic-aware)")

    # Filtre : ne garder que les options dont le mode est autorisé
    # (mapping option.mode → label user-facing)
    MODE_TO_LABEL = {
        "transit": "🚇 Métro",
        "tram": "🚊 Tram",
        "bus": "🚌 Bus",
        "bike": "🚲 Vélov",
        "car": "🚗 Voiture",
        "walk": "🚶 Marche",
    }
    from typing import Any, cast

    authorized = set(search.get("modes") or [])
    # Cast options explicitly since mock dict inference returns Collection[str]
    typed_options = cast(list[dict[str, Any]], options)
    filtered_options = [opt for opt in typed_options if MODE_TO_LABEL.get(str(opt.get("mode"))) in authorized]
    if not filtered_options:
        filtered_options = options  # fallback si tous filtrés
        st.caption("⚠️ Aucun mode autorisé ne correspond aux options mock — toutes affichées.")

    if filtered_options:
        # Sélecteur : l'utilisateur choisit la reco principale
        mode_choices = [
            f"{opt.get('mode_icon', '🚦')} {opt.get('mode_label', 'Mode')}" + f" — {opt.get('duration_text', '? min')}"
            for opt in filtered_options
        ]
        selected_idx = st.selectbox(
            "Mode de transport mis en avant",
            range(len(filtered_options)),
            format_func=lambda i: mode_choices[i],
            index=0,
            key="usager_reco_selector",
        )
        top = filtered_options[selected_idx]
        render_recommendation_card(top)
        why = top.get("why", [])
        if isinstance(why, str):
            why = [why]
        if why:
            render_why_explainer(why)
        if top.get("steps"):
            with st.expander("🧭 Voir les étapes détaillées", expanded=False):
                render_steps(top["steps"])

    # Alternatives (les autres options)
    if len(filtered_options) > 1:
        st.markdown("### 🔄 Autres options")
        for opt in filtered_options:
            if opt is filtered_options[selected_idx]:
                continue
            render_alternative_card(opt)

    st.markdown("---")
    st.caption("Mode démonstration · Données simulées · Sprint 6+ : branchement PostgreSQL Gold")
