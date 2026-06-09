"""Widget — Barre de recherche trajet (géocodage simulé + sélection cliquable).

Affiche 2 champs (départ + destination) avec auto-complétion **cliquable** :
- Liste de 21 adresses Lyon (mock) avec icône par type (gare/place/quartier…)
- Bouton par adresse : au clic, remplit départ OU destination selon le toggle actif
- Plus de tape à la main, l'utilisateur clique

Sprint 8 — Adresses chargées via
data_loader.cached_lyon_addresses_with_coords().
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

_TYPE_LABEL = {
    "gare": "Gare",
    "place": "Place",
    "monument": "Monument",
    "quartier": "Quartier",
    "parc": "Parc",
    "universite": "Université",
    "banlieue": "Banlieue",
}


def render_search_bar() -> dict[str, typing.Any]:
    """Affiche la barre de recherche trajet cliquable.

    Returns:
        Dict avec clés 'origin', 'destination', 'departure_mode', 'departure_time',
        'modes'.
    """
    # ---- 2 champs texte (éditables à la main aussi) ----
    col1, col2 = st.columns([1, 1])
    with col1:
        origin = st.text_input(
            "🟢 Départ",
            placeholder="Adresse, arrêt, station…",
            value=st.session_state.get("search_origin", "Villeurbanne"),
            key="search_origin",
        )
    with col2:
        destination = st.text_input(
            "🔴 Destination",
            placeholder="Adresse, arrêt, station…",
            value=st.session_state.get("search_destination", "Part-Dieu"),
            key="search_destination",
        )

    # ---- Auto-complétion cliquable ----
    with st.expander("📍 Adresses suggérées — clique pour sélectionner", expanded=True):
        # Toggle : le prochain clic va dans départ OU destination
        st.caption("Le bouton ira dans :")
        target = st.radio(
            "Cible du prochain clic",
            ["🟢 Départ", "🔴 Destination"],
            horizontal=True,
            key="search_target",
            label_visibility="collapsed",
        )

        addresses = cached_lyon_addresses_with_coords(force_mock=False)
        # Affichage en grille 3 colonnes pour économiser la hauteur
        for i in range(0, len(addresses), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                if i + j >= len(addresses):
                    break
                addr = addresses[i + j]
                icon = _TYPE_ICON.get(addr["type"], "📍")
                with col:
                    if st.button(
                        f"{icon} {addr['name']}",
                        key=f"addr_btn_{addr['name']}",
                        help=f"{_TYPE_LABEL.get(addr['type'], addr['type'])} — clic = remplit {target}",
                        use_container_width=True,
                    ):
                        if "Départ" in target:
                            st.session_state["search_origin"] = addr["name"]
                        else:
                            st.session_state["search_destination"] = addr["name"]
                        st.rerun()

    # ---- Bloc départ (maintenant / heure) ----
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

    # ---- Modes de transport autorisés ----
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
        default=st.session_state.get(
            "search_modes",
            ["🚇 Métro", "🚊 Tram", "🚌 Bus", "🚲 Vélov", "🚶 Marche"],
        ),
        key="search_modes",
        help="Les modes autorisés filtrent les recommandations affichées plus bas",
    )

    return {
        "origin": origin,
        "destination": destination,
        "departure_mode": departure_mode,
        "departure_time": str(departure_time) if departure_time else None,
        "modes": modes,
    }
