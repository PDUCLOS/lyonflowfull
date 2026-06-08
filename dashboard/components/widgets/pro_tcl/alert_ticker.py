"""Widget — Ticker horizontal d'alertes (style 'Tape' en CSS).

Sprint 8 — Charge les alertes via data_loader.cached_recent_alerts().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_recent_alerts


def render_alert_ticker(alerts: list | None = None) -> None:
    """Affiche un ticker horizontal défilant avec les alertes.

    Args:
        alerts: liste d'alertes. Si None, charge via data_loader.
    """
    if alerts is None:
        df = cached_recent_alerts(force_mock=False)
        alerts = df.to_dict("records") if not df.empty else []

    if not alerts:
        st.info("Aucune alerte active.")
        return

    # Concaténer les alertes en bandeau
    items = []
    for a in alerts:
        sev = a.get("severity", "info")
        color = {"warning": COLORS["status_warning"], "info": COLORS["status_info"], "critical": COLORS["status_critical"]}.get(sev, COLORS["text_muted"])
        icon = a.get("line_icon", "⚠️")
        items.append(
            f'<span style="background:{color};color:white;padding:2px 10px;'
            f'border-radius:10px;margin-right:12px;font-size:0.85rem;">'
            f"{icon} {a.get('title', '—')}</span>"
        )

    # Ticker CSS simple
    html = f"""
    <div style="overflow:hidden;background:var(--bg-card);border:1px solid var(--border-card);
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
