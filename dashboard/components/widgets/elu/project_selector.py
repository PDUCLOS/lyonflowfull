"""Widget — Sélecteur d'un aménagement passé.

Aménagements via data_loader.cached_amenagements_passes().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_amenagements_passes
from dashboard.components.loading_state import loading_wrapper


def render_project_selector(key_suffix: str = "default") -> dict | None:
    with loading_wrapper("Chargement Project selector…", "⏳"):
        """Affiche un sélecteur d'aménagement passé.

    Args:
        key_suffix: suffixe pour la clé Streamlit.

    Returns:
        Dict aménagement sélectionné ou None.
    """
    df = cached_amenagements_passes()
    amenagements = df.to_dict("records") if not df.empty else []
    if not amenagements:
        st.info("Aucun aménagement passé disponible.")
        return None

    # Adapt DB format → expected nom/description keys
    options = []
    options_to_record = {}
    for idx, a in enumerate(amenagements):
        # DB format utilise "name", mock utilise "nom". Si les 2 sont None,
        # on ajoute un suffixe pour distinguer les options (sinon N entrées "—"
        # indistinguables dans le selectbox).
        raw_label = a.get("name") or a.get("nom")
        if not raw_label:
            raw_label = f"Aménagement #{idx + 1}"
        # Si doublon, suffixe
        label = raw_label
        suffix = 2
        while label in options_to_record:
            label = f"{raw_label} ({suffix})"
            suffix += 1
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
