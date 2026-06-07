"""Authentification par persona.

3 personas, 3 stratégies :
- usager : pas d'auth (accès public)
- pro_tcl : mot de passe en env var PERSONA_PRO_TCL_PASSWORD
- elu : mot de passe en env var PERSONA_ELU_PASSWORD

Le mot de passe est saisi une fois, validé côté serveur (via st.session_state),
et la session est marquée authentifiée jusqu'au logout.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

from src.persona.manager import (
    get_current_persona,
    is_current_persona_authenticated,
    mark_current_persona_authenticated,
)
from src.persona.personas_loader import get_persona_config

_SESSION_AUTH_KEY = "lyonflow_auth"


def _get_expected_password(persona_id: str) -> str | None:
    """Récupère le mot de passe attendu depuis les env vars.

    Returns None si le persona n'a pas d'auth requise.
    Returns la chaîne vide si l'env var est définie mais vide (rejeté).
    """
    pconf = get_persona_config(persona_id)
    env_var = pconf.get("access", {}).get("password_env")
    if not env_var:
        return None
    password = os.getenv(env_var)
    return password if password else None


def authenticate_persona(persona_id: str, password: str) -> bool:
    """Vérifie le mot de passe d'un persona.

    Args:
        persona_id: id du persona
        password: mot de passe saisi par l'utilisateur

    Returns:
        True si valide, False sinon.

    Raises:
        RuntimeError: si l'env var password n'est pas configurée côté serveur.
    """
    expected = _get_expected_password(persona_id)
    if expected is None:
        # Pas d'auth requise pour ce persona
        return True
    if not password:
        return False
    return hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def is_authenticated() -> bool:
    """Retourne True si le persona courant est authentifié."""
    return is_current_persona_authenticated()


def logout() -> None:
    """Déconnecte le persona courant."""
    st.session_state[_SESSION_AUTH_KEY] = False


def require_password() -> None:
    """Affiche un formulaire de mot de passe si l'auth est requise.

    À utiliser dans la page d'accueil pour déverrouiller un persona protégé.
    """
    persona_id = get_current_persona()
    pconf = get_persona_config(persona_id)
    label = pconf.get("label", persona_id)
    icon = pconf.get("icon", "🔒")

    if is_authenticated():
        st.success(f"✅ Connecté en tant que **{icon} {label}**")
        if st.button("Se déconnecter"):
            logout()
            st.rerun()
        return

    # Vérifier que l'env var est configurée
    expected = _get_expected_password(persona_id)
    if expected is None:
        st.error(
            f"⚠️ Auth requise pour **{label}** mais la variable d'environnement "
            f"`{pconf.get('access', {}).get('password_env')}` n'est pas définie "
            f"côté serveur. Contacte l'admin."
        )
        return

    st.info(f"🔐 **{label}** est un espace protégé. Saisis le mot de passe.")
    password = st.text_input("Mot de passe", type="password", key=f"pwd_{persona_id}")
    if st.button("Se connecter", key=f"login_{persona_id}"):
        if authenticate_persona(persona_id, password):
            mark_current_persona_authenticated()
            st.success("Connexion réussie.")
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
