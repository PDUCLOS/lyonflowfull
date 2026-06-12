"""Widget — Liste des trajets favoris avec alternatives multimodales (Sprint 10)."""

from __future__ import annotations

import streamlit as st

# Mapping mode → icône
MODE_ICONS = {
    "metro": "🚇",
    "tram": "🚊",
    "bus": "🚌",
    "velov": "🚲",
    "walk": "🚶",
    "vtc": "🚕",
    "car": "🚗",
}


def render_favorite_list(favorites: list, api_base_url: str | None = None) -> None:
    """Affiche la liste des trajets favoris.

    Args:
        favorites: liste de dicts {id, name, origin, destination, usual_mode, ...}
        api_base_url: URL de base de l'API (optionnel — sinon utilise session_state)
    """
    if not favorites:
        st.info("Aucun trajet favori. Ajoute-en un pour recevoir des alertes proactives.")
        return

    for fav in favorites:
        render_recurrent_trip_card(fav, expanded=False, key_prefix="", api_base_url=api_base_url)


def render_recurrent_trip_card(
    fav: dict,
    expanded: bool = True,
    key_prefix: str = "",
    api_base_url: str | None = None,
) -> None:
    """Affiche une carte trajet récurrent avec bouton Alternatives.

    Args:
        fav: dict {id, name, origin, destination, usual_mode, usual_duration_min,
                   next_departure, alert_subscribed}
        expanded: True pour afficher les détails inline.
        key_prefix: préfixe pour les clés Streamlit.
        api_base_url: URL de base de l'API.
    """
    name = fav.get("name", "—")
    origin = fav.get("origin", "—")
    destination = fav.get("destination", "—")
    mode = fav.get("usual_mode", "—")
    duration = fav.get("usual_duration_min", 0)
    next_dep = fav.get("next_departure", "—")
    alert_on = fav.get("alert_subscribed", False)
    fav_uid = fav.get("id") or fav.get("name", "unknown")

    # Session state pour les alternatives affichées
    alt_key = f"{key_prefix}alt_expanded_{fav_uid}"
    if alt_key not in st.session_state:
        st.session_state[alt_key] = False

    with st.container():
        st.markdown(
            f"""
            <div class="lyonflow-card">
                <div style="display:flex;justify-content:space-between;align-items:start;">
                    <div>
                        <div style="font-size:1.05rem;font-weight:600;">{name}</div>
                        <div style="font-size:0.85rem;opacity:0.7;margin-top:2px;">
                            {origin} → {destination}
                        </div>
                    </div>
                    <div style="text-align:right;font-size:0.85rem;">
                        <div>🚇 {mode}</div>
                        <div style="opacity:0.7;">{duration} min</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        with c1:
            st.caption(f"⏰ Prochain : **{next_dep}**")
        with c2:
            st.caption(f"{'🔔 Alertes activées' if alert_on else '🔕 Alertes désactivées'}")
        with c3:
            view_key = f"{key_prefix}fav_view_{fav_uid}"
            if st.button("Voir", key=view_key):
                st.info(f"Details trajet {name}")
        with c4:
            # Bouton Alternatives — toggle
            btn_label = "Masquer" if st.session_state.get(alt_key) else "Alternatives"
            alt_btn_key = f"{key_prefix}alt_btn_{fav_uid}"
            if st.button(btn_label, key=alt_btn_key):
                st.session_state[alt_key] = not st.session_state.get(alt_key, False)
                st.rerun()

        # Affichage des alternatives si expandé
        if st.session_state.get(alt_key):
            _render_alternatives_widget(fav, api_base_url)

        if expanded:
            st.markdown("---")


def _render_alternatives_widget(
    fav: dict,
    api_base_url: str | None = None,
) -> None:
    """Appelle l'API et affiche les alternatives multimodales."""
    fav_id = fav.get("id")
    fav_name = fav.get("name", "ce trajet")

    if not api_base_url:
        api_base_url = st.session_state.get("api_base_url", "http://localhost:8000")

    if not fav_id:
        st.caption("ID favori manquant — alternatives non disponibles.")
        return

    url = f"{api_base_url}/api/favorites/{fav_id}/alternatives"

    try:
        import requests

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            alternatives = response.json()
            _display_alternatives(alternatives, fav_name)
        elif response.status_code == 404:
            st.warning(f"Favori introuvable (ID: {fav_id})")
        else:
            st.warning(f"Erreur API ({response.status_code}) — essayer en mode demo")
            # Fallback : mock local
            _display_alternatives(_mock_alternatives(fav), fav_name)
    except Exception:
        # Erreur réseau → fallback mock
        _display_alternatives(_mock_alternatives(fav), fav_name)


def _display_alternatives(alternatives: list[dict], fav_name: str) -> None:
    """Affiche la liste des alternatives dans une UI structurée."""
    if not alternatives:
        st.info("Aucune alternative disponible pour le moment.")
        return

    st.markdown(f"**Alternatives pour {fav_name}**")
    for alt in alternatives:
        mode_icon = alt.get("mode_icon", "🚇")
        mode_label = alt.get("mode_label", alt.get("mode", "?"))
        temps = alt.get("temps_min", "?")
        score = alt.get("score_confiance", 0)
        raison = alt.get("raison", "")

        # Barre de confiance visuelle
        score_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))

        st.markdown(
            f"""
            <div style="margin-left: 0.5rem; margin-bottom: 0.5rem; padding: 0.4rem 0.6rem;
                        border-left: 3px solid #4C78A8; background: #f8f9fa; border-radius: 4px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <span style="font-size:1.1rem;">{mode_icon}</span>
                        <strong>{mode_label}</strong>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:1.1rem;font-weight:600;">{temps} min</span>
                    </div>
                </div>
                <div style="margin-top:2px;font-size:0.78rem;color:#555;">
                    confiance {score_bar} {score:.0%}
                </div>
                <div style="margin-top:2px;font-size:0.78rem;color:#666;font-style:italic;">
                    {raison}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _mock_alternatives(fav: dict) -> list[dict]:
    """Fallback mock quand l'API nest pas accessible."""
    usual_duration = fav.get("usual_duration_min") or 20
    return [
        {
            "mode": "velov",
            "mode_label": "Velov'",
            "mode_icon": "bike",
            "temps_min": max(1, usual_duration - 3),
            "score_confiance": 0.82,
            "raison": "12 velos dispo . 8 docks . a 3 min plus rapide",
        },
        {
            "mode": "bus",
            "mode_label": "Bus C13",
            "mode_icon": "bus",
            "temps_min": usual_duration + 5,
            "score_confiance": 0.68,
            "raison": "C13 a 150m . attente ~4 min . pas de correspondances",
        },
        {
            "mode": "vtc",
            "mode_label": "VTC / Taxi",
            "mode_icon": "taxi",
            "temps_min": max(1, usual_duration - 8),
            "score_confiance": 0.72,
            "raison": "disponible 24h/24 . plus rapide (14 min)",
        },
    ]
