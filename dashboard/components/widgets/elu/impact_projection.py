"""Widget — Projection d'impact (trafic VP, bus, vélo, CO2)."""

from __future__ import annotations

import streamlit as st


def render_impact_projection(zone: str | None = None) -> None:
    """Affiche la projection d'impact d'un aménagement.

    Args:
        zone: nom de la zone (optionnel).
    """
    st.markdown("##### 🔮 Projection d'impact")

    if not zone:
        st.info("Sélectionnez une zone sur la carte pour voir la projection.")
        return

    # Modèle simplifié (Sprint 5 : GNN + XGBoost)
    st.warning(
        "⚠️ **Estimation générique** — ces valeurs (-12% VP, +18% bus, +45% vélo, -23% CO₂) "
        "ne sont PAS calculées pour la zone sélectionnée. Sprint suivant : modèle ML (GNN + XGBoost) "
        "affiné par zone."
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Trafic VP", "-12%", delta_color="inverse", help="Réduction attendue du trafic véhicule particulier")
    with col2:
        st.metric("Fréquentation bus", "+18%", help="Gain de fréquentation bus post-aménagement")
    with col3:
        st.metric("Fréquentation vélo", "+45%", help="Si aménagement cyclable inclus")
    with col4:
        st.metric("CO₂", "-23%", delta_color="inverse", help="Réduction des émissions CO₂ sur la zone")

    st.markdown("---")
    st.markdown("**Hypothèses du modèle (Sprint 4) :**")
    st.caption(
        "- Réduction VP : élastique au report modal TC/vélo\n"
        "- Gain bus : attractivité + fréquence perçue\n"
        "- Gain vélo : effet réseau\n"
        "- CO₂ : mix modal post-aménagement × facteur d'émission"
    )
