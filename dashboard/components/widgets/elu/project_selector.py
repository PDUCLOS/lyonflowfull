"""Widget — Sélecteur d'un aménagement passé.

Sprint 8 — Aménagements via data_loader.cached_amenagements_passes().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_amenagements_passes


def render_project_selector(key_suffix: str = "default") -> dict | None:
    """Affiche un sélecteur d'aménagement passé.

    Args:
        key_suffix: suffixe pour la clé Streamlit.

    Returns:
        Dict aménagement sélectionné ou None.
    """
    df = cached_amenagements_passes(force_mock=False)
    amenagements = df.to_dict("records") if not df.empty else []
    if not amenagements:
        st.info("Aucun aménagement passé disponible.")
        return None

    # Adapt DB format → expected nom/description keys
    options = []
    options_to_record = {}
    for a in amenagements:
        # DB format utilise "name", mock utilise "nom"
        label = a.get("name") or a.get("nom", "—")
        options.append(label)
        options_to_record[label] = a

    selected_name = st.selectbox(
        "Aménagement à analyser",
        options,
        key=f"project_selector_{key_suffix}",
    )

    if not selected_name:
        return None
    return options_to_record.get(selected_name)
