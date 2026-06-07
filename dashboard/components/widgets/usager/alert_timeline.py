"""Widget — Frise temporelle des alertes."""

from __future__ import annotations

from datetime import datetime

import streamlit as st


def render_alert_timeline(alerts: list) -> None:
    """Affiche une frise temporelle verticale des alertes.

    Args:
        alerts: liste de dicts d'alertes (avec timestamp, title, severity)
    """
    if not alerts:
        st.info("Aucune alerte active.")
        return

    st.markdown("##### 🕐 Frise temporelle")

    # Trier par timestamp desc
    sorted_alerts = sorted(alerts, key=lambda a: a.get("timestamp", ""), reverse=True)

    for alert in sorted_alerts:
        ts = alert.get("timestamp", "")
        # Extraire heure
        try:
            dt = datetime.fromisoformat(ts)
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = "—"

        sev = alert.get("severity", "info")
        color = {"warning": "#FF9800", "info": "#2196F3", "critical": "#E74C3C"}.get(sev, "#666")
        icon = alert.get("line_icon", "⚠️")

        st.markdown(
            f"""
            <div style="display:flex;gap:0.8rem;align-items:flex-start;margin:0.5rem 0;">
                <div style="text-align:right;min-width:50px;">
                    <div style="font-size:0.85rem;font-weight:600;color:{color};">{time_str}</div>
                </div>
                <div style="background:{color};width:8px;height:8px;border-radius:50%;
                            margin-top:6px;flex-shrink:0;"></div>
                <div style="flex:1;font-size:0.9rem;">
                    <b>{icon} {alert.get("title", "—")}</b>
                    <div style="font-size:0.8rem;opacity:0.7;">{alert.get("description", "")}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
