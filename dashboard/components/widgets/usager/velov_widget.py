"""Widget — Disponibilité Vélov des stations proches.

Sprint 8 — binding DB Silver via data_loader (zéro mock) :
* ``stations=None`` → ``data_loader.cached_velov_stations()`` (DB Silver uniquement,
  fail loud via DashboardDataError si DB down)
* Le widget reste rétro-compatible (accepte toujours une liste en arg).

Sprint 10 — affichage des prédictions H+30min next to current state
(``gold.velov_predictions`` via cached_velov_predictions).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import (
    cached_velov_predictions,
    cached_velov_stations,
)


def _build_predictions_lookup(horizon_minutes: int) -> dict[str, int]:
    """Retourne un dict {station_id: predicted_bikes} pour l'horizon donné."""
    df = cached_velov_predictions(horizon_minutes=horizon_minutes)
    if df.empty or "station_id" not in df.columns:
        return {}
    latest = (
        df.sort_values("prediction_timestamp", ascending=False)
        .drop_duplicates(subset=["station_id"])
        .set_index("station_id")["predicted_bikes"]
        .to_dict()
    )
    return {str(k): int(v) for k, v in latest.items() if v is not None}


def render_velov_widget(stations: list | None = None, max_stations: int = 3) -> None:
    """Affiche la dispo Vélov des N stations les plus proches.

    Args:
        stations: liste de stations Vélov. Si None, charge via DB Silver (fail loud).
        max_stations: nombre max de stations à afficher.
    """
    if stations is None:
        stations = cached_velov_stations()

    stations = stations[:max_stations]

    if not stations:
        st.info("Aucune station Vélov disponible — vérifiez le pipeline.")
        return

    # Sprint 8+ (2026-06-12) — focus H+1h. Avant (Sprint 10) : H+30min.
    pred_60 = _build_predictions_lookup(60)

    cols = st.columns(len(stations))
    for col, s in zip(cols, stations):
        bikes = s.get("bikes_available", 0)
        stands = s.get("stands_available", 0)
        station_id = str(s.get("station_id", ""))
        pred = pred_60.get(station_id)

        # Couleur selon dispo
        if bikes == 0:
            color = COLORS["status_critical"]
            status = "❌ Vide"
        elif bikes < 5:
            color = COLORS["status_warning"]
            status = "⚠️ Faible"
        else:
            color = COLORS["status_ok"]
            status = "✅ OK"

        # Prédiction H+1h — delta et icône (Sprint 8+ : focus H+1h)
        if pred is not None:
            delta = pred - bikes
            if delta > 0:
                pred_html = f'<span style="color:{COLORS["status_ok"]};">↗ {pred} (+{delta})</span>'
            elif delta < 0:
                pred_html = f'<span style="color:{COLORS["status_warning"]};">↘ {pred} ({delta})</span>'
            else:
                pred_html = f'<span style="opacity:0.7;">→ {pred}</span>'
            pred_line = f'<div style="font-size:0.7rem;opacity:0.8;margin-top:0.3rem;">H+1h : {pred_html}</div>'
        else:
            pred_line = ""

        with col:
            # Sprint 10 : on utilise st.html() au lieu de st.markdown(unsafe_allow_html=True)
            # car le markdown parser wrappait la partie préd_line (avec un <span>
            # imbriqué) dans un <pre><code>, affichant le HTML brut.
            st.html(
                f"""
                <div class="lyonflow-card" style="border-left:4px solid {color};">
                    <div style="font-size:0.85rem;font-weight:600;">{s.get("name", "—")}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.4rem 0;color:{color};">
                        🚲 {bikes}
                    </div>
                    <div style="font-size:0.75rem;opacity:0.7;">
                        {stands} places libres · {status}
                    </div>
                    {pred_line}
                    <div style="font-size:0.7rem;opacity:0.5;margin-top:0.3rem;">
                        {s.get("distance_m", 0)}m
                    </div>
                </div>
                """
            )
