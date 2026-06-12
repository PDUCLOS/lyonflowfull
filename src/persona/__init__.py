"""Module persona — gestion des personas, auth, routing.

Ce module centralise toute la logique liée aux 3 personas LyonFlowFull :
chargement de la config, auth par mot de passe, application des règles
d'affichage par persona, etc.
"""

from src.persona.auth import authenticate_persona, is_authenticated, logout
from src.persona.manager import PersonaManager, get_current_persona, set_current_persona
from src.persona.personas_loader import (
    get_persona_config,
    list_personas,
    load_personas_config,
)

__all__ = [
    "PersonaManager",
    "authenticate_persona",
    "get_current_persona",
    "get_persona_config",
    "is_authenticated",
    "list_personas",
    "load_personas_config",
    "logout",
    "set_current_persona",
]
