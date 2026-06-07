"""Widget — Matrice de corrélation bus × trafic (USP technique).

Affiche les segments en matrice 2D (bus_state × traffic_state) avec
classification en 4 diagnostics :
- ok (vert) : bus à l'heure + trafic fluide
- infra (rouge) : bus retard + trafic bouché
- operations (orange) : bus retard + trafic fluide
- bus_lane_ok (bleu) : bus à l'heure + trafic bouché

Sprint 8 — Charge via data_loader.load_correlation_matrix() pour les paires
bus×trafic. Fallback mock si DB down.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.data_loader import load_correlation_matrix
from src.data.mock.pro_tcl import (
    DIAGNOSIS_LABELS,
    SEGMENTS,
)


def render_correlation_matrix(line_id: str | None = None) -> None:
    """Affiche la matrice de corrélation bus × trafic pour une ou toutes lignes.

    Args:
        line_id: si fourni, filtre sur cette ligne. Sinon, toutes.
    """
    # Charge la matrice de corrélation (DB ou mock)
    corr_df = load_correlation_matrix(force_mock=False)

    # Charge les segments (pour le détail)
    segments = SEGMENTS
    if line_id:
        segments = [s for s in segments if s["line_id"] == line_id]

    if not segments:
        st.info("Aucun segment à analyser.")
        return

    # Compter par diagnostic
    counts = {"ok": 0, "infra": 0, "operations": 0, "bus_lane_ok": 0}
    for s in segments:
        d = s.get("diagnosis", "ok")
        counts[d] = counts.get(d, 0) + 1

    # 4 quadrants visuels
    st.markdown("##### 📊 Matrice bus × trafic")

    quadrants = [
        ("ok", "🟢 Bus à l'heure + 🚗 Fluide", "Aucun problème", "#4CAF50"),
        ("bus_lane_ok", "🔵 Bus à l'heure + 🚗 Bouché", "Voie bus fonctionne", "#2196F3"),
        ("operations", "🟠 Bus retard + 🚗 Fluide", "Problème exploitation", "#FF9800"),
        ("infra", "🔴 Bus retard + 🚗 Bouché", "Problème infrastructure", "#E74C3C"),
    ]
    # 2x2 grid
    for i in range(0, 4, 2):
        cols = st.columns(2)
        for col, (key, title, sub, color) in zip(cols, quadrants[i:i+2]):
            with col:
                n = counts.get(key, 0)
                st.markdown(
                    f"""
                    <div style="background:#1A1D24;border-left:4px solid {color};
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

    # Table détaillée
    st.markdown("##### 📋 Détail des segments")
    df = pd.DataFrame([
        {
            "Ligne": s["line_id"],
            "Segment": s["name"],
            "Bus": "🟢 OK" if s["bus_state"] == "on_time" else "🔴 Retard",
            "Trafic": "🟢 Fluide" if s["traffic_state"] == "fluid" else "🔴 Bloqué",
            "Diagnostic": DIAGNOSIS_LABELS.get(s["diagnosis"], "—"),
            "Retard (min)": s.get("delay_min", 0),
        }
        for s in segments
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Sprint 8 — Heatmap corrélation features (Gold)
    if not corr_df.empty:
        with st.expander("🔬 Matrice corrélation features Gold (vue matérialisée)", expanded=False):
            st.dataframe(corr_df, use_container_width=True, hide_index=True)
