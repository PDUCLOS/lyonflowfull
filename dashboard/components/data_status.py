"""Banner statut source de donnees — transparence live.

Affiche un bandeau discret en haut de chaque page indiquant si les widgets
voient la DB live (Postgres + MLflow + Airflow) ou si la DB est indisponible
(fail loud, aucune donnee fictive affichee — politique zero mock ).

Usage::

    from dashboard.components.data_status import render_data_status_banner
    render_data_status_banner()
"""

from __future__ import annotations

import streamlit as st

from src.data.db_query import _is_db_available


def render_data_status_banner(compact: bool = True) -> None:
    """Affiche un banner statut source.

    Args:
        compact: si True, format inline minimal. Sinon block info plus large.
    """
    db_ok = _is_db_available()
    if db_ok:
        label = "Live · Postgres Gold"
        bg = "rgba(76, 175, 80, 0.12)"
        border = "var(--status-ok)"
    else:
        label = "DB non joignable — données indisponibles"
        bg = "rgba(255, 152, 0, 0.12)"
        border = "var(--status-warning)"

    padding = "4px 10px" if compact else "8px 14px"
    fs = "0.72rem" if compact else "0.85rem"
    st.markdown(
        f"""
        <div style="background:{bg};border-left:3px solid {border};
                    border-radius:4px;padding:{padding};margin-bottom:8px;
                    font-size:{fs};font-weight:500;display:inline-block;">
            {label}
        </div>
        """,
        unsafe_allow_html=True,
    )
