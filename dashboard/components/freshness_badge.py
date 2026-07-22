"""Badge de fraîcheur des données — Axe F.

Affiche en haut de chaque page un badge discret indiquant l'âge des
données et le temps restant avant la prochaine mise à jour. a ajouté l'auto-refresh par persona (Pro TCL 30s, Usager 60s, Élu 300s),
mais l'usager ne sait pas quand la prochaine MAJ arrive. Ce badge rend
l'auto-refresh visible.

Cf. docs/SPEC_SPRINT_20_UX.md §7.1.
"""

from __future__ import annotations

import time

import streamlit as st

from src.persona.manager import get_current_persona

# Intervalle d'auto-refresh par persona (secondes).
# Source : CLAUDE.md auto-refresh par persona.
REFRESH_INTERVALS_SEC: dict[str, int] = {
    "pro_tcl": 30,
    "usager": 60,
    "elu": 300,
}


def seconds_until_next_refresh(persona: str | None) -> int:
    """Calcule le temps restant avant la prochaine MAJ (fonction pure).

    Args:
        persona: identifiant persona (usager, pro_tcl, elu, ou None).

    Returns:
        Secondes restantes avant le prochain cycle d'auto-refresh.
        Retourne 0 si persona inconnu.
    """
    interval = REFRESH_INTERVALS_SEC.get(persona or "", 0)
    if interval <= 0:
        return 0
    # Wrap-around modulo : le temps dans le cycle courant
    return int(interval - (time.time() % interval))


def render_freshness_badge() -> None:
    """Affiche le badge de fraîcheur en haut de la page courante.

    Le badge indique :
    - Le persona courant
    - L'intervalle d'auto-refresh
    - Le temps restant avant la prochaine MAJ
    """
    persona = get_current_persona()
    interval = REFRESH_INTERVALS_SEC.get(persona, 60)
    next_refresh = seconds_until_next_refresh(persona)

    st.markdown(
        f"""
        <div class="lyf-freshness-badge">
            Prochaine MAJ dans <strong>{next_refresh}s</strong>
            · Intervalle : {interval}s
        </div>
        """,
        unsafe_allow_html=True,
    )
