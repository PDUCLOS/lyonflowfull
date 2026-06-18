"""Auto-refresh par persona — cable sur personas.yaml refresh_interval_sec."""

from __future__ import annotations

from streamlit_autorefresh import st_autorefresh

from src.persona.manager import get_current_persona
from src.persona.personas_loader import get_persona_config


def setup_auto_refresh() -> int:
    """Active l'auto-refresh selon le persona courant.

    Intervalles (personas.yaml) : Pro TCL 30s, Usager 60s, Elu 300s.
    Le cache Streamlit (data_cache.py TTLs) evite de re-frapper la DB
    a chaque rerun si le TTL n'a pas expire.
    """
    persona_id = get_current_persona()
    config = get_persona_config(persona_id)
    interval_sec = config.get("refresh_interval_sec", 60)
    return st_autorefresh(
        interval=interval_sec * 1000,
        key=f"autorefresh_{persona_id}",
    )
