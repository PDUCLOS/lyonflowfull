"""Widget — Courbe d'évolution sur 12 mois (Plotly).

Sprint 8 — KPIs via data_loader.load_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_elu_kpis_dict


def render_trend_chart(kpi_key: str = "part_modale_tc") -> None:
    """Affiche la courbe d'évolution d'un KPI sur 12 mois.

    Args:
        kpi_key: clé du KPI dans KPI_12_MONTHS.
    """
    kpis = load_elu_kpis_dict(force_mock=False)
    kpi = kpis.get(kpi_key)
    if not kpi:
        st.warning(f"KPI '{kpi_key}' inconnu.")
        return

    history = kpi.get("history", [])
    if not history:
        st.info("Pas d'historique disponible.")
        return

    target = kpi.get("target_2026", 0)
    current = kpi.get("current", 0)
    unit = kpi.get("unit", "")

    months = [
        "Juil",
        "Août",
        "Sept",
        "Oct",
        "Nov",
        "Déc",
        "Jan",
        "Fév",
        "Mar",
        "Avr",
        "Mai",
        "Juin",
    ]

    try:
        import plotly.graph_objects as go

        fig = go.Figure()

        # Courbe historique
        fig.add_trace(
            go.Scatter(
                x=months,
                y=history,
                mode="lines+markers",
                name=kpi.get("label", ""),
                line={"color": "#5C6BC0", "width": 3},
                marker={"size": 8},
            )
        )

        # Ligne target
        if target:
            fig.add_hline(
                y=target,
                line_dash="dash",
                line_color="#4CAF50",
                annotation_text=f"Cible 2026: {target}{unit}",
            )

        fig.update_layout(
            title=f"{kpi.get('label', '—')} — 12 derniers mois",
            yaxis_title=f"Valeur ({unit})",
            height=320,
            template="plotly_dark",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        # Fallback : barres markdown
        st.markdown("##### " + kpi.get("label", "—"))
        for m, v in zip(months, history):
            st.caption(f"{m}: {v}{unit}")
