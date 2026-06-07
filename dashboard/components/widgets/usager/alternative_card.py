"""Widget — Carte d'alternative (plus compact que recommendation)."""

from __future__ import annotations

import streamlit as st


def render_alternative_card(option: dict) -> None:
    """Affiche une carte d'alternative (rank 2, 3, ...).

    Args:
        option: dict avec mode_icon, mode_label, duration_text, cost_eur, co2_g, why
    """
    bg = "#161A20"
    st.markdown(
        f"""
        <div style="background:{bg};border:1px solid #2A2D34;border-radius:8px;
                    padding:0.8rem 1rem;margin:0.5rem 0;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="display:flex;align-items:center;gap:0.8rem;">
                    <div style="font-size:1.8rem;">{option.get("mode_icon", "🚦")}</div>
                    <div>
                        <div style="font-weight:600;">{option.get("mode_label", "—")}</div>
                        <div style="font-size:0.8rem;opacity:0.6;">{option.get("why", "")}</div>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:1.2rem;font-weight:600;">{option.get("duration_text", "—")}</div>
                    <div style="font-size:0.8rem;opacity:0.7;">
                        {option.get("cost_eur", 0):.2f}€ · {option.get("co2_g", 0)}g CO₂
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
