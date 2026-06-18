"""Page Usager — Mon trajet.

Recherche d'itineraire multimodale Lyon. Widgets :
- search_bar (selectbox lieux referentiel)
- weather_widget, velov_widget, traffic_widget (contexte)
- velov_trip (trajet Velov calcule live)
- itinerary_result (trajet voiture Dijkstra)
- traffic_map_compact, velov_map_compact (cartes)
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.common import render_traffic_map_compact
from dashboard.components.widgets.usager import (
    render_itinerary_result,
    render_lieux_velov_map,
    render_search_bar,
    render_traffic_widget,
    render_velov_map_compact,
    render_velov_trip,
    render_velov_widget,
    render_weather_widget,
)
from src.config import get_settings
from src.data.exceptions import DashboardDataError

st.set_page_config(
    page_title="Mon trajet — LyonFlowFull",
    page_icon="🧭",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()

st.title("🧭 Mon trajet")
render_data_status_banner()

# ── Recherche ────────────────────────────────────────────────────────────────
with st.container():
    search = render_search_bar()

st.markdown("---")

col_btn = st.columns([1, 2, 1])
with col_btn[1]:
    search_clicked = st.button(
        "🔍 Trouver mon trajet",
        type="primary",
        use_container_width=True,
    )

st.markdown("---")

if search_clicked:
    st.session_state["results_loaded"] = True
elif "results_loaded" not in st.session_state:
    st.session_state["results_loaded"] = False

if st.session_state.get("results_loaded"):
    from dashboard.components.widgets.usager.velov_trip import _resolve_lieu
    from src.data.data_loader import load_nearest_velov_stations

    origin_coords = _resolve_lieu(search["origin"])
    dest_coords = _resolve_lieu(search["destination"])

    # ── Contexte : météo + Vélov destination ─────────────────────────────
    st.markdown("##### 🌤 Conditions actuelles")
    ctx1, ctx2 = st.columns(2)
    with ctx1:
        render_weather_widget()
    with ctx2:
        if dest_coords is not None:
            try:
                stations_dest = load_nearest_velov_stations(
                    lat=dest_coords[1], lon=dest_coords[0], k=3,
                )
                if stations_dest:
                    st.caption(f"🚲 Stations Vélov proches de **{search['destination']}** :")
                    render_velov_widget(stations=stations_dest, max_stations=3)
                else:
                    st.info(f"Aucune station Vélov proche de {search['destination']}.")
            except DashboardDataError as e:
                st.error(f"⚠️ {e}")
        else:
            render_velov_widget(max_stations=3)

    # ── Trafic routier ───────────────────────────────────────────────────
    st.markdown("##### 🚦 État du trafic routier")
    render_traffic_widget()

    st.markdown("##### 🗺️ Carte du trafic — H+1h")
    render_traffic_map_compact(height=320, horizon_minutes=60, key_suffix="usager")

    # ── Trajet Vélov ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🚲 Trajet Vélov + marche")

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
            f"Impossible de résoudre les coordonnées GPS : "
            f"{search['origin']} → {origin_coords}, "
            f"{search['destination']} → {dest_coords}"
        )

    # ── Itinéraire voiture ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🛣️ Itinéraire voiture")

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

    if st.button(
        "🚗 Calculer l'itinéraire",
        type="primary",
        use_container_width=True,
        key="itin_calc_btn",
    ):
        render_itinerary_result(
            origin=search["origin"],
            destination=search["destination"],
            horizon_minutes=60,
        )

    # ── Cartes informatives ──────────────────────────────────────────────
    st.markdown("---")

    st.markdown("##### 🗺️ Couverture Vélov des lieux emblématiques")
    try:
        render_lieux_velov_map(height=400)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")

    st.markdown("##### 🚲 Toutes les stations Vélo'v")
    render_velov_map_compact(height=320, key_suffix="usager")

    st.markdown("---")

st.caption(
    f"LyonFlowFull v{get_settings().app_version} · "
    "100% pipeline (PostgreSQL, Airflow, MLflow)"
)
