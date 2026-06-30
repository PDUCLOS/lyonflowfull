"""Authentification par persona — version démo simplifiée.

3 personas, 3 stratégies simplification démo) :
- usager : pas d'auth (accès public)
- pro_tcl : mot de passe (env var PERSONA_PRO_TCL_PASSWORD, défaut "demo2026")
- elu : mot de passe (env var PERSONA_ELU_PASSWORD, défaut "demo2026")

**Mode démo** , 2026-06-12) : le projet est une démo Jedha,
les mots de passe sont volontairement simples et hardcodés.
En production réelle (post-Jedha), il faudra :
- Hasher les mots de passe (bcrypt déjà utilisé côté API)
- Les sortir du repo public (variables d'env injectées au déploiement)
- Implémenter une rotation automatique

Le mot de passe est saisi une fois, validé côté serveur (via
``st.session_state``), et la session est marquée authentifiée
jusqu'au logout.

 sécurité :
- ``hmac.compare_digest`` (constant-time comparison, pas d'attaque timing)
- ``bcrypt`` côté API FastAPI
- Aucune fuite du mot de passe dans les logs
"""

from __future__ import annotations

import hmac
import logging

import streamlit as st

from src.persona.manager import (
    get_current_persona,
    is_current_persona_authenticated,
    mark_current_persona_authenticated,
)
from src.persona.personas_loader import get_persona_config

logger = logging.getLogger(__name__)

_SESSION_AUTH_KEY = "lyonflow_auth"

# Mot de passe démo par défaut simplification démo Jedha).
# En production réelle, ces valeurs NE DOIVENT PAS être dans le repo :
# les valeurs réelles sont injectées via les env vars au déploiement.
_DEMO_PASSWORD = "demo2026"  # nosec B105


def _get_expected_password(persona_id: str) -> str | None:
    """Récupère le mot de passe attendu.

    (2026-06-16) — Force ``_DEMO_PASSWORD`` (toujours
      ``demo2026``). Les env vars ``PERSONA_*_PASSWORD`` du .env sont
      ignorées volontairement pour que la démo Jedha fonctionne partout
      avec le même mot de passe.

      Si on veut remettre l'override par env var, il faudra flagger ça
      explicitement (variable d'env ``LYONFLOW_AUTH_USE_ENV_PASSWORD=1``).

      Returns:
          None si le persona n'a pas d'auth requise (usager).
          Chaîne attendue sinon (= _DEMO_PASSWORD).
    """
    pconf = get_persona_config(persona_id)
    if not pconf.get("access", {}).get("password_env"):
        return None
    return _DEMO_PASSWORD


def authenticate_persona(persona_id: str, password: str) -> bool:
    """Vérifie le mot de passe d'un persona.

    Args:
        persona_id: id du persona
        password: mot de passe saisi par l'utilisateur

    Returns:
        True si valide, False sinon.
    """
    expected = _get_expected_password(persona_id)
    if expected is None:
        # Pas d'auth requise pour ce persona (usager)
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

    pour la démo, on affiche le mot de passe par défaut
      dans l'info box (sous l'input) pour faciliter les tests Jedha.
      À retirer en production réelle.
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

    # Vérifier que l'env var est configurée (sinon warning)
    expected = _get_expected_password(persona_id)
    if expected is None:
        st.error(
            f"⚠️ Auth requise pour **{label}** mais la variable d'environnement "
            f"`{pconf.get('access', {}).get('password_env')}` n'est pas définie "
            f"côté serveur. Contacte l'admin."
        )
        return

    st.info(f"🔐 **{label}** est un espace protégé. Saisis le mot de passe.")
    # démo : on affiche le mdp par défaut dans une info box
    # (à retirer en prod).
    with st.expander("Information Aide démo (mots de passe par défaut)"):
        st.markdown(f"**Mot de passe démo Jedha** : `{_DEMO_PASSWORD}`")
        st.caption(
            "Cette aide est affichée uniquement parce que c'est une démo Jedha. "
            "En production réelle, les mots de passe seront haschés et stockés "
            "hors du repo public."
        )
    password = st.text_input("Mot de passe", type="password", key=f"pwd_{persona_id}")
    if st.button("Se connecter", key=f"login_{persona_id}"):
        if authenticate_persona(persona_id, password):
            mark_current_persona_authenticated()
            st.success("Connexion réussie.")
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
