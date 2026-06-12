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
    render_itinerary_result,
    render_lieux_velov_map,
    render_recommendation_card,
    render_search_bar,
    render_traffic_map_compact,
    render_velov_trip,
    render_velov_widget,
    render_weather_widget,
)
from src.data.exceptions import DashboardDataError

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

# Résultats — Sprint VPS-6 (2026-06-11) : 100% pipeline. Le pathfinding
# multimode (voiture + Vélov) lit PostgreSQL, le référentiel lieux est en
# DB, plus de mock silencieux.
st.caption(
    "ℹ️ Sprint VPS-6 : trajet Vélov + voiture calculés depuis le pipeline. "
    "Source = PostgreSQL (silver.velov_clean, gold.trafic_predictions, "
    "referentiel.lieux_lyon)."
)

# Init : results_loaded=False au 1er render, set True au clic bouton.
if search_clicked:
    st.session_state["results_loaded"] = True
elif "results_loaded" not in st.session_state:
    st.session_state["results_loaded"] = False

if st.session_state.get("results_loaded"):
    # Sprint VPS-6 (2026-06-11) : les cards Vélov et la météo sont
    # désormais **contextuelles** à la destination choisie (et non
    # plus un point fixe Part-Dieu). Calcul des stations Vélov
    # proches de la destination via referentiel.nearest_velov_stations.
    from dashboard.components.widgets.usager.velov_trip import (
        _resolve_lieu,
    )
    from src.data.exceptions import DashboardDataError
    from src.db.connection import execute_query

    # === 0. Carte globale lieux × Vélov proches (Sprint VPS-6 hotfix) ===
    # 21 lieux emblématiques reliés à leur borne Vélov la plus proche.
    # Permet à l'usager de voir d'un coup d'œil la couverture Vélov
    # de tous les lieux emblématiques (avant : aucune vue d'ensemble).
    st.markdown("##### 🗺️ Couverture Vélov des lieux emblématiques")
    st.caption(
        "21 lieux emblématiques Lyon × borne Vélov la plus proche. "
        "Lignes pointillées : vert < 100m, orange < 300m, rouge ≥ 300m. "
        "Source = referentiel.v_lieux_velov_proches (jointure haversine)."
    )
    try:
        render_lieux_velov_map(height=500)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")

    st.markdown("---")

    # Résoudre les 2 lieux pour contexte
    origin_coords = _resolve_lieu(search["origin"])
    dest_coords = _resolve_lieu(search["destination"])

    # === 1. Météo (toujours Lyon global) + Vélov destination ===
    st.markdown("##### 🌤 Conditions actuelles")
    ctx1, ctx2 = st.columns([1, 1])
    with ctx1:
        render_weather_widget()
    with ctx2:
        # Vélov proches de la destination (3 stations)
        if dest_coords is not None:
            try:
                rows = execute_query(
                    """
                    SELECT station_id, station_name, lat, lon,
                           num_bikes_available AS bikes_available,
                           num_docks_available AS stands_available,
                           distance_m, is_active
                    FROM referentiel.nearest_velov_stations(
                        %s::double precision, %s::double precision,
                        3, 0, 0
                    )
                    """,
                    (dest_coords[1], dest_coords[0]),  # lat, lon
                )
                stations_dest = [
                    {
                        "station_id": str(r["station_id"]),
                        "name": r["station_name"],
                        "lat": r["lat"], "lon": r["lon"],
                        "bikes_available": r["bikes_available"],
                        "stands_available": r["stands_available"],
                        "distance_m": int(r["distance_m"]),
                    }
                    for r in rows
                ]
                if stations_dest:
                    st.caption(f"🚲 3 stations Vélov les plus proches de **{search['destination']}** :")
                    render_velov_widget(stations=stations_dest, max_stations=3)
                else:
                    st.info(f"Aucune station Vélov proche de {search['destination']}.")
            except DashboardDataError as e:
                st.error(f"⚠️ {e}")
        else:
            render_velov_widget(max_stations=3)

    st.markdown("##### 🚦 État du trafic routier")
    render_traffic_widget()

    # Carte trafic compacte — vitesses prédites par tronçon (Sprint 10)
    st.markdown("##### 🗺️ Carte du trafic — H+30min")
    render_traffic_map_compact(height=320, horizon_minutes=60, key_suffix="usager")  # Sprint 8+ : focus H+1h

    # === 2. Trajet Vélov + marche sur carte (calculé en live) ===
    st.markdown("---")
    st.markdown("### 🚲 Trajet Vélov + marche (calculé depuis le pipeline)")
    st.caption(
        "Marche → Vélov → Marche. Stations Vélov + graphe routier Dijkstra + "
        "prédictions trafic. Source 100% pipeline (silver.velov_clean, "
        "gold.trafic_predictions, referentiel.lieux_lyon)."
    )

    if origin_coords and dest_coords:
        try:
            render_velov_trip(
                origin=search["origin"],
                destination=search["destination"],
                origin_coords=origin_coords,
                dest_coords=dest_coords,
            )
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
    else:
        st.warning(
            f"⚠️ Impossible de résoudre les adresses GPS pour le calcul : "
            f"origin={search['origin']} → {origin_coords}, "
            f"dest={search['destination']} → {dest_coords}"
        )

    st.markdown("---")

    # === 3. Carte stations Vélov globale (info, pas contextuelle) ===
    st.markdown("##### 🚲 Toutes les stations Vélo'v (info)")
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
        # Sprint 8+ (2026-06-12) — focus H+1h strict. L'utilisateur n'a
        # plus à choisir : tout est H+1h. L'option 0 (Maintenant)
        # reste supportée en interne mais n'est plus exposée.
        horizon = st.selectbox(
            "🕐 Trafic (focus H+1h)",
            [60],
            index=0,
            format_func=lambda x: f"H+{x}min",
            key="itin_horizon",
            help="Sprint 8+ : focus H+1h. Les autres horizons sont entraînés "
                 "mais l'interface n'expose que H+1h (cas d'usage principal).",
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

    st.markdown("---")

    # === ITINÉRAIRE VOITURE (déjà calculé par render_itinerary_result) ===
    # Si l'utilisateur a cliqué "Calculer l'itinéraire" plus haut, on a déjà
    # la carte voiture. Sinon on l'invite à le faire.

    st.caption(
        "LyonFlowFull · v0.6.x · Sprint VPS-6 (2026-06-11) — "
        "Zéro mock : 100% pipeline (PostgreSQL, Airflow, MLflow)"
    )
