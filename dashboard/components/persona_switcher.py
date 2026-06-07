"""Sélecteur de persona — affichage en cartes ou pills selon le contexte.

Composant principal d'entrée. Affiche 3 cartes (1 par persona) avec :
- Icon + label
- Description courte
- Badge "Protégé" si auth requise
- Bouton "Adopter ce persona"

Le composant est responsive : 3 colonnes en desktop, 1 colonne en mobile.
"""

from __future__ import annotations

import streamlit as st

from src.persona.auth import is_authenticated
from src.persona.manager import (
    get_current_persona,
    is_current_persona_authenticated,
    set_current_persona,
)
from src.persona.personas_loader import list_personas


def render_persona_switcher(layout: str = "cards") -> None:
    """Affiche le sélecteur de persona.

    Args:
        layout: 'cards' (3 colonnes) | 'pills' (bandeau horizontal)
    """
    personas = list_personas()
    current = get_current_persona()

    if layout == "pills":
        _render_pills(personas, current)
    else:
        _render_cards(personas, current)


def _render_cards(personas: list[dict], current: str) -> None:
    """3 cartes côte à côte (ou empilées en mobile)."""
    cols = st.columns(len(personas), gap="medium")
    for col, p in zip(cols, personas):
        is_active = p["id"] == current
        is_locked = p["auth_required"] and not is_authenticated_for(p["id"])
        border_color = p["color_primary"] if is_active else "#333"
        bg_color = p["color_primary"] + "1A" if is_active else "#1A1D24"

        with col:
            st.markdown(
                f"""
                <div style="background:{bg_color};border:2px solid {border_color};
                            border-radius:12px;padding:20px;height:200px;
                            display:flex;flex-direction:column;justify-content:space-between;">
                    <div>
                        <div style="font-size:2.5rem;">{p['icon']}</div>
                        <div style="font-size:1.3rem;font-weight:600;
                                    margin-top:8px;color:{p['color_primary']};">
                            {p['label']}
                        </div>
                        <div style="font-size:0.85rem;opacity:0.7;
                                    margin-top:4px;">{p['short_label']}</div>
                        <div style="font-size:0.9rem;margin-top:12px;opacity:0.85;">
                            {p['description']}
                        </div>
                    </div>
                    <div style="font-size:0.75rem;opacity:0.6;">
                        {('🔒 Protégé' if p['auth_required'] else '🔓 Accès libre')}
                        {'  •  ✅ Actif' if is_active else ''}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_label = "✅ Actif" if is_active else "➡️ Adopter"
            if st.button(
                btn_label,
                key=f"switch_{p['id']}",
                disabled=is_active,
                use_container_width=True,
            ):
                set_current_persona(p["id"])
                st.rerun()
            if is_locked:
                st.caption("⚠️ Mot de passe requis après adoption")


def _render_pills(personas: list[dict], current: str) -> None:
    """Bandes horizontales compactes pour la sidebar."""
    cols = st.columns(len(personas), gap="small")
    for col, p in zip(cols, personas):
        is_active = p["id"] == current
        with col:
            label = f"{p['icon']} {p['label']}"
            if st.button(
                label,
                key=f"pill_{p['id']}",
                disabled=is_active,
                use_container_width=True,
            ):
                set_current_persona(p["id"])
                st.rerun()


def is_authenticated_for(persona_id: str) -> bool:
    """Helper : authentifié pour CE persona spécifiquement.

    Différent de is_authenticated() qui regarde le persona courant.
    Pour le switcher, on veut savoir si un persona est déjà auth.
    """
    # Le session_state d'auth est partagé, donc si on est auth pour un
    # persona protégé, on l'est pour tous. Mais l'auth est invalidée
    # quand on change de persona (voir set_current_persona).
    if persona_id == get_current_persona():
        return is_current_persona_authenticated()
    return False
