"""Widget — KPI cards denses par ligne (OTP, retard, fréquence, charge).

Sprint 6 — binding DB :
* ``line_ids=None`` → ``data_loader.load_line_kpis()`` (DB Gold vue matérialisée
  ``gold.mv_line_kpis_live`` ou mock fallback).
* Le widget reste rétro-compatible (accepte un dict en arg).
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_line_kpis


def render_line_kpis(
    line_ids: list | None = None,
    compact: bool = False,
    kpis_dict: dict | None = None,
) -> None:
    """Affiche les KPI cards denses par ligne.

    Args:
        line_ids: liste de line_id. Si None, toutes les lignes.
        compact: True pour 4 KPIs/ligne en mode compact, False pour layout large.
        kpis_dict: dict pré-calculé. Si None, tente DB → fallback mock.
    """
    if kpis_dict is None:
        kpis_dict = load_line_kpis(force_mock=False)

    if line_ids is None:
        line_ids = list(kpis_dict.keys())

    for line_id in line_ids:
        kpis = kpis_dict.get(line_id)
        if not kpis:
            continue

        otp = kpis.get("otp_pct", 0)
        otp_color = "#4CAF50" if otp >= 88 else "#FF9800" if otp >= 80 else "#E74C3C"
        delay = kpis.get("avg_delay_min", 0)
        load = kpis.get("load_pct", 0)
        load_color = "#4CAF50" if load < 70 else "#FF9800" if load < 90 else "#E74C3C"
        trend = kpis.get("trend", "stable")
        trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(trend, "➡️")
        trend_delta = kpis.get("trend_delta", 0)

        st.markdown(
            f"""
            <div class="lyonflow-card" style="padding:0.6rem 0.8rem;margin:0.3rem 0;">
                <div style="display:flex;align-items:center;justify-content:space-between;
                            margin-bottom:6px;">
                    <div style="font-weight:600;font-size:0.95rem;">{line_id}</div>
                    <div style="font-size:0.75rem;opacity:0.7;">
                        {trend_icon} {trend_delta:+.1f}pts
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;
                            font-size:0.8rem;">
                    <div>
                        <div style="opacity:0.6;font-size:0.7rem;">OTP</div>
                        <div style="font-weight:600;color:{otp_color};">{otp}%</div>
                    </div>
                    <div>
                        <div style="opacity:0.6;font-size:0.7rem;">Retard</div>
                        <div style="font-weight:600;">{delay} min</div>
                    </div>
                    <div>
                        <div style="opacity:0.6;font-size:0.7rem;">Fréq.</div>
                        <div style="font-weight:600;">{kpis.get('frequency_min', 0)} min</div>
                    </div>
                    <div>
                        <div style="opacity:0.6;font-size:0.7rem;">Charge</div>
                        <div style="font-weight:600;color:{load_color};">{load}%</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
