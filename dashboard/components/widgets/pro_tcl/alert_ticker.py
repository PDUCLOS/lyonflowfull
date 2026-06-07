"""Widget — Ticker horizontal d'alertes (style 'Tape' en CSS).

Sprint 8 — Charge les alertes via data_loader.load_recent_alerts().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_recent_alerts


def render_alert_ticker(alerts: list | None = None) -> None:
    """Affiche un ticker horizontal défilant avec les alertes.

    Args:
        alerts: liste d'alertes. Si None, charge via data_loader.
    """
    if alerts is None:
        df = load_recent_alerts(force_mock=False)
        alerts = df.to_dict("records") if not df.empty else []

    if not alerts:
        st.info("Aucune alerte active.")
        return

    # Concaténer les alertes en bandeau
    items = []
    for a in alerts:
        sev = a.get("severity", "info")
        color = {"warning": "#FF9800", "info": "#2196F3", "critical": "#E74C3C"}.get(sev, "#666")
        icon = a.get("line_icon", "⚠️")
        items.append(
            f'<span style="background:{color};color:white;padding:2px 10px;'
            f'border-radius:10px;margin-right:12px;font-size:0.85rem;">'
            f'{icon} {a.get("title", "—")}</span>'
        )

    # Ticker CSS simple
    html = f"""
    <div style="overflow:hidden;background:#1A1D24;border:1px solid #2A2D34;
                border-radius:8px;padding:8px 0;white-space:nowrap;">
        <div style="display:inline-block;animation:ticker_scroll 30s linear infinite;
                    padding-left:100%;">
            {"".join(items)}{"".join(items)}
        </div>
    </div>
    <style>
    @keyframes ticker_scroll {{
        0% {{ transform: translateX(0); }}
        100% {{ transform: translateX(-50%); }}
    }}
    </style>
    """
    st.markdown(html, unsafe_allow_html=True)
