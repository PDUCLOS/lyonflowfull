"""Widget — Heatmap OTP Plotly (lignes × heures).

Sprint 8 — Charge via data_loader.cached_otp_heatmap_data() (vue Gold
mv_otp_heatmap, 4416 triplets). Pas de mock — la DB est la source
unique de vérité (fail loud si DB down).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_otp_heatmap_data


def render_otp_heatmap(otp_data: dict | None = None, days: int = 1, height: int = 500) -> None:
    """Affiche la heatmap OTP Plotly (lignes × heures).

    Args:
        otp_data: dict {line_id: {date: [otp_h0, otp_h1, ...]}}. Si None, charge via data_loader.
        days: nombre de jours à moyenner (1 = aujourd'hui, 7 = moyenne 7j)
        height: hauteur du graphique.
    """
    if otp_data is None:
        # Charge depuis la DB (Gold mv_otp_grid) — fail loud si indispo
        df = cached_otp_heatmap_data()
        if not df.empty:
            # Reconstruit le format {line_id: {date: [otp_per_hour]}}
            # Sprint 11+ — on garde un dict parallèle ``line_labels`` pour
            # afficher ``"L66"`` plutôt que ``"ActIV:Line::66:SYTRAL"``.
            otp_data = {}
            line_labels: dict[str, str] = {}
            for _, row in df.iterrows():
                line_id = row["line_id"]
                date = str(row.get("date", ""))
                if line_id not in otp_data:
                    otp_data[line_id] = {}
                line_labels[line_id] = row.get("line_label") or line_id
                # On a (line_id, date, hour, otp_pct) → on agrège par date
                if date not in otp_data[line_id]:
                    otp_data[line_id][date] = [0.0] * 24
                otp_data[line_id][date][int(row["hour"])] = float(row["otp_pct"])
        else:
            # Sprint 8 (2026-06-12) — viré le fallback OTP_GRID (mock).
            # Si la vue est vide, le widget affiche un message et return.
            st.info("Aucune donnée OTP — gold.mv_otp_heatmap est vide.")
            return
    else:
        line_labels = {}  # mode pré-calculé : pas de labels dispo

    # Calculer la moyenne
    # Sprint 8 — tri par nombre de dates observées (proxy activité),
    # plus besoin de LINE_BASE_OTP (mock).
    def _n_dates(lid: str) -> int:
        return len(otp_data.get(lid, {}))

    lines_raw = sorted(otp_data.keys(), key=_n_dates, reverse=True)
    # Sprint 11+ — affiche le libellé lisible sur l'axe Y
    # (le ``line_id`` brut reste la clé interne du dict).
    lines = [line_labels.get(lid, lid) for lid in lines_raw]
    dates = sorted(otp_data[lines_raw[0]].keys()) if lines_raw else []

    if days == 1:
        selected_dates = dates[:1]
    else:
        selected_dates = dates[:days]

    # Construire la matrice : lignes × heures
    # Sprint 9+ (2026-06-17) — viré le fallback magique ``[85.0] * 24`` qui
    # masquait l'absence de données. Quand une date manque, on moyenne sur
    # les dates présentes (au lieu d'inventer un OTP à 85%).
    z_data = []
    text_data = []
    for line_id in lines_raw:  # itère sur la clé brute (``ActIV:Line::...``)
        row = []
        text_row = []
        for h in range(24):
            values = [
                otp_data[line_id][d][h]
                for d in selected_dates
                if d in otp_data[line_id] and h < len(otp_data[line_id][d])
            ]
            if values:
                avg = sum(values) / len(values)
                row.append(round(avg, 1))
                text_row.append(f"{avg:.0f}%")
            else:
                # Pas de données : None (Plotly affichera un trou dans la heatmap)
                # plutôt qu'un faux 85%.
                row.append(None)
                text_row.append("—")
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
                    [0.0, COLORS["status_critical"]],    # < 60% mediocre
                    [0.395, COLORS["status_warning"]],   # 75% = seuil "bon"
                    [0.789, COLORS["chart_yellow"]],     # 90% = seuil "excellent"
                    [1.0, COLORS["status_ok"]],          # 98% vert
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
        # line_labels pour le mode pré-calculé (pas utilisé ici, mais on garde la var
        # pour ne pas casser le scope)
        _ = line_labels


def render_otp_heatmap_mini(otp_data: dict | None = None, height: int = 200) -> None:
    """Version compacte pour PCC Live (moins de détails)."""
    render_otp_heatmap(otp_data, days=1, height=height)
