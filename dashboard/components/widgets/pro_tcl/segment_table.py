"""Widget — Table des segments interactive.

Sprint 8 — Segments chargés via data_loader.cached_segments() (silver.
trafic_segments_clean). Fallback mock si DB down.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_segments
from src.data.mock.pro_tcl import DIAGNOSIS_LABELS, SEGMENTS


def render_segment_table(line_id: str | None = None, height: int = 400) -> None:
    """Affiche la table interactive des segments.

    Args:
        line_id: si fourni, filtre. Sinon, tous.
        height: hauteur de la table.
    """
    # Tente DB d'abord
    df_seg = cached_segments(force_mock=False)
    if not df_seg.empty:
        # Adapte au format attendu (mock)
        segments = [
            {
                "line_id": row.get("channel_id", "?").split("_")[0] if row.get("channel_id") else "?",
                "name": row["segment_id"],
                "bus_state": "—",  # pas dans la table segments de base
                "traffic_state": "—",
                "diagnosis": "ok",  # sera enrichi par jointure dans Sprint 9
                "delay_min": 0,
                "lat": row.get("lat_start", 0),
                "lon": row.get("lng_start", 0),
            }
            for _, row in df_seg.iterrows()
        ]
    else:
        segments = SEGMENTS
    if line_id:
        segments = [s for s in segments if s["line_id"] == line_id]

    if not segments:
        st.info("Aucun segment.")
        return

    df = pd.DataFrame(
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

    # Filtre par diagnostic
    diagnostic_filter = st.multiselect(
        "Filtrer par diagnostic",
        list(DIAGNOSIS_LABELS.keys()),
        default=list(DIAGNOSIS_LABELS.keys()),
        format_func=lambda x: DIAGNOSIS_LABELS.get(x, x),
        key="seg_filter_diag",
    )
    df = df[df["Diagnostic"].isin(diagnostic_filter)]

    st.dataframe(
        df[["Ligne", "Segment", "Bus", "Trafic", "Diagnostic", "Retard"]],
        use_container_width=True,
        height=height,
        hide_index=True,
    )
