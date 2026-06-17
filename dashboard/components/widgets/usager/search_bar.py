"""Widget — Barre de recherche trajet (géocodage + sélection cliquable).

Affiche 2 champs (départ + destination) avec auto-complétion **cliquable** :
- Liste d'adresses Lyon (DB referentiel.lieux_lyon) avec icône par type (gare/place/quartier…)
- Bouton par adresse : au clic, remplit départ OU destination selon le toggle actif
- Plus de tape à la main, l'utilisateur clique

Sprint 8 — Adresses chargées via
data_loader.cached_lyon_addresses_with_coords() (zéro mock).
"""

from __future__ import annotations

import typing

import streamlit as st

from dashboard.components.data_cache import cached_lyon_addresses_with_coords

_TYPE_ICON = {
    "gare": "🚉",
    "place": "📍",
    "monument": "🏛",
    "quartier": "🏘",
    "parc": "🌳",
    "universite": "🎓",
    "banlieue": "🏙",
}

def render_search_bar() -> dict[str, typing.Any]:
    """Affiche la barre de recherche trajet, élégante et ergonomique."""
    addresses = cached_lyon_addresses_with_coords()
    # Préparer les options pour la selectbox
    addr_options = [f"{_TYPE_ICON.get(a['type'], '📍')} {a['name']}" for a in addresses]

    # Injection de CSS pour un style épuré
    st.markdown("""
    <style>
    /* Styling des selectbox pour un effet plus premium */
    div[data-baseweb="select"] > div {
        border-radius: 8px;
        background-color: var(--secondary-background-color);
        border: 1px solid var(--border-color);
        transition: all 0.3s ease;
    }
    div[data-baseweb="select"] > div:hover {
        border-color: var(--primary-color);
    }
    /* Stylisation du container principal de recherche */
    .search-container {
        padding: 1.5rem;
        border-radius: 12px;
        background: linear-gradient(145deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### 🗺️ Où allez-vous ?")

        col1, col2 = st.columns(2)
        with col1:
            origin = st.selectbox(
                "🟢 Point de départ",
                options=addr_options,
                index=addr_options.index("🏙 Villeurbanne") if "🏙 Villeurbanne" in addr_options else 0,
                key="search_origin",
                help="Tapez pour rechercher une adresse"
            )
        with col2:
            destination = st.selectbox(
                "🔴 Destination",
                options=addr_options,
                index=addr_options.index("🚉 Part-Dieu") if "🚉 Part-Dieu" in addr_options else min(1, len(addr_options)-1),
                key="search_destination",
                help="Tapez pour rechercher une adresse"
            )

        st.markdown("<br/>", unsafe_allow_html=True)

        # Bloc départ et filtres
        col_time, col_modes = st.columns([1, 1])
        with col_time:
            departure_mode = st.radio(
                "Quand ?",
                ["🚶 Partir maintenant", "⏰ Arriver à l'heure"],
                horizontal=True,
                key="search_dep_mode",
            )
            departure_time = None
            if departure_mode == "⏰ Arriver à l'heure":
                departure_time = st.time_input("Heure prévue", key="search_dep_time")

        with col_modes:
            modes = st.multiselect(
                "Modes de transport autorisés",
                ["🚇 Métro", "🚊 Tram", "🚌 Bus", "🚲 Vélov", "🚗 Voiture", "🚶 Marche"],
                default=["🚇 Métro", "🚊 Tram", "🚌 Bus", "🚲 Vélov", "🚶 Marche"],
                key="search_modes"
            )

    return {
        "origin": origin,
        "destination": destination,
        "departure_mode": departure_mode,
        "departure_time": str(departure_time) if departure_time else None,
        "modes": modes,
    }
