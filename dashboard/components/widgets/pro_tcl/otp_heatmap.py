"""Widget — Heatmap OTP Plotly (lignes × heures).

Sprint 8 — Charge via data_loader.cached_otp_heatmap_data() (vue Gold
mv_otp_heatmap, 4416 triplets). Pas de mock — la DB est la source
unique de vérité (fail loud si DB down).

Sprint 23 — Ajout sélecteur de ligne (multiselect). Toutes les lignes
de gold.mv_otp_heatmap sont accessibles. Mode "Toutes" = top_n pires.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_otp_heatmap_data
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.plotly_theme import LYF_TEMPLATE


def _load_otp_data() -> tuple[dict, dict[str, str]]:
    """Charge et structure les données OTP depuis la DB.

    Returns:
        (otp_data, line_labels) — otp_data = {line_id: {date: [otp_h0..h23]}},
        line_labels = {line_id: "L66"}.
    """
    df = cached_otp_heatmap_data()
    if df.empty:
        return {}, {}
    otp_data: dict = {}
    line_labels: dict[str, str] = {}
    for _, row in df.iterrows():
        line_id = row["line_id"]
        date = str(row.get("date", ""))
        if line_id not in otp_data:
            otp_data[line_id] = {}
        line_labels[line_id] = row.get("line_label") or line_id
        if date not in otp_data[line_id]:
            otp_data[line_id][date] = [0.0] * 24
        otp_data[line_id][date][int(row["hour"])] = float(row["otp_pct"])
    return otp_data, line_labels


def _compute_matrix(
    otp_data: dict,
    line_labels: dict[str, str],
    days: int = 1,
    top_n: int | None = None,
    selected_line_ids: list[str] | None = None,
) -> tuple[list[str], list[list[float | None]]]:
    """Construit la matrice OTP (lignes × 24h), triée par pire OTP moyen.

    Args:
        top_n: si défini et pas de sélection, ne garde que les N pires lignes.
        selected_line_ids: si défini, filtre sur ces lignes (ignore top_n).
    """
    if not otp_data:
        return [], []

    first_key = next(iter(otp_data))
    dates = sorted(otp_data[first_key].keys())
    selected_dates = dates[:days] if days < len(dates) else dates

    line_ids_to_process = list(otp_data.keys())
    if selected_line_ids:
        line_ids_to_process = [lid for lid in line_ids_to_process if lid in selected_line_ids]

    line_avgs: dict[str, float] = {}
    line_rows: dict[str, list[float | None]] = {}
    for line_id in line_ids_to_process:
        row: list[float | None] = []
        hourly_values: list[float] = []
        for h in range(24):
            values = [
                otp_data[line_id][d][h]
                for d in selected_dates
                if d in otp_data[line_id] and h < len(otp_data[line_id][d])
            ]
            if values:
                avg = sum(values) / len(values)
                row.append(round(avg, 1))
                hourly_values.append(avg)
            else:
                row.append(None)
        line_rows[line_id] = row
        line_avgs[line_id] = sum(hourly_values) / len(hourly_values) if hourly_values else 100.0

    sorted_ids = sorted(line_avgs, key=lambda k: line_avgs[k])
    if top_n and not selected_line_ids:
        sorted_ids = sorted_ids[:top_n]

    sorted_ids.reverse()

    lines_display = [line_labels.get(lid, lid) for lid in sorted_ids]
    z_data = [line_rows[lid] for lid in sorted_ids]
    return lines_display, z_data


def _line_type_icon(label: str) -> str:
    if label.startswith("T"):
        return "🚊"
    if label.startswith("M"):
        return "🚇"
    return "🚌"


def render_otp_heatmap(
    otp_data: dict | None = None,
    days: int = 1,
    height: int = 500,
    top_n: int | None = None,
    compact: bool = False,
    show_line_selector: bool = False,
    key_suffix: str = "",
) -> None:
    with loading_wrapper("Chargement Otp heatmap…", "⏳"):
        if otp_data is None:
            otp_data, line_labels = _load_otp_data()
            if not otp_data:
                st.info("Aucune donnée OTP — gold.mv_otp_heatmap est vide.")
                return
        else:
            line_labels = {}

        selected_line_ids: list[str] | None = None

        if show_line_selector and line_labels:
            all_ids = sorted(line_labels.keys(), key=lambda k: line_labels.get(k, k))
            display_options = [
                f"{_line_type_icon(line_labels[lid])} {line_labels[lid]}"
                for lid in all_ids
            ]
            id_by_display = dict(zip(display_options, all_ids))

            st.caption(f"{len(all_ids)} lignes disponibles dans gold.mv_otp_heatmap")
            chosen = st.multiselect(
                "Filtrer par ligne",
                options=display_options,
                default=[],
                placeholder="Toutes (top pires)",
                key=f"otp_line_selector_{key_suffix}",
            )
            if chosen:
                selected_line_ids = [id_by_display[c] for c in chosen]

        lines, z_data = _compute_matrix(
            otp_data, line_labels, days=days, top_n=top_n,
            selected_line_ids=selected_line_ids,
        )
        if not lines:
            st.info("Aucune ligne OTP à afficher.")
            return

        try:
            import plotly.graph_objects as go

            heatmap_args: dict = {
                "z": z_data,
                "x": [f"{h}h" for h in range(24)],
                "y": lines,
                "colorscale": [
                    [0.0, COLORS["status_critical"]],
                    [0.395, COLORS["status_warning"]],
                    [0.789, COLORS["chart_yellow"]],
                    [1.0, COLORS["status_ok"]],
                ],
                "zmin": 60,
                "zmax": 98,
                "colorbar": {"title": "OTP %", "thickness": 15, "len": 0.8},
                "hovertemplate": "<b>%{y}</b> à %{x}<br/>OTP: %{z:.0f}%<extra></extra>",
                "xgap": 1,
                "ygap": 1,
            }

            if not compact or selected_line_ids:
                heatmap_args["texttemplate"] = "%{z:.0f}"
                heatmap_args["textfont"] = {"size": 9}

            fig = go.Figure(data=go.Heatmap(**heatmap_args))

            title_suffix = "aujourd'hui" if days == 1 else f"moyenne {days}j"
            if selected_line_ids:
                title_top = f"{len(selected_line_ids)} ligne(s)"
            elif top_n:
                title_top = f"Top {top_n} pires"
            else:
                title_top = "Toutes"

            fig_height = height
            if selected_line_ids and len(selected_line_ids) <= 5:
                fig_height = max(200, 80 * len(selected_line_ids) + 80)

            fig.update_layout(
                title={
                    "text": f"OTP — {title_top} lignes × heure ({title_suffix})",
                    "font": {"size": 14},
                },
                xaxis_title="Heure" if not compact else None,
                yaxis_title=None,
                height=fig_height,
                template=LYF_TEMPLATE,
                margin={"l": 60, "r": 30, "t": 40, "b": 30} if compact else {"l": 70, "r": 40, "t": 50, "b": 50},
                yaxis={"tickfont": {"size": 11 if not compact else 10}},
                xaxis={"tickfont": {"size": 10}},
            )
            plotly_with_alt(fig, use_container_width=True)

        except ImportError:
            df_display = pd.DataFrame(z_data, index=lines, columns=[f"{h}h" for h in range(24)])
            st.dataframe(
                df_display.style.background_gradient(cmap="RdYlGn", vmin=60, vmax=98),
                height=height,
            )


def render_otp_heatmap_mini(otp_data: dict | None = None, height: int = 280) -> None:
    with loading_wrapper("Chargement Otp heatmap mini…", "⏳"):
        """Version compacte PCC Live — top 15 pires lignes, sans text overlay."""
        render_otp_heatmap(otp_data, days=1, height=height, top_n=15, compact=True)
