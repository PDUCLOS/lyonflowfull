"""Widget — Heatmap OTP Plotly (lignes × heures).

Sprint 8 — Charge via data_loader.cached_otp_heatmap_data() (vue Gold.
mv_otp_grid_7d ou équivalent). Fallback mock si DB down.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_otp_heatmap_data
from src.data.mock.pro_tcl import LINE_BASE_OTP, OTP_GRID


def render_otp_heatmap(otp_data: dict | None = None, days: int = 1, height: int = 500) -> None:
    """Affiche la heatmap OTP Plotly (lignes × heures).

    Args:
        otp_data: dict {line_id: {date: [otp_h0, otp_h1, ...]}}. Si None, charge via data_loader.
        days: nombre de jours à moyenner (1 = aujourd'hui, 7 = moyenne 7j)
        height: hauteur du graphique.
    """
    if otp_data is None:
        # Tente DB d'abord (Gold mv_otp_grid), fallback mock
        df = cached_otp_heatmap_data(force_mock=False)
        if not df.empty:
            # Reconstruit le format {line_id: {date: [otp_per_hour]}}
            otp_data = {}
            for _, row in df.iterrows():
                line_id = row["line_id"]
                date = str(row.get("date", ""))
                if line_id not in otp_data:
                    otp_data[line_id] = {}
                # On a (line_id, date, hour, otp_pct) → on agrège par date
                if date not in otp_data[line_id]:
                    otp_data[line_id][date] = [0.0] * 24
                otp_data[line_id][date][int(row["hour"])] = float(row["otp_pct"])
        else:
            otp_data = OTP_GRID

    # Calculer la moyenne
    lines = sorted(otp_data.keys(), key=lambda lid: LINE_BASE_OTP.get(lid, 0), reverse=True)
    dates = sorted(otp_data[lines[0]].keys()) if lines else []

    if days == 1:
        selected_dates = dates[:1]
    else:
        selected_dates = dates[:days]

    # Construire la matrice : lignes × heures
    z_data = []
    text_data = []
    for line_id in lines:
        row = []
        text_row = []
        for h in range(24):
            values = [otp_data[line_id].get(d, [85.0] * 24)[h] for d in selected_dates]
            avg = sum(values) / len(values) if values else 85.0
            row.append(round(avg, 1))
            text_row.append(f"{avg:.0f}%")
        z_data.append(row)
        text_data.append(text_row)

    try:
        import plotly.graph_objects as go

        fig = go.Figure(
            data=go.Heatmap(
                z=z_data,
                x=[f"{h}h" for h in range(24)],
                y=lines,
                colorscale=[
                    [0.0, COLORS["status_critical"]],  # rouge si <70
                    [0.3, COLORS["status_warning"]],  # orange 70-80
                    [0.6, COLORS["chart_yellow"]],  # jaune 80-90
                    [1.0, COLORS["status_ok"]],  # vert >90
                ],
                zmin=60,
                zmax=98,
                text=text_data,
                texttemplate="%{text}",
                textfont={"size": 10},
                colorbar={"title": "OTP %"},
                hovertemplate="<b>%{y}</b> à %{x}<br/>OTP: %{z}%<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"OTP par ligne × heure ({"aujourd'hui" if days == 1 else f'moyenne {days}j'})",
            xaxis_title="Heure",
            yaxis_title="Ligne",
            height=height,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        # Fallback
        df = pd.DataFrame(z_data, index=lines, columns=[f"{h}h" for h in range(24)])
        st.dataframe(df.style.background_gradient(cmap="RdYlGn", vmin=60, vmax=98), height=height)


def render_otp_heatmap_mini(otp_data: dict | None = None, height: int = 200) -> None:
    """Version compacte pour PCC Live (moins de détails)."""
    render_otp_heatmap(otp_data, days=1, height=height)
