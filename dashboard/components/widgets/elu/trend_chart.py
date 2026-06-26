"""Widget — Courbe d'évolution sur 12 mois (Plotly).

 KPIs via data_loader.cached_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_elu_kpis_dict
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.plotly_theme import LYF_TEMPLATE


def render_trend_chart(kpi_key: str = "part_modale_tc") -> None:
    with loading_wrapper("Chargement Trend chart…", "⏳"):
        """Affiche la courbe d'évolution d'un KPI sur 12 mois.

    Args:
        kpi_key: clé du KPI dans KPI_12_MONTHS.
    """
    kpis = cached_elu_kpis_dict()
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
                line={"color": COLORS["persona_elu_accent"], "width": 3},
                marker={"size": 8},
            )
        )

        # Ligne target
        if target:
            fig.add_hline(
                y=target,
                line_dash="dash",
                line_color=COLORS["status_ok"],
                annotation_text=f"Cible 2026: {target}{unit}",
            )

        fig.update_layout(
            title=f"{kpi.get('label', '—')} — 12 derniers mois",
            yaxis_title=f"Valeur ({unit})",
            height=320,
            template=LYF_TEMPLATE,
            showlegend=False,
        )
        plotly_with_alt(fig, use_container_width=True)

    except ImportError:
        # Fallback : barres markdown
        st.markdown("##### " + kpi.get("label", "—"))
        for m, v in zip(months, history):
            st.caption(f"{m}: {v}{unit}")
