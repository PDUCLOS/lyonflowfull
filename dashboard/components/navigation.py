"""Navigation sidebar adaptée au persona courant.

Remplace la navigation native Streamlit par une navigation custom qui :
- N'affiche que les pages du persona actif
- Ajoute les pages communes (RGPD, À propos) en bas
- Affiche un badge persona en haut
- Propose le switcher de persona en haut
- Filtre via pm.is_widget_visible() (câblage du feature `hidden_widgets`)
"""

from __future__ import annotations

import streamlit as st

from src.persona.manager import PersonaManager, get_current_persona
from src.persona.personas_loader import get_common_pages, get_navigation


def render_sidebar_navigation() -> None:
    """Affiche la navigation custom dans la sidebar Streamlit."""
    pm = PersonaManager()
    persona_id = get_current_persona()

    with st.sidebar:
        # Header persona
        pm.render_sidebar_header()

        # Switcher compact (pills)
        st.markdown("---")
        from dashboard.components.persona_switcher import render_persona_switcher

        with st.expander("🔄 Changer de persona", expanded=False):
            render_persona_switcher(layout="pills")

        # Pages du persona (filtrées par is_widget_visible — câblage effectif)
        st.markdown("---")
        st.markdown("##### Navigation")

        nav_entries = get_navigation(persona_id)
        for entry in nav_entries:
            # Câblage : la nav entry est visible si son widget/page est autorisé
            # On utilise le label comme clé de visibilité (ex: "mon_trajet" → widget)
            widget_key = entry.get("label", "").lower().replace(" ", "_")
            if not pm.is_widget_visible(widget_key):
                continue  # Filtré : invisible pour ce persona

            label = f"{entry.get('icon', '')} {entry.get('label', '')}"
            if st.button(
                label,
                key=f"nav_{entry.get('file', '')}",
                use_container_width=True,
            ):
                try:
                    st.switch_page(f"pages/{entry.get('file', '')}")
                except Exception:
                    st.info(f"Page : {entry.get('file', '')} (à créer)")

        # Pages communes
        st.markdown("---")
        st.markdown("##### Commun")
        for entry in get_common_pages():
            label = f"{entry.get('icon', '')} {entry.get('label', '')}"
            if st.button(
                label,
                key=f"nav_{entry.get('file', '')}",
                use_container_width=True,
            ):
                try:
                    st.switch_page(f"pages/{entry.get('file', '')}")
                except Exception:
                    st.info(f"Page : {entry.get('file', '')} (à créer)")

        # Footer
        st.markdown("---")
        st.caption("LyonFlowFull v0.1.0 — MLOps mobilité Lyon")
