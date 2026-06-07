"""Widget — Barre de recherche trajet (géocodage simulé).

Affiche 2 champs (départ + destination) avec auto-complétion simple
basée sur des adresses Lyon (mock statique — pas de DB query).

Sprint 8 — Adresses chargées via data_loader.load_lyon_addresses().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_lyon_addresses


def render_search_bar() -> dict:
    """Affiche la barre de recherche trajet.

    Returns:
        Dict avec clés 'origin', 'destination', 'departure_mode', 'departure_time'

    Note : pas de responsive Streamlit — `st.columns(2)` reste 2 colonnes
    même sur mobile. La docstring antérieure mentionnait "1 colonne mobile"
    qui n'était pas implémentée.
    """
    col1, col2 = st.columns([1, 1])

    with col1:
        origin = st.text_input(
            "🟢 Départ",
            placeholder="Adresse, arrêt, station…",
            value="Villeurbanne",
            key="search_origin",
        )
    with col2:
        destination = st.text_input(
            "🔴 Destination",
            placeholder="Adresse, arrêt, station…",
            value="Part-Dieu",
            key="search_destination",
        )

    # Auto-complétion simple (adresses Lyon, statiques)
    addresses = load_lyon_addresses(force_mock=False)
    with st.expander("📍 Adresses suggérées", expanded=False):
        for addr in addresses[:5]:
            st.caption(f"• {addr}")

    st.markdown("##### 🕐 Départ")
    dep_col1, dep_col2 = st.columns(2)
    with dep_col1:
        departure_mode = st.radio(
            "Mode",
            ["🚶 Partir maintenant", "⏰ Arriver à l'heure"],
            horizontal=True,
            key="search_dep_mode",
        )
    with dep_col2:
        departure_time = st.time_input(
            "Heure",
            value=None,
            key="search_dep_time",
        )

    st.markdown("##### 🚦 Modes autorisés")
    modes = st.multiselect(
        "Filtrer",
        [
            "🚇 Métro",
            "🚊 Tram",
            "🚌 Bus",
            "🚲 Vélov",
            "🚗 Voiture",
            "🚶 Marche",
        ],
        default=["🚇 Métro", "🚊 Tram", "🚌 Bus", "🚲 Vélov", "🚶 Marche"],
        key="search_modes",
    )

    return {
        "origin": origin,
        "destination": destination,
        "departure_mode": departure_mode,
        "departure_time": str(departure_time) if departure_time else None,
        "modes": modes,
    }
