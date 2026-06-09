"""Guard de page — bloque l'accès si persona non autorisé.

À appeler en TOUT PREMIER dans chaque page Streamlit. Vérifie :
1. Le persona de la page correspond au persona actif
2. Si auth requise, l'utilisateur est authentifié

Si KO, affiche un message et st.stop().
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

from src.persona.manager import PersonaManager

# Mapping page file → persona attendu
# Mis à jour manuellement quand on ajoute une page
_PAGE_TO_PERSONA = {
    "Usager_": "usager",
    "Pro_": "pro_tcl",
    "Elu_": "elu",
}

PersonaId = Literal["usager", "pro_tcl", "elu"]


def apply_persona_guard(expected_persona: PersonaId | None = None) -> PersonaManager:
    """Applique le guard de persona en début de page.

    Args:
        expected_persona: si fourni, vérifie que la page est bien destinée
                          à ce persona. Sinon, inféré depuis le nom du fichier.

    Returns:
        PersonaManager configuré pour la page (déjà garanti valide).
    """
    pm = PersonaManager()

    # Inférence depuis le nom de fichier si pas fourni
    caller_file = ""
    if expected_persona is None:
        try:
            import inspect

            frame = inspect.currentframe()
            caller_file = frame.f_back.f_code.co_filename
            for prefix, persona_id in _PAGE_TO_PERSONA.items():
                if prefix in caller_file:
                    expected_persona = persona_id
                    break
        except Exception:
            pass

    # Tracker la page courante pour la mise en évidence dans la nav
    if caller_file:
        st.session_state["_nav_current_page"] = caller_file.rsplit("/", 1)[-1].removesuffix(".py")

    # Mismatch persona/page : auto-switch silencieux (UX > friction)
    # Si auth requise pour le nouveau persona et pas encore faite → renvoi à l'accueil
    if expected_persona and pm.persona_id != expected_persona:
        from src.persona.manager import (
            is_current_persona_authenticated,
            set_current_persona,
        )
        from src.persona.personas_loader import get_persona_config

        set_current_persona(expected_persona)
        expected_config = get_persona_config(expected_persona)
        auth_required = expected_config.get("access", {}).get("auth_required", False)
        if auth_required and not is_current_persona_authenticated():
            try:
                st.switch_page("Accueil.py")
            except Exception:
                st.rerun()
            st.stop()
        st.rerun()

    # Vérification de l'auth
    pm.guard()

    return pm


def _persona_label(persona_id: str) -> str:
    labels = {"usager": "Usager", "pro_tcl": "Pro TCL", "elu": "Élu"}
    return labels.get(persona_id, persona_id)
