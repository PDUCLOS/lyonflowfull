"""Widget — Projection OTP avant/après."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_otp_projection(simulation: dict, base_otp: float = 78.0) -> None:
    """Affiche la projection OTP avant/après une modification de fréquence.

    Args:
        simulation: dict retourné par render_frequency_slider().
        base_otp: OTP actuel de la ligne.
    """
    buses_added = simulation.get("buses_added", 0)

    # Modèle simplifié : +1 bus → +2.5pts OTP, -1 bus → -3pts
    if buses_added > 0:
        delta = buses_added * 2.5
    elif buses_added < 0:
        delta = buses_added * 3.0
    else:
        delta = 0

    new_otp = max(60.0, min(98.0, base_otp + delta))
    actual_delta = new_otp - base_otp

    # Intervalle de confiance ±2pts
    ic_low = max(60.0, new_otp - 2)
    ic_high = min(98.0, new_otp + 2)

    color = (
        COLORS["status_ok"]
        if actual_delta > 0
        else COLORS["status_critical"]
        if actual_delta < 0
        else COLORS["status_warning"]
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("OTP actuel", f"{base_otp:.1f}%")
    with c2:
        st.metric("OTP projeté", f"{new_otp:.1f}%", delta=f"{actual_delta:+.1f}pts", delta_color="normal")
    with c3:
        st.metric("IC 95%", f"[{ic_low:.1f}%, {ic_high:.1f}%]")

    st.markdown(
        f"""
        <div style="background:var(--bg-card);border-left:4px solid {color};
                    border-radius:6px;padding:0.8rem;margin-top:0.5rem;">
            <div class="lyf-detail" style="opacity:0.7;">Impact estimé</div>
            <div class="lyf-value" style="font-weight:600;color:{color};">
                {buses_added:+d} bus sur la plage {simulation.get("period_start", 17)}h-{simulation.get("period_end", 19)}h
            </div>
            <div class="lyf-detail" style="margin-top:0.4rem;opacity:0.8;">
                Gain voyageurs estimé : {int(abs(actual_delta) * 1500):,}/jour (sur la base de 1500 voyageurs/point OTP)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
