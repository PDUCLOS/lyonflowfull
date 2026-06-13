"""Widget — Table des segments interactive.

Segments chargés depuis gold.infrastructure_bottlenecks (croisement bus × trafic).
Fallback mock si DB down.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_infra_bottlenecks
from src.data.mock.pro_tcl import DIAGNOSIS_LABELS, SEGMENTS

_DELAY_THRESHOLD = 120
_SPEED_THRESHOLD = 25


def render_segment_table(line_id: str | None = None, height: int = 400) -> None:
    """Affiche la table interactive des segments."""
    df = cached_infra_bottlenecks(top=500)

    if not df.empty:
        segments = []
        for _, row in df.iterrows():
            delay_s = row.get("bus_delay_seconds", 0) or 0
            speed = row.get("traffic_speed_kmh", 50) or 50
            segments.append(
                {
                    "line_id": row.get("line_ref", "?"),
                    "name": row.get("segment_id", "—"),
                    "bus_state": "delayed" if delay_s > _DELAY_THRESHOLD else "on_time",
                    "traffic_state": "jammed" if speed < _SPEED_THRESHOLD else "fluid",
                    "diagnosis": row.get("diagnosis", "ok"),
                    "delay_min": round(delay_s / 60, 1),
                    "lat": row.get("lat", 0) or 0,
                    "lon": row.get("lng", 0) or 0,
                }
            )
    else:
        segments = SEGMENTS

    if line_id:
        segments = [s for s in segments if s["line_id"] == line_id]

    if not segments:
        st.info("Aucun segment.")
        return

    df_display = pd.DataFrame(
        [
            {
                "Ligne": s["line_id"],
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
