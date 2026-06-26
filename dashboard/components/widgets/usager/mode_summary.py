"""Widget — Résumé KPIs d'un mode de transport (Phase 1 comparateur Usager).

Affiche 4-5 KPI cards (durée, coût, CO2, distance, +calories pour Vélov)
au-dessus du widget détaillé d'un mode (TC / voiture / Vélov).

 (2026-06-19) — Première version. S'inspire du HTML inline utilisé
dans ``transit_trip.py`` et ``velov_trip.py`` (cards avec ``border-left``
colorée + ``st.metric``).

Politique projet ) — ZÉRO MOCK : tout vient du pipeline.
Les impacts sont calculés par ``src.routing.eco_calculator`` (constantes
ADEME/SYTRAL) + ``gold.tarifs_modes`` (Phase 2).

Usage::

    from dashboard.components.widgets.usager.mode_summary import render_mode_summary
    from src.routing.eco_calculator import calculate_impact

    impact = calculate_impact("voiture", distance_km=3.5, is_congested=True)
    render_mode_summary(
        mode="voiture",
        duration_min=12.0,
        distance_km=3.5,
        impact=impact,
    )
"""

from __future__ import annotations

import streamlit as st

# Couleurs par mode (cohérent avec colors.py + spec §3.1)
_MODE_ACCENT = {
    "tc": "#1976D2",  # bleu TCL (cohérent transit_trip.py)
    "voiture": "#FF9800",  # orange voiture (cohérent traffic_widget)
    "velov": "#43A047",  # vert Vélov (cohérent velov_trip.py)
}

_MODE_LABEL = {
    "tc": "🚌 Transport en commun",
    "voiture": "🚗 Voiture",
    "velov": "🚲 Vélov",
}


def render_mode_summary(
    mode: str,
    duration_min: float,
    distance_km: float,
    impact: dict,
) -> None:
    """Affiche les KPI cards (durée + coût + CO2 + distance [+ calories Vélov]).

    Args:
        mode: ``"tc"`` | ``"voiture"`` | ``"velov"``.
        duration_min: durée totale du trajet en minutes.
        distance_km: distance du trajet en km.
        impact: sortie de ``src.routing.eco_calculator.calculate_impact()``
            avec clés ``co2_g``, ``cost_eur``, ``fuel_l``, ``calories_kcal``,
            ``is_congested``, ``congestion_penalty``.
    """
    if mode not in _MODE_ACCENT:
        # Mode inconnu → on log un warning et on affiche un fallback sobre
        st.warning(f"⚠️ Mode inconnu dans render_mode_summary : {mode!r}")
        mode = "tc"
        mode_label = _MODE_LABEL[mode]
    else:
        mode_label = _MODE_LABEL[mode]

    accent = _MODE_ACCENT[mode]

    # Bandeau compact : libellé mode + distance + durée en haut
    st.markdown(
        f"""
        <div class="lyf-label" style="background:var(--bg-card);padding:0.7rem 1rem;border-radius:8px;border-left:4px solid {
            accent
        };display:flex;align-items:center;gap:0.8rem;margin:0.5rem 0 0.7rem 0;flex-wrap:wrap;">
            <span style="background:{accent};color:white;padding:0.25rem 0.7rem;
                         border-radius:12px;font-size:0.8rem;font-weight:600;">
                {mode_label}
            </span>
            <span style="opacity:0.85;">📏 {distance_km:.2f} km</span>
            <span style="opacity:0.85;">🕐 {duration_min:.0f} min</span>
            {
            f'<span style="opacity:0.85;color:{accent};font-weight:600;">⚠️ Congestionné</span>'
            if impact.get("is_congested")
            else ""
        }
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4 ou 5 KPI cards selon le mode
    if mode == "velov":
        # Vélov : 5 cards (Durée, Coût, CO2, Distance, Calories)
        cols = st.columns(5)
        with cols[0]:
            st.metric("🕐 Durée", f"{duration_min:.0f} min")
        with cols[1]:
            cost = float(impact.get("cost_eur", 0.0))
            st.metric(
                "💰 Coût",
                f"{cost:.2f} €",
                help="Gratuit < 30 min pour abonné annuel (Vélov SYTRAL 2026)",
            )
        with cols[2]:
            co2 = float(impact.get("co2_g", 0.0))
            st.metric(
                "🌿 CO2",
                f"{int(co2)} g",
                help="Zéro émission directe (ADEME Base Carbone 2024)",
            )
        with cols[3]:
            st.metric("📏 Distance", f"{distance_km:.2f} km")
        with cols[4]:
            kcal = int(impact.get("calories_kcal", 0))
            st.metric(
                "🔥 Calories",
                f"{kcal} kcal",
                help="~46 kcal/km (MET tables ADEME/INSERM)",
            )
    else:
        # TC + voiture : 4 cards (Durée, Coût, CO2, Distance)
        cols = st.columns(4)
        with cols[0]:
            st.metric("🕐 Durée", f"{duration_min:.0f} min")
        with cols[1]:
            cost = float(impact.get("cost_eur", 0.0))
            help_text = (
                "Ticket TCL unitaire (SYTRAL 2026)" if mode == "tc" else "Carburant SP95 seul (parking = Phase 2)"
            )
            st.metric("💰 Coût", f"{cost:.2f} €", help=help_text)
        with cols[2]:
            co2 = float(impact.get("co2_g", 0.0))
            help_co2 = "Mix bus/tram/métro (SYTRAL/ADEME)" if mode == "tc" else "193 g CO2/km base (ADEME 2024)"
            st.metric("🌿 CO2", f"{int(co2)} g", help=help_co2)
        with cols[3]:
            st.metric("📏 Distance", f"{distance_km:.2f} km")

    # Note congestion pour voiture (sous les KPIs)
    if mode == "voiture" and impact.get("is_congested"):
        penalty = float(impact.get("congestion_penalty", 1.0))
        st.caption(
            f"⚠️ Trafic congestionné : consommation et coût majorés de "
            f"{int((penalty - 1.0) * 100)}% (référence ADEME impact trafic)."
        )
