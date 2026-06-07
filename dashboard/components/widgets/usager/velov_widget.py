"""Widget — Disponibilité Vélov des stations proches.

Sprint 6 — binding DB Silver via data_loader :
* ``stations=None`` → ``data_loader.load_velov_stations()`` (DB Silver ou mock)
* Le widget reste rétro-compatible (accepte toujours une liste en arg).
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_velov_stations


def render_velov_widget(stations: list | None = None, max_stations: int = 3) -> None:
    """Affiche la dispo Vélov des N stations les plus proches.

    Args:
        stations: liste de stations Vélov. Si None, tente DB → fallback mock.
        max_stations: nombre max de stations à afficher.
    """
    if stations is None:
        stations = load_velov_stations(force_mock=False)

    stations = stations[:max_stations]

    if not stations:
        st.info("Aucune station Vélov disponible — vérifiez le pipeline.")
        return

    cols = st.columns(len(stations))
    for col, s in zip(cols, stations):
        bikes = s.get("bikes_available", 0)
        stands = s.get("stands_available", 0)

        # Couleur selon dispo
        if bikes == 0:
            color = "#E74C3C"
            status = "❌ Vide"
        elif bikes < 5:
            color = "#FF9800"
            status = "⚠️ Faible"
        else:
            color = "#4CAF50"
            status = "✅ OK"

        with col:
            st.markdown(
                f"""
                <div class="lyonflow-card" style="border-left:4px solid {color};">
                    <div style="font-size:0.85rem;font-weight:600;">{s.get('name', '—')}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.4rem 0;color:{color};">
                        🚲 {bikes}
                    </div>
                    <div style="font-size:0.75rem;opacity:0.7;">
                        {stands} places libres · {status}
                    </div>
                    <div style="font-size:0.7rem;opacity:0.5;margin-top:0.3rem;">
                        {s.get('distance_m', 0)}m
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
