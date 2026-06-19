"""Widget — Table des segments interactive.

Segments chargés depuis gold.infrastructure_bottlenecks (croisement bus × trafic).
Sprint 8 — fail loud en prod, zéro mock (DB uniquement).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_infra_bottlenecks
from src.data.db_query import clean_line_label  # Sprint 15+ : libellé lisible des lignes TCL.
from src.data.exceptions import DashboardDataError

# DIAGNOSIS_LABELS est un libellé FR d'un code SQL (cf. infra_bottlenecks.diagnosis),
# pas une métrique inventée — on l'importe toujours.
from src.data.labels import DIAGNOSIS_LABELS  # Sprint 8 : référentiel statique, plus un mock.

_DELAY_THRESHOLD = 120
_SPEED_THRESHOLD = 25


def render_segment_table(line_id: str | None = None, height: int = 400) -> None:
    """Affiche la table interactive des segments."""
    try:
        df = cached_infra_bottlenecks(top=500)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if not df.empty:
        segments = []
        for _, row in df.iterrows():
            delay_s = row.get("bus_delay_seconds", 0) or 0
            speed = row.get("traffic_speed_kmh", 50) or 50
            segments.append({
                "line_id": row.get("line_ref", "?"),
                "name": row.get("segment_id", "—"),
                # Sprint 15+ (audit Pro TCL D3) : libellés FR dans l'UI.
                "bus_state": "En retard" if delay_s > _DELAY_THRESHOLD else "À l'heure",
                "traffic_state": "Congestionné" if speed < _SPEED_THRESHOLD else "Fluide",
                "diagnosis": row.get("diagnosis", "ok"),
                "delay_min": round(delay_s / 60, 1),
                "lat": row.get("lat", 0) or 0,
                "lon": row.get("lng", 0) or 0,
            })
    else:
        # Sprint 8 (2026-06-12) — viré le fallback SEGMENTS (mock).
        st.info("Aucun segment bottleneck — gold.infrastructure_bottlenecks est vide.")
        return

    if line_id:
        segments = [s for s in segments if s["line_id"] == line_id]

    if not segments:
        st.info("Aucun segment.")
        return

    df_display = pd.DataFrame(
        [
            {
                # Sprint 15+ (audit Pro TCL B2) : libellé lisible L66 au lieu
                # de l'identifiant SYTRAL brut (ActIV:Line::66:SYTRAL_h20).
                "Ligne": clean_line_label(s["line_id"]),
                "Segment": s["name"],
                "Bus": s["bus_state"],
                "Trafic": s["traffic_state"],
                "Diagnostic": s["diagnosis"],
                "Retard": s.get("delay_min", 0),
                "Lat": s["lat"],
                "Lon": s["lon"],
            }
            for s in segments
        ]
    )

    diagnostic_filter = st.multiselect(
        "Filtrer par diagnostic",
        list(DIAGNOSIS_LABELS.keys()),
        default=list(DIAGNOSIS_LABELS.keys()),
        format_func=lambda x: DIAGNOSIS_LABELS.get(x, x),
        key="seg_filter_diag",
    )
    df_display = df_display[df_display["Diagnostic"].isin(diagnostic_filter)]

    st.dataframe(
        df_display[["Ligne", "Segment", "Bus", "Trafic", "Diagnostic", "Retard"]],
        use_container_width=True,
        height=height,
        hide_index=True,
    )
