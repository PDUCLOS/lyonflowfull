"""Widget — Builder de rapport (sélection période + lignes)."""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st


def render_report_builder() -> dict:
    """Affiche le builder de rapport (période, lignes, sections).

    Returns:
        Dict avec clés : start_date, end_date, lines, sections, format
    """
    st.markdown("##### 🛠 Builder de rapport")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Date début",
            value=datetime.now() - timedelta(days=7),
            key="rb_start_date",
        )
    with col2:
        end_date = st.date_input(
            "Date fin",
            value=datetime.now(),
            key="rb_end_date",
        )

    st.markdown("**Lignes à inclure**")
    from dashboard.components.widgets.pro_tcl.line_selector import render_line_selector

    lines = render_line_selector(multiselect=True, key_suffix="rb")

    st.markdown("**Sections à inclure**")
    sections = st.multiselect(
        "Sections",
        [
            "KPIs par ligne (OTP, retard, charge)",
            "Heatmap OTP lignes × heures",
            "Matrice corrélation bus × trafic",
            "Top bottlenecks",
            "Alertes prédites",
            "Backtesting vs réel",
        ],
        default=[
            "KPIs par ligne (OTP, retard, charge)",
            "Matrice corrélation bus × trafic",
        ],
        key="rb_sections",
    )

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "lines": lines,
        "sections": sections,
    }
