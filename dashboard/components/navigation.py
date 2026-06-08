"""Navigation sidebar adaptée au persona courant.

Remplace la navigation native Streamlit par une navigation custom qui :
- N'affiche que les pages du persona actif
- Groupe les pages en sous-sections (champ `group:` dans personas.yaml)
- Ajoute les pages communes (RGPD, À propos) en bas
- Affiche un badge persona en haut
- Propose le switcher de persona en haut
- Filtre via pm.is_widget_visible() (câblage du feature `hidden_widgets`)
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import streamlit as st

from src.persona.manager import PersonaManager, get_current_persona
from src.persona.personas_loader import get_common_pages, get_navigation


def _group_entries(entries: list[dict[str, Any]]) -> OrderedDict[str, dict[str, Any]]:
    """Regroupe les entries par champ `group:` (ordre = première apparition)."""
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for e in entries:
        gname = e.get("group", "Général")
        gicon = e.get("group_icon", "")
        if gname not in groups:
            groups[gname] = {"icon": gicon, "entries": []}
        groups[gname]["entries"].append(e)
    return groups


def _render_nav_entry(entry: dict[str, Any]) -> None:
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

        st.markdown("---")
        st.markdown("##### Navigation")

        nav_entries = get_navigation(persona_id)
        # Filtre par visibilité widget
        visible = [e for e in nav_entries if pm.is_widget_visible(e.get("label", "").lower().replace(" ", "_"))]
        grouped = _group_entries(visible)

        # Render chaque groupe dans un expander (le premier déplié)
        for i, (gname, gdata) in enumerate(grouped.items()):
            header = f"{gdata['icon']} {gname}".strip()
            with st.expander(header, expanded=(i == 0)):
                for entry in gdata["entries"]:
                    _render_nav_entry(entry)

        # Pages communes
        st.markdown("---")
        with st.expander("🛠️ Commun", expanded=False):
            for entry in get_common_pages():
                _render_nav_entry(entry)

        # Footer
        st.markdown("---")
        st.caption("LyonFlowFull v0.3.0 — MLOps mobilité Lyon")
