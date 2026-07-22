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
    """Affiche un lien de navigation stylisé vers une page du persona."""
    file = entry.get("file", "")
    label = entry.get("label", "")
    icon = entry.get("icon", "")

    if file:
        # Calcul du highlight : match exact sur le nom de fichier (sans .py)
        # Avant : `_current_page_file() in file` matchait par substring → faux positifs
        # (ex: "Pro_4" matchait dans "Pro_4_Simulateur" ET dans "Pro_4_Correlation" si current="Pro_4")
        current = _current_page_file()
        is_active = bool(current) and (file == current or file == f"{current}.py")
        try:
            if is_active:
                # Marqueur visuel pour la page active
                st.page_link(
                    f"pages/{file}",
                    label=f"▶ {label}",
                    icon=icon,
                )
            else:
                st.page_link(
                    f"pages/{file}",
                    label=label,
                    icon=icon,
                )
        except Exception:
            # Fallback si la page n'existe pas encore
            st.button(f"{icon} {label} (à créer)", key=f"nav_{file}", disabled=True, use_container_width=True)


def render_sidebar_navigation() -> None:
    """Affiche la navigation custom dans la sidebar Streamlit.

    Ordre d'affichage :
    1. En-tête du persona actif (nom + icône)
    2. Groupes de pages du persona avec st.page_link
    3. Pages communes
    4. Footer avec bouton de retour à l'accueil
    """
    from src.persona.personas_loader import list_personas

    pm = PersonaManager()
    persona_id = get_current_persona()

    # Trouver les infos du persona courant
    personas = list_personas()
    current_p = next((p for p in personas if p["id"] == persona_id), None)
    p_label = current_p.get("label", persona_id) if current_p else persona_id
    p_icon = current_p.get("icon", "👤") if current_p else "👤"

    with st.sidebar:
        # 1. Header du persona
        st.markdown(f"### {p_icon} {p_label}")
        st.markdown("---")

        # 2. Pages du persona
        nav_entries = get_navigation(persona_id)
        if not nav_entries:
            st.warning("Aucune page configurée pour ce profil.")
        else:
            grouped = _group_entries(nav_entries)
            for gname, gdata in grouped.items():
                st.markdown(f"**{gdata['icon']} {gname.upper()}**")
                for entry in gdata["entries"]:
                    _render_nav_entry(entry)
                st.write("")  # Espacement

        # 3. Pages communes
        common = get_common_pages()
        if common:
            st.markdown("---")
            st.markdown("**COMMUN**")
            for entry in common:
                _render_nav_entry(entry)

        # 4. Footer & Quitter
        st.markdown("---")
        if st.button("Quitter (retour à l'accueil)", use_container_width=True, type="secondary"):
            # (2026-06-19) — fix bug "Changer de profil ne
            # ramène pas à l'accueil". Avant : ``clear_current_persona_auth``
            # ne clearait que l'auth (mot de passe), laissant le
            # ``_SESSION_KEY = "lyonflow_persona"`` en place. Résultat :
            # Accueil.py détectait un persona actif → renvoyait direct
            # sur la page de re-login au lieu d'afficher l'onboarding.
            # Maintenant : ``clear_current_persona()`` pop le persona ET
            # clear l'auth → retour propre à l'accueil (sélecteur 3 cartes).
            from src.persona.manager import clear_current_persona

            clear_current_persona()
            st.switch_page("Accueil.py")

        from src.config import get_settings

        st.caption(f"LyonFlow v{get_settings().app_version}")
