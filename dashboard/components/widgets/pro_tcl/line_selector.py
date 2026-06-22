"""Widget — Selecteur de ligne(s) TCL.

Sprint 8 — Lignes chargées via data_loader.cached_tcl_lines().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_tcl_lines
from dashboard.components.loading_state import loading_wrapper


def render_line_selector(multiselect: bool = True, key_suffix: str = "") -> list:
    with loading_wrapper("Chargement Line selector…", "⏳"):
        """Affiche un sélecteur de ligne(s) TCL.

    Args:
        multiselect: True pour multi-sélection, False pour une seule.
        key_suffix: suffixe pour les clés Streamlit (permet plusieurs instances).

    Returns:
        Liste des line_id sélectionnés.
    """
    tcl_lines = cached_tcl_lines()
    options = [(line["id"], f"{line['icon']} {line['name']}") for line in tcl_lines]

    if multiselect:
        selected = st.multiselect(
            "Lignes",
            options=[o[0] for o in options],
            format_func=lambda x: next((o[1] for o in options if o[0] == x), x),
            default=[],
            key=f"line_selector_{key_suffix}",
        )
    else:
        selected_id = st.selectbox(
            "Ligne",
            options=[o[0] for o in options],
            format_func=lambda x: next((o[1] for o in options if o[0] == x), x),
            key=f"line_selector_{key_suffix}",
        )
        selected = [selected_id] if selected_id else []

    return selected
