"""Composant transversal — Bandeau sécurité Vélov (pollution + canicule).

Centralise la lecture de ``gold.v_velov_safety_advisory`` (migration_045,
2026-07-05) pour les 3 widgets qui proposent le mode Vélov : weather_widget,
velov_trip, velov_widget. Décision projet (brainstorming 2026-07-05) : on
avertit mais on ne bloque jamais le mode — l'usager reste libre de choisir,
mais LyonFlow ne peut pas rester silencieux quand l'État déconseille le
sport en extérieur (pollution dégradée ou vigilance canicule).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_velov_safety_advisory


def get_velov_safety_severity() -> tuple[int, dict]:
    """Retourne (severity, advisory) — 0=ok/unknown, 1=warning, 2=severe.

    Ne lève jamais : ``get_velov_safety_advisory`` (db_query) dégrade déjà
    vers un advisory ``status="unknown"`` en cas de panne DB (neutre, pas un
    faux "ok" ni un blocage du mode Vélov).
    """
    advisory = cached_velov_safety_advisory()
    severity = {"severe": 2, "warning": 1}.get(advisory.get("status"), 0)
    return severity, advisory


def render_velov_safety_banner() -> int:
    """Affiche un bandeau d'avertissement si pollution/canicule dégradée.

    Returns:
        La sévérité (0/1/2), pour que l'appelant puisse l'utiliser dans son
        propre calcul d'affichage (ex. weather_widget combine avec pluie/vent).
    """
    severity, advisory = get_velov_safety_severity()
    reason = advisory.get("reason")
    if severity == 2 and reason:
        st.error(f"{reason} — l'État déconseille le sport en extérieur. Privilégiez le TC ou la marche courte.")
    elif severity == 1 and reason:
        st.warning(f"{reason} — évitez l'effort prolongé à vélo, préférez le TC si possible.")
    return severity
