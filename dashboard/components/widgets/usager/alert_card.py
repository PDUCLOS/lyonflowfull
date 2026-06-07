"""Widget — Carte d'alerte (format compact pour liste d'alertes)."""

from __future__ import annotations

import streamlit as st


def render_alert_card(alert: dict) -> None:
    """Affiche une carte d'alerte (titre, description, action).

    Args:
        alert: dict avec line, line_icon, line_color, title, description,
               action, severity
    """
    sev = alert.get("severity", "info")
    color = {"warning": "#FF9800", "info": "#2196F3", "critical": "#E74C3C"}.get(sev, "#666")
    icon = alert.get("line_icon", "⚠️")

    st.markdown(
        f"""
        <div class="lyonflow-card" style="border-left:4px solid {color};">
            <div style="display:flex;align-items:center;gap:0.6rem;">
                <div style="font-size:1.4rem;">{icon}</div>
                <div style="flex:1;">
                    <div style="font-weight:600;">{alert.get('title', '—')}</div>
                    <div style="font-size:0.85rem;opacity:0.7;">{alert.get('description', '')}</div>
                </div>
            </div>
            <div style="margin-top:0.5rem;padding:0.5rem 0.7rem;background:{color}22;
                        border-radius:4px;font-size:0.85rem;">
                💡 <b>Action :</b> {alert.get('action', '')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
