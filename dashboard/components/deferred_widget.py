"""Helper de chargement différé (button-gate) — Sprint 15+ audit.

Problème : `st.tabs` et `st.expander` ne diffèrent PAS le calcul. Les widgets
lourds (Folium HTML, pydeck WebGL, multi-Plotly) se re-rendent à chaque
auto-refresh (30s Pro, 60s Usager). Sur VPS 12 Go, Pro_3 cumule 3 widgets
Sprint 13+/15+ (Folium + 3×Plotly + PostGIS) = 5-15s par cycle.

Solution : ``deferred_render()`` persiste le choix de l'utilisateur dans
``session_state`` pour qu'au prochain auto-refresh le widget reste visible.
Un simple ``st.button()`` retourne True uniquement au clic — au refresh
suivant il repasse à False et le widget disparaît. C'est le piège #1.

Usage::

    from dashboard.components.deferred_widget import deferred_render

    deferred_render(
        "multimodal_heatmap",
        "Charger la vue multimodale grille 0.01°",
        render_multimodal_heatmap,
    )

    # Avec args kwargs :
    deferred_render(
        "bus_spatial",
        "Charger la corrélation spatiale bus × trafic",
        render_bus_traffic_spatial,
        line_id=target_line,
    )
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st


def deferred_render(
    widget_key: str,
    label: str,
    render_fn: Callable[..., Any],
    *args: Any,
    show_label: str = "Masquer",
    button_icon: str = "📊",
    **kwargs: Any,
) -> None:
    """Affiche un bouton. Au clic, persiste dans session_state et rend le widget.

    Args:
        widget_key: identifiant unique (utilisé comme suffixe de session_state).
        label: texte du bouton "Charger".
        render_fn: callable à exécuter (le widget).
        *args: positionnels passés à ``render_fn``.
        show_label: texte du bouton "Masquer" (défaut: "Masquer").
        button_icon: emoji du bouton (défaut: 📊).
        **kwargs: kwargs passés à ``render_fn``.

    Le widget reste affiché tant que l'utilisateur n'a pas cliqué "Masquer",
    indépendamment des auto-refresh Streamlit (30s, 60s, 300s).
    """
    state_key = f"show_{widget_key}"
    btn_key = f"btn_load_{widget_key}"
    hide_key = f"btn_hide_{widget_key}"

    # Bouton "Charger" — toujours visible, persiste le choix au clic
    if st.button(f"{button_icon} {label}", key=btn_key):
        st.session_state[state_key] = True
        # Pas de st.rerun() ici — Streamlit re-run naturellement après le clic
        # et la condition ci-dessous rendra le widget dans le même cycle.

    if st.session_state.get(state_key):
        # Délimiteur visuel pour bien voir la zone lazy
        st.markdown("---")
        render_fn(*args, **kwargs)
        if st.button(f"🙈 {show_label}", key=hide_key):
            st.session_state[state_key] = False
            st.rerun()
