"""Module persona — gestion des personas, auth, routing.

Ce module centralise toute la logique liée aux 3 personas LyonFlowFull :
chargement de la config, auth par mot de passe, application des règles
d'affichage par persona, etc.
"""

from src.persona.personas_loader import (
    load_personas_config,
    get_persona_config,
    list_personas,
)
from src.persona.manager import PersonaManager, get_current_persona, set_current_persona
from src.persona.auth import authenticate_persona, is_authenticated, logout

__all__ = [
    "load_personas_config",
    "get_persona_config",
    "list_personas",
    "PersonaManager",
    "get_current_persona",
    "set_current_persona",
    "authenticate_persona",
    "is_authenticated",
    "logout",
]
