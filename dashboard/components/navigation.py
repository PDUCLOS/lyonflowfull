"""Navigation sidebar adaptée au persona courant.

Remplace la navigation native Streamlit (cachée via `.streamlit/config.toml`,
`hideSidebarNav = true`) par une navigation custom qui :

- Affiche un badge persona en haut (icône + label + courte description)
- Propose un bouton "← Accueil" pour changer de persona (UX : pas d'expander
  caché, retour à l'accueil = point d'entrée unique pour switcher)
- N'affiche que les pages du persona actif (filtrage strict via
  `get_navigation(persona_id)` depuis `config/personas.yaml`)
- Groupe les pages en sous-sections (champ `group:` dans le YAML)
- Ajoute les pages communes (RGPD, À propos) en bas
- Met en évidence la page active

L'auto-switch de persona est géré par `persona_guard.py` (si l'URL d'une page
Usager est appelée avec persona=pro_tcl, le guard force le switch vers usager
ou renvoie vers Accueil si auth requise).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import streamlit as st

from src.persona.manager import PersonaManager, get_current_persona
from src.persona.personas_loader import get_common_pages, get_navigation

# Chemin de la page d'accueil (utilisé par le bouton "← Accueil")
_HOME_PAGE = "Accueil.py"


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


def _current_page_file() -> str:
    """Retourne le nom de fichier (sans extension) de la page courante, ou ''.

    Stratégie : la valeur est stockée par chaque page dans
    `st.session_state["_nav_current_page"]` au tout début. Fallback vide
    si pas set → aucun bouton mis en évidence (cosmétique, pas bloquant).
    """
    return str(st.session_state.get("_nav_current_page", ""))


def _render_nav_entry(entry: dict[str, Any]) -> None:
    """Affiche un bouton de navigation vers une page du persona."""
    file = entry.get("file", "")
    label = f"{entry.get('icon', '')} {entry.get('label', '')}".strip()

    # Mise en évidence de la page active (style CSS léger via markdown)
    is_active = file and _current_page_file() in file
    btn_type = "primary" if is_active else "secondary"

    if st.button(
        label,
        key=f"nav_{file}",
        use_container_width=True,
        type=btn_type,
    ):
        try:
            st.switch_page(f"pages/{file}")
        except Exception:
            st.info(f"Page : {file} (à créer)")


def _render_persona_switcher(pm: PersonaManager) -> None:
    """Workspace switcher (dropdown) en haut de la sidebar."""
    from src.persona.personas_loader import list_personas
    from dashboard.components.persona_switcher import _route_after_switch

    personas = list_personas()
    current = pm.persona_id
    options = [p["id"] for p in personas]

    def format_func(p_id: str) -> str:
        p = next(x for x in personas if x["id"] == p_id)
        return f"{p.get('icon', '👤')} {p.get('label', p_id)}"

    st.sidebar.markdown("##### 🏢 Espace de travail")
    selected = st.sidebar.selectbox(
        "Changer de Persona",
        options=options,
        index=options.index(current) if current in options else 0,
        format_func=format_func,
        label_visibility="collapsed",
        key="nav_persona_switcher"
    )

    if selected != current:
        _route_after_switch(selected)


def render_sidebar_navigation() -> None:
    """Affiche la navigation custom dans la sidebar Streamlit.

    Ordre d'affichage :
    1. Card persona (badge)
    2. Bouton "← Accueil" (pour switcher)
    3. Groupes de pages du persona (premier ouvert)
    4. Pages communes (dans un expander "Commun")
    5. Footer version
    """
    pm = PersonaManager()
    persona_id = get_current_persona()

    with st.sidebar:
        # 1. Switcher de workspace/persona
        _render_persona_switcher(pm)

        st.sidebar.markdown("---")
        st.sidebar.markdown("##### Navigation")

        # 3. Pages du persona, filtrées strictement par get_navigation(persona_id)
        nav_entries = get_navigation(persona_id)
        if not nav_entries:
            st.sidebar.warning(
                f"Aucune page configurée pour le persona **{persona_id}**.\n"
                f"Vérifie `config/personas.yaml` → `navigation.{persona_id}`."
            )
        else:
            grouped = _group_entries(nav_entries)
            for i, (gname, gdata) in enumerate(grouped.items()):
                header = f"{gdata['icon']} {gname}".strip()
                with st.sidebar.expander(header, expanded=(i == 0)):
                    for entry in gdata["entries"]:
                        _render_nav_entry(entry)

        # 4. Pages communes
        common = get_common_pages()
        if common:
            st.sidebar.markdown("---")
            with st.sidebar.expander("🛠️ Commun", expanded=False):
                for entry in common:
                    _render_nav_entry(entry)

        # 5. Footer
        st.sidebar.markdown("---")
        st.sidebar.caption("LyonFlowFull v0.3.0 — MLOps mobilité Lyon")
