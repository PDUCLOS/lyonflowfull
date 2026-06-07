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

    # Vérification que le persona de la page correspond au persona actif
    if expected_persona and pm.persona_id != expected_persona:
        st.warning(
            f"⚠️ Cette page est destinée au persona "
            f"**{_persona_label(expected_persona)}** mais tu as sélectionné "
            f"**{pm.config.get('label', pm.persona_id)}**."
        )
        if st.button(f"Basculer vers {_persona_label(expected_persona)}"):
            from src.persona.manager import set_current_persona

            set_current_persona(expected_persona)
            st.rerun()
        st.stop()

    # Vérification de l'auth
    pm.guard()

    return pm


def _persona_label(persona_id: str) -> str:
    labels = {"usager": "Usager", "pro_tcl": "Pro TCL", "elu": "Élu"}
    return labels.get(persona_id, persona_id)
