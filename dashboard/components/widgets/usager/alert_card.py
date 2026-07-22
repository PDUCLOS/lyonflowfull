"""Widget — Carte d'alerte (format compact pour liste d'alertes)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import STATUS_COLORS


def render_alert_card(alert: dict) -> None:
    """Affiche une carte d'alerte (titre, description, action).

    Args:
        alert: dict avec line, line_icon, line_color, title, description,
               action, severity
    """
    sev = alert.get("severity", "info")
    color = STATUS_COLORS.get(sev, STATUS_COLORS["info"])
    icon = alert.get("line_icon", "⚠️")

    st.markdown(
        f"""
        <div class="lyonflow-card" style="border-left-color:{color};">
            <div style="display:flex;align-items:center;gap:0.7rem;">
                <div style="font-size:1.5rem;line-height:1;">{icon}</div>
                <div style="flex:1;">
                    <div style="font-weight:600;font-size:0.98rem;">
                        {alert.get("title", "—")}
                    </div>
                    <div class="lyf-detail" style="opacity:0.7;margin-top:2px;">
                        {alert.get("description", "")}
                    </div>
                </div>
            </div>
            <div style="margin-top:0.7rem;padding:0.55rem 0.8rem;background:{color}22;
                        border-left:3px solid {color};border-radius:6px;
                        font-size:0.86rem;">
                <b>Action :</b> {alert.get("action", "")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
