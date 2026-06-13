"""Widget — Matrice de corrélation bus × trafic (USP technique).

Affiche les segments en matrice 2D (bus_state × traffic_state) avec
classification en 4 diagnostics :
- ok (vert) : bus à l'heure + trafic fluide
- infra (rouge) : bus retard + trafic bouché
- operations (orange) : bus retard + trafic fluide
- bus_lane_ok (bleu) : bus à l'heure + trafic bouché

Données chargées depuis gold.infrastructure_bottlenecks (transform
bus_delay × traffic_features). Fallback mock si DB down.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_infra_bottlenecks
from src.data.mock.pro_tcl import (
    DIAGNOSIS_LABELS,
    SEGMENTS,
)

_DELAY_THRESHOLD = 120
_SPEED_THRESHOLD = 25


def _bus_state(delay_s: float) -> str:
    return "delayed" if delay_s > _DELAY_THRESHOLD else "on_time"


def _traffic_state(speed: float) -> str:
    return "jammed" if speed < _SPEED_THRESHOLD else "fluid"


def _bottlenecks_to_segments(df: pd.DataFrame) -> list[dict]:
    """Convert infrastructure_bottlenecks rows to segment dicts."""
    segments = []
    for _, row in df.iterrows():
        delay_s = row.get("bus_delay_seconds", 0) or 0
        speed = row.get("traffic_speed_kmh", 50) or 50
        segments.append(
            {
                "line_id": row.get("line_ref", "?"),
                "name": row.get("segment_id", "—"),
                "bus_state": _bus_state(delay_s),
                "traffic_state": _traffic_state(speed),
                "diagnosis": row.get("diagnosis", "ok"),
                "delay_min": round(delay_s / 60, 1),
                "lat": row.get("lat", 0) or 0,
                "lon": row.get("lng", 0) or 0,
            }
        )
    return segments


def render_correlation_matrix(line_id: str | None = None) -> None:
    """Affiche la matrice de corrélation bus × trafic pour une ou toutes lignes."""
    df = cached_infra_bottlenecks(top=500)

    if not df.empty:
        segments = _bottlenecks_to_segments(df)
    else:
        segments = SEGMENTS

    if line_id:
        segments = [s for s in segments if s.get("line_id") == line_id]

    if not segments:
        st.info("Aucun segment à analyser.")
        return

    counts = {"ok": 0, "infra": 0, "operations": 0, "bus_lane_ok": 0}
    for s in segments:
        d = str(s.get("diagnosis", "ok"))
        counts[d] = counts.get(d, 0) + 1

    st.markdown("##### Matrice bus × trafic")

    quadrants = [
        ("ok", "Bus à l'heure + Fluide", "Aucun problème", COLORS["status_ok"]),
        ("bus_lane_ok", "Bus à l'heure + Bouché", "Voie bus fonctionne", COLORS["status_info"]),
        ("operations", "Bus retard + Fluide", "Problème exploitation", COLORS["status_warning"]),
        ("infra", "Bus retard + Bouché", "Problème infrastructure", COLORS["status_critical"]),
    ]
    for i in range(0, 4, 2):
        cols = st.columns(2)
        for col, (key, title, sub, color) in zip(cols, quadrants[i : i + 2]):
            with col:
                n = counts.get(key, 0)
                st.markdown(
                    f"""
                    <div style="background:var(--bg-card);border-left:4px solid {color};
                                border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                        <div style="font-size:0.85rem;opacity:0.8;">{title}</div>
                        <div style="font-size:1.8rem;font-weight:700;margin:0.2rem 0;">
                            {n} <span style="font-size:0.8rem;font-weight:400;">segments</span>
                        </div>
                        <div style="font-size:0.75rem;opacity:0.6;">{sub}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("##### Détail des segments")
    detail_df = pd.DataFrame(
        [
            {
                "Ligne": s["line_id"],
                "Segment": s["name"],
                "Bus": "OK" if s["bus_state"] == "on_time" else "Retard",
                "Trafic": "Fluide" if s["traffic_state"] == "fluid" else "Bloqué",
                "Diagnostic": DIAGNOSIS_LABELS.get(s["diagnosis"], "—"),
                "Retard (min)": s.get("delay_min", 0),
            }
            for s in segments
        ]
    )
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
