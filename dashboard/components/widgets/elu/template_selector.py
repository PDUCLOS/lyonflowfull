"""Widget — Sélecteur de type de rapport (template)."""

from __future__ import annotations

import streamlit as st

TEMPLATE_TYPES = {
    "Synthèse mensuelle (5 pages)": {
        "template": "synthese_mensuelle.html",
        "sections": ["kpis", "bottlenecks", "decisions"],
    },
    "Bilan annuel (20 pages)": {
        "template": "synthese_mensuelle.html",  # TODO: template bilan
        "sections": ["kpis", "bottlenecks", "decisions", "amenagements", "perspectives"],
    },
    "Présentation projet aménagement (10 pages)": {
        "template": "synthese_mensuelle.html",  # TODO: template projet
        "sections": ["zone_focus", "avant_apres", "roi", "calendrier"],
    },
    "Rapport annuel RGPD (3 pages)": {
        "template": "synthese_mensuelle.html",  # TODO: template RGPD
        "sections": ["donnees_collectees", "duree_conservation", "droits"],
    },
}


def render_template_selector() -> dict:
    """Affiche un sélecteur de type de rapport.

    Returns:
        Dict avec 'name', 'template', 'sections' sélectionnés.
    """
    selected = st.selectbox(
        "Type de rapport",
        list(TEMPLATE_TYPES.keys()),
        key="report_template_selector",
    )
    return {
        "name": selected,
        **TEMPLATE_TYPES[selected],
    }
