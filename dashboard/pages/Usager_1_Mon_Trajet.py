"""Page Usager — Mon trajet.

Recherche d'itineraire multimodale Lyon. Widgets :
- search_bar (selectbox lieux referentiel)
- weather_widget, velov_widget, traffic_widget (contexte)
- velov_trip (trajet Velov calcule live)
- itinerary_result (trajet voiture Dijkstra)
- traffic_map_compact, velov_map_compact (cartes)
"""

from __future__ import annotations

import logging
import math

import streamlit as st

logger = logging.getLogger(__name__)

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_cache import cached_traffic
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.common import render_traffic_map_compact
from dashboard.components.widgets.usager import (
    render_itinerary_result,
    render_lieux_velov_map,
    render_mode_comparison,
    render_mode_summary,
    render_search_bar,
    render_traffic_widget,
    render_transit_trip,
    render_velov_map_compact,
    render_velov_trip,
    render_velov_widget,
    render_weather_widget,
)
from src.config import get_settings
from src.data.exceptions import DashboardDataError
from src.routing.eco_calculator import calculate_impact, is_congested_from_speed

st.set_page_config(
    page_title="Mon trajet — LyonFlowFull",
    page_icon="🧭",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

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
    st.session_state.pop("itin_compute", None)
    st.session_state.pop("itin_cached_alts", None)
    st.session_state.pop("itin_alt_choice", None)
elif "results_loaded" not in st.session_state:
    st.session_state["results_loaded"] = False

if st.session_state.get("results_loaded"):
    from dashboard.components.widgets.usager.velov_trip import _resolve_lieu
    from src.data.data_loader import load_nearest_velov_stations

    modes = search.get("modes", [])
    has_velov = any("Vélov" in m for m in modes)
    has_voiture = any("Voiture" in m for m in modes)
    # Sprint 14 (2026-06-19) — Transport en commun : nouveau mode unifié
    # Métro + Tram + Bus fusionnés en "🚌 Transport en commun".
    has_tc = any("Transport en commun" in m for m in modes)

    origin_coords = _resolve_lieu(search["origin"])
    dest_coords = _resolve_lieu(search["destination"])

    # ── Comparateur multimodal (Sprint 15+ audit P0-3 + Sprint 16 Axe C) ──
    # Affiche un comparatif 3 modes (tc/voiture/velov) + winner card
    # AVANT les détails par mode. Sprint 16 : si une durée réelle est déjà
    # calculée pour un mode (session_state["trip_<key>"]), on l'utilise.
    # Sinon, fallback estimation par vitesses moyennes Lyon.
    # Sprint 22+ : vitesse voiture = ``cached_traffic()`` (live), pas hardcodée ;
    # détection congestion via ``is_congested_from_speed()`` (vraie valeur).
    if origin_coords and dest_coords and len(modes) >= 2:
        # Récupère la vitesse moyenne Lyon live (avec gestion d'erreur
        # explicite : on catche DashboardDataError uniquement, pas Exception
        # — un KeyboardInterrupt ou SystemExit doit remonter).
        try:
            traffic_live = cached_traffic()
            real_avg_speed = float(traffic_live.get("average_speed_kmh", 0) or 0)
            traffic_unavailable = False
        except DashboardDataError as e:
            logger.warning("cached_traffic() indispo dans comparateur : %s", e)
            real_avg_speed = 0.0
            traffic_unavailable = True

        # Vitesses moyennes par mode. Voiture = live si dispo, sinon fallback
        # 25 km/h (ref ADEME "urbain France"). Vélov + TC = hypothèses
        # documentées (cf. SPEC_COMPARATEUR_MODES_USAGER.md).
        speed_kmh = {
            "velov": 12.0,  # moyenne Lyon (ADEME + obs terrain)
            "tc": 18.0,     # moyen bus/tram/métro SYTRAL
            "voiture": real_avg_speed if real_avg_speed > 0 else 25.0,
        }
        is_congested_voiture = is_congested_from_speed(real_avg_speed)

        R_KM = 6371.0
        lat1, lon1 = math.radians(origin_coords[1]), math.radians(origin_coords[0])
        lat2, lon2 = math.radians(dest_coords[1]), math.radians(dest_coords[0])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        dist_km = 2 * R_KM * math.asin(math.sqrt(a))
        # Mapping display name (search_bar) → key (mode_comparison)
        mode_to_key = {
            "Vélov": "velov",
            "Voiture": "voiture",
            "Transport en commun": "tc",
        }
        # Construit results pour les modes actifs et faisables.
        # Sprint 16 Axe C : on privilégie la durée RÉELLE depuis session_state
        # si dispo, sinon fallback estimation.
        results: dict[str, dict] = {}
        for display_name, key in mode_to_key.items():
            if not any(display_name in m for m in modes):
                continue
            trip_real = st.session_state.get(f"trip_{key}")
            # Sprint 22+ : is_congested n'est True QUE pour voiture ET QUE si
            # la vitesse moyenne Lyon le justifie (réel, pas un proxy bidon).
            is_congested = (key == "voiture" and is_congested_voiture)
            if trip_real:
                dur_min = float(trip_real["duration_min"])
                impact = calculate_impact(
                    mode=key,
                    distance_km=float(trip_real.get("distance_km", dist_km)),
                    duration_min=dur_min,
                    is_congested=is_congested,
                )
                results[key] = {
                    "duration_min": dur_min,
                    "distance_km": float(trip_real.get("distance_km", dist_km)),
                    "impact": impact,
                    "feasible": True,
                    "source": "computed",  # durée réelle calculée
                }
            else:
                v = speed_kmh[key]
                dur_min = (dist_km / v) * 60.0
                impact = calculate_impact(
                    mode=key,
                    distance_km=dist_km,
                    duration_min=dur_min,
                    is_congested=is_congested,
                )
                # Tag "live" pour la voiture si on a la vitesse réelle
                source_tag = "estimated"
                if key == "voiture" and not traffic_unavailable:
                    source_tag = "live_estimated"
                results[key] = {
                    "duration_min": dur_min,
                    "distance_km": dist_km,
                    "impact": impact,
                    "feasible": True,
                    "source": source_tag,
                }
        if results:
            st.markdown("---")
            st.markdown("### ⚖️ Comparaison des modes")
            render_mode_comparison(
                results=results,
                critere=search.get("critere", "temps"),
                origin=search["origin"],
                destination=search["destination"],
            )
            # Summary cards (1 par mode actif)
            st.markdown("#### 📊 Détail par mode")
            n_modes = len(results)
            cols = st.columns(min(n_modes, 3))
            for col, (key, r) in zip(cols, results.items()):
                with col:
                    render_mode_summary(
                        mode=key,
                        duration_min=r["duration_min"],
                        distance_km=r["distance_km"],
                        impact=r["impact"],
                    )

    # ── Contexte : météo (toujours) + Vélov destination (si mode actif) ──
    st.markdown("##### 🌤 Conditions actuelles")
    if has_velov:
        ctx1, ctx2 = st.columns(2)
        with ctx1:
            render_weather_widget()
        with ctx2:
            if dest_coords is not None:
                try:
                    stations_dest = load_nearest_velov_stations(
                        lat=dest_coords[1],
                        lon=dest_coords[0],
                        k=3,
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
    else:
        render_weather_widget()

    # ── Trajet transport en commun (si TC sélectionné, Sprint 14) ─────────
    # Sprint 22+ — button-gate (deferred_render) au lieu d'expander seul :
    # render_transit_trip() fait des appels GTFS lourds (1-3s) — on attend
    # le clic explicite de l'user pour déclencher le calcul. Sans ça, le
    # seul `with st.expander()` exécute le code à l'ouverture (cf. P0-1
    # Sprint 15+ dans deferred_widget.py:3).
    if has_tc:
        st.markdown("---")
        deferred_render(
            "usager_transit_trip",
            "Charger le trajet transport en commun",
            _render_transit_trip_for_user,
            origin=search["origin"],
            destination=search["destination"],
            button_icon="🚌",
        )

    # ── Trafic routier (si Voiture sélectionné) ──────────────────────────
    if has_voiture:
        st.markdown("##### 🚦 État du trafic routier")
        render_traffic_widget()

        with st.expander("🗺️ Carte du trafic — H+1h", expanded=False):
            render_traffic_map_compact(height=320, horizon_minutes=60, key_suffix="usager")

    # ── Trajet Vélov (si Vélov sélectionné) ──────────────────────────────
    if has_velov:
        st.markdown("---")
        with st.expander("🚲 Trajet Vélov + marche", expanded=False):
            if origin_coords and dest_coords:
                try:
                    # Sprint 16 Axe C — Stocke la durée réelle dans session_state.
                    velov_result = render_velov_trip(
                        origin=search["origin"],
                        destination=search["destination"],
                        origin_coords=origin_coords,
                        dest_coords=dest_coords,
                    )
                    if velov_result:
                        st.session_state["trip_velov"] = velov_result
                except DashboardDataError as e:
                    st.error(f"⚠️ {e}")
            else:
                st.warning(
                    f"Impossible de résoudre les coordonnées GPS : "
                    f"{search['origin']} → {origin_coords}, "
                    f"{search['destination']} → {dest_coords}"
                )

    # ── Itinéraire voiture (si Voiture sélectionné) ──────────────────────
    if has_voiture:
        st.markdown("---")
        st.markdown("### 🛣️ Itinéraire voiture")

        itin_col1, itin_col2 = st.columns([3, 1])
        with itin_col1:
            st.markdown(
                f"""
                <div class="lyf-label" style="background:var(--bg-card);padding:0.8rem 1rem;border-radius:6px;border-left:4px solid #4CAF50;display:flex;align-items:center;gap:0.6rem;">
                    <span class="lyf-sublabel" style="background:#4CAF50;color:white;padding:0.2rem 0.6rem;border-radius:12px;font-weight:600;">🟢 DÉPART</span>
                    <span style="font-weight:600;">{search["origin"]}</span>
                    <span style="opacity:0.4;margin:0 0.5rem;">→</span>
                    <span class="lyf-sublabel" style="background:#F44336;color:white;padding:0.2rem 0.6rem;border-radius:12px;font-weight:600;">🔴 ARRIVÉE</span>
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
            st.session_state["itin_compute"] = True
            st.session_state.pop("itin_cached_alts", None)
            st.session_state.pop("itin_alt_choice", None)

        if st.session_state.get("itin_compute"):
            with st.expander("Voir l'itinéraire voiture détaillé", expanded=True):
                voiture_result = render_itinerary_result(
                    origin=search["origin"],
                    destination=search["destination"],
                    origin_coords=origin_coords,
                    dest_coords=dest_coords,
                )
                if voiture_result:
                    st.session_state["trip_voiture"] = voiture_result

    # ── Cartes informatives Vélov (si Vélov sélectionné) ─────────────────
    if has_velov:
        st.markdown("---")

        with st.expander("🗺️ Couverture Vélov des lieux emblématiques", expanded=False):
            try:
                render_lieux_velov_map(height=400)
            except DashboardDataError as e:
                st.error(f"⚠️ {e}")

        with st.expander("🚲 Toutes les stations Vélo'v", expanded=False):
            render_velov_map_compact(height=320, key_suffix="usager")

    st.markdown("---")

st.caption(f"LyonFlowFull v{get_settings().app_version} · 100% pipeline (PostgreSQL, Airflow, MLflow)")


# === Helpers privés Sprint 22+ — appelés par deferred_render (button-gate) ===
# Avant : ces appels étaient inline dans des ``with st.expander()`` (P2
# du quick wins Sprint 22+). Le seul expander ne différait PAS le calcul,
# donc le code s'exécutait à l'ouverture (coût GTFS 1-3s). Le wrapping
# dans ``deferred_render`` (button-gate) attend le clic explicite de
# l'user avant de lancer le calcul. Cf. P0-1 Sprint 15+ dans
# deferred_widget.py:3.


def _render_transit_trip_for_user(origin: str, destination: str) -> None:
    """Helper pour deferred_render : appel GTFS + stockage session_state."""
    try:
        # Sprint 16 Axe C — Stocke la durée réelle dans session_state
        # pour le comparateur multimodal.
        tc_result = render_transit_trip(
            origin=origin,
            destination=destination,
        )
        if tc_result:
            st.session_state["trip_tc"] = tc_result
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
