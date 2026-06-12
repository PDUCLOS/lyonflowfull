"""Widget — Liste des trajets favoris."""

from __future__ import annotations

import streamlit as st


def render_favorite_list(favorites: list) -> None:
    """Affiche la liste des trajets favoris.

    Args:
        favorites: liste de dicts {id, name, origin, destination, usual_mode, ...}
    """
    if not favorites:
        st.info("Aucun trajet favori. Ajoute-en un pour recevoir des alertes proactives.")
        return

    for fav in favorites:
        render_recurrent_trip_card(fav, expanded=False, key_prefix="")


def render_recurrent_trip_card(fav: dict, expanded: bool = True, key_prefix: str = "") -> None:
    """Affiche une carte trajet récurrent avec prédiction.

    Args:
        fav: dict {id, name, origin, destination, usual_mode, usual_duration_min,
                   next_departure, alert_subscribed}
        expanded: True pour afficher les détails inline.
        key_prefix: préfixe pour les clés Streamlit (évite les duplicate keys
                    quand on render la même carte dans des contextes différents).
    """
    name = fav.get("name", "—")
    origin = fav.get("origin", "—")
    destination = fav.get("destination", "—")
    mode = fav.get("usual_mode", "—")
    duration = fav.get("usual_duration_min", 0)
    next_dep = fav.get("next_departure", "—")
    alert_on = fav.get("alert_subscribed", False)
    # Compose la key unique : key_prefix + id (fallback name pour mock sans id)
    fav_uid = fav.get("id") or fav.get("name", "unknown")
    button_key = f"{key_prefix}fav_view_{fav_uid}"

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

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            st.caption(f"⏰ Prochain : **{next_dep}**")
        with c2:
            st.caption(f"{'🔔 Alertes activées' if alert_on else '🔕 Alertes désactivées'}")
        with c3:
            if st.button("Voir", key=button_key):
                st.info(f"Détails trajet {name}")

        if expanded:
            st.markdown("---")
