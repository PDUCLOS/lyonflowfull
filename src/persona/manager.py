"""Gestion du persona courant dans la session Streamlit.

State management simple basé sur st.session_state. Le persona sélectionné
est persistant pendant la session navigateur, mais pas au-delà.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.persona.personas_loader import (
    get_persona_config,
    list_personas,
    load_personas_config,
)

_SESSION_KEY = "lyonflow_persona"
_SESSION_AUTH_KEY = "lyonflow_auth"  # dict[persona_id, bool] depuis le fix UX persona


def _auth_state() -> dict[str, bool]:
    """Retourne le dict d'auth par persona. Migre l'ancien format (bool global).

    Avant : st.session_state["lyonflow_auth"] = bool partagé (perdu au switch).
    Maintenant : dict {persona_id: bool}, persisté par persona pendant la session.
    """
    raw = st.session_state.get(_SESSION_AUTH_KEY)
    if isinstance(raw, dict):
        return raw
    migrated: dict[str, bool] = {}
    if raw is True:
        current = st.session_state.get(_SESSION_KEY)
        if current:
            migrated[current] = True
    st.session_state[_SESSION_AUTH_KEY] = migrated
    return migrated


def get_current_persona() -> str:
    """Retourne l'id du persona actuellement sélectionné.

    Si aucun persona n'est sélectionné, retourne le default_persona du YAML.
    """
    config = load_personas_config()
    default = config.get("default_persona", "usager")
    return st.session_state.get(_SESSION_KEY, default)


def set_current_persona(persona_id: str) -> None:
    """Change le persona actif sans toucher à l'auth des autres personas.

    Args:
        persona_id: 'usager' | 'pro_tcl' | 'elu'

    Raises:
        ValueError: si le persona n'existe pas.
    """
    available = [p["id"] for p in list_personas()]
    if persona_id not in available:
        raise ValueError(f"Persona '{persona_id}' inconnu. Disponibles : {available}")
    st.session_state[_SESSION_KEY] = persona_id
    _auth_state()  # garantit l'init du dict (migration si besoin)


def get_current_persona_config() -> dict[str, Any]:
    """Retourne la config complète du persona courant."""
    return get_persona_config(get_current_persona())


def is_current_persona_authenticated() -> bool:
    """Vérifie si l'auth du persona courant a été validée."""
    return bool(_auth_state().get(get_current_persona(), False))


def mark_current_persona_authenticated() -> None:
    """Marque le persona courant comme authentifié (utilisé par auth.py)."""
    _auth_state()[get_current_persona()] = True


def clear_current_persona_auth() -> None:
    """Logout du persona courant (laisse les autres personas intacts)."""
    _auth_state().pop(get_current_persona(), None)


def clear_current_persona() -> None:
    """Retire le persona actif de la session, permettant de revenir à l'accueil."""
    import streamlit as st

    st.session_state.pop(_SESSION_KEY, None)
    clear_current_persona_auth()


class PersonaManager:
    """Façade pour la gestion de persona dans les pages.

    Usage typique dans une page :
        pm = PersonaManager()
        pm.guard()  # bloque la page si persona ou auth invalide
        pm.render_sidebar_nav()
    """

    def __init__(self) -> None:
        self.persona_id = get_current_persona()
        self.config = get_current_persona_config()
        self.is_authenticated = is_current_persona_authenticated()

    @property
    def color_primary(self) -> str:
        return self.config.get("color_primary", "#666")

    @property
    def theme(self) -> dict[str, Any]:
        return self.config.get("theme", {})

    @property
    def default_filters(self) -> dict[str, Any]:
        return self.config.get("default_filters", {})

    @property
    def landing_page(self) -> str:
        return self.config.get("landing_page", "")

    def guard(self) -> None:
        """Stoppe l'exécution si l'auth est requise mais non validée.

        À appeler en début de chaque page protégée. Lève st.stop() si
        l'utilisateur n'a pas le bon persona ou n'est pas authentifié.
        """
        access = self.config.get("access", {})
        if access.get("auth_required", False) and not self.is_authenticated:
            st.error(
                f"🔒 Accès restreint — Persona **{self.config.get('label', self.persona_id)}** "
                f"protégé par mot de passe. Sélectionne ce persona depuis l'accueil."
            )
            st.stop()

    def is_widget_visible(self, widget_name: str) -> bool:
        """Vérifie si un widget est visible pour le persona courant."""
        hidden = set(self.config.get("hidden_widgets", []))
        return widget_name not in hidden

    def render_sidebar_header(self) -> None:
        """Affiche un badge persona en haut de la sidebar."""
        st.sidebar.markdown(
            f"""
            <div style="background:{self.color_primary}22;border-left:4px solid {self.color_primary};
                        padding:8px 12px;border-radius:4px;margin-bottom:12px;">
                <div style="font-size:1.4rem;font-weight:600;">
                    {self.config.get("icon", "👤")} {self.config.get("label", self.persona_id)}
                </div>
                <div style="font-size:0.85rem;opacity:0.8;">
                    {self.config.get("description", "")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
