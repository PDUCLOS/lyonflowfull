"""Widget — Barre de recherche trajet (géocodage + sélection cliquable).

Affiche 2 champs (départ + destination) avec auto-complétion **cliquable** :
- Liste d'adresses Lyon (DB referentiel.lieux_lyon) avec icône par type (gare/place/quartier…)
- Bouton par adresse : au clic, remplit départ OU destination selon le toggle actif
- Plus de tape à la main, l'utilisateur clique

 Adresses chargées via
data_loader.cached_lyon_addresses_with_coords() (zéro mock).

 (2026-06-19) — Ajout du radio "Optimiser pour" (temps / coût).
Ce critère sert :
- Phase 1 : affichage enrichi dans ``render_mode_summary`` (KPI cards).
- Phase 2 : critère de tri du comparateur multi-modes (winner card).
Le critère est ajouté au dict retourné sous la clé ``"critere"``
(``"temps"`` | ``"cout"``).
"""

from __future__ import annotations

import typing

import streamlit as st

from dashboard.components.data_cache import cached_lyon_addresses_with_coords
from dashboard.components.loading_state import loading_wrapper

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
    with loading_wrapper("Chargement Search bar…", "⏳"):
        addresses = cached_lyon_addresses_with_coords()
        # Préparer les options pour la selectbox
        addr_options = [f"{_TYPE_ICON.get(a['type'], '📍')} {a['name']}" for a in addresses]

        # Injection de CSS pour un style épuré
        st.markdown(
            """
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
    /* Segmented control modes de transport : plus visible */
        div[data-testid="stSegmentedControl"] {
            margin-top: 0.25rem;
        }
        div[data-testid="stSegmentedControl"] label {
            padding: 0.6rem 0.8rem !important;
            font-weight: 500 !important;
        }
        div[data-testid="stSegmentedControl"] label[data-checked="true"] {
            background-color: var(--primary-color) !important;
            color: white !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
        }
        .mode-hint {
            font-size: 0.8rem;
            color: var(--text-color-secondary, rgba(128,128,128,0.9));
            margin-top: 0.4rem;
            font-style: italic;
        }
    /* radio critère d'optimisation : compact, sous le mode hint */
        div[data-testid="stRadio"][aria-label="Optimiser pour"] {
            margin-top: 0.5rem;
        }
        div[data-testid="stRadio"][aria-label="Optimiser pour"] label {
            padding: 0.3rem 0.6rem !important;
            font-size: 0.85rem !important;
        }
        </style>
        """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown("#### 🗺️ Où allez-vous ?")

            col1, col2 = st.columns(2)
            with col1:
                origin = st.selectbox(
                    "🟢 Point de départ",
                    options=addr_options,
                    index=addr_options.index("🏙 Villeurbanne") if "🏙 Villeurbanne" in addr_options else 0,
                    key="search_origin",
                    help="Tapez pour rechercher une adresse",
                )
            with col2:
                destination = st.selectbox(
                    "🔴 Destination",
                    options=addr_options,
                    index=addr_options.index("🚉 Part-Dieu")
                    if "🚉 Part-Dieu" in addr_options
                    else min(1, len(addr_options) - 1),
                    key="search_destination",
                    help="Tapez pour rechercher une adresse",
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
                # (2026-06-19) — Refonte UX modes de transport v3 :
                # - Single-select (``selection_mode="single"``) + ``required=True`` :
                #   l'usager choisit 1 mode à la fois, et ne peut pas le
                #   désélectionner (clic sur l'option active = no-op, cf. doc
                #   Streamlit). Garantit que ``selected_mode`` est toujours set.
                # - Default = ``"🚌 Transport en commun"`` (mode principal usager).
                # - Retour wrappé en liste d'1 élément pour rétro-compat avec
                #   ``has_velov/has_voiture/has_tc`` dans Usager_1_Mon_Trajet.py:74-79.
                # - (2026-06-19) : fusion TC + suppression Marche.
                selected_mode = st.segmented_control(
                    "Modes de transport autorisés",
                    options=["🚌 Transport en commun", "🚲 Vélov", "🚗 Voiture"],
                    selection_mode="single",
                    default="🚌 Transport en commun",
                    key="search_modes",
                    width="stretch",
                    required=True,
                    help="Un seul mode à la fois — obligatoire",
                )
                # Hint contextuel + rétro-compat ``modes`` (list[str]) pour le code aval.
                _mode_hints = {
                    "🚌 Transport en commun": "Métro · Tram · Bus (GTFS TCL temps réel)",
                    "🚲 Vélov": "Vélos en libre-service + marche d'accès",
                    "🚗 Voiture": "Itinéraire routier avec trafic H+1h",
                }
                st.markdown(
                    f'<div class="mode-hint">{_mode_hints[selected_mode]}</div>',
                    unsafe_allow_html=True,
                )
                modes = [selected_mode]

                # Critère d'optimisation (radio horizontal compact).
                # Position : sous le hint contextuel dans la même col_modes.
                # Sert au scoring composite du comparateur Phase 2 (cf. eco_calculator).
                critere_label = st.radio(
                    "Optimiser pour",
                    ["⏱️ Temps", "💰 Coût"],
                    horizontal=True,
                    key="search_critere",
                    index=0,
                    help="Critère de tri pour le comparateur multi-modes (Phase 2)",
                )
                critere = "temps" if critere_label.startswith("⏱") else "cout"

        return {
            "origin": origin,
            "destination": destination,
            "departure_mode": departure_mode,
            "departure_time": str(departure_time) if departure_time else None,
            "modes": modes,
            "critere": critere,
        }
