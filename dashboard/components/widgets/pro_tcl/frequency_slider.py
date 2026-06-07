"""Widget — Slider de fréquence (simulateur)."""

from __future__ import annotations

import streamlit as st


def render_frequency_slider(line_id: str = "C3") -> dict:
    """Affiche un slider pour ajouter/supprimer des bus sur une ligne.

    Args:
        line_id: ligne concernée (par défaut C3).

    Returns:
        Dict avec 'line_id', 'buses_added', 'period_start', 'period_end'
    """
    st.markdown(f"##### 🎚 Simulateur — Ligne {line_id}")

    col1, col2 = st.columns(2)
    with col1:
        buses_added = st.slider(
            "Bus ajoutés (négatif = retirés)",
            min_value=-3, max_value=5, value=1, step=1,
            key=f"freq_slider_{line_id}",
        )
    with col2:
        scenario = st.selectbox(
            "Scénario",
            ["Ajout bus", "Retrait bus", "Redéploiement"],
            key=f"freq_scenario_{line_id}",
        )

    st.markdown("**Plage horaire d'application**")
    c1, c2 = st.columns(2)
    with c1:
        period_start = st.number_input(
            "Début (h)", min_value=0, max_value=23, value=17, step=1,
            key=f"freq_start_{line_id}",
        )
    with c2:
        period_end = st.number_input(
            "Fin (h)", min_value=0, max_value=23, value=19, step=1,
            key=f"freq_end_{line_id}",
        )

    return {
        "line_id": line_id,
        "buses_added": buses_added,
        "scenario": scenario,
        "period_start": period_start,
        "period_end": period_end,
    }
