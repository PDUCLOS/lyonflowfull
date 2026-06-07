"""Widget — Carte de recommandation principale (top trajet).

Carte colorée mise en avant, affiche mode, durée, coût, CO2, probabilité.
"""

from __future__ import annotations

import streamlit as st


def render_recommendation_card(option: dict) -> None:
    """Affiche la carte de recommandation top (mise en avant).

    Args:
        option: dict avec clés mode_label, mode_icon, duration_text,
                cost_eur, co2_g, confidence_pct, why (list), etc.
    """
    bg_color = "#1A1D24"
    accent = "#4CAF50"
    border = "4px solid #4CAF50"

    st.markdown(
        f"""
        <div style="background:{bg_color};border-left:{border};border-radius:12px;
                    padding:1.5rem;margin:1rem 0;color:white;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div>
                    <div style="font-size:2.5rem;">{option.get("mode_icon", "🚦")}</div>
                    <div style="font-size:1.4rem;font-weight:600;margin-top:4px;">
                        {option.get("mode_label", "—")}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:2.2rem;font-weight:700;color:{accent};">
                        {option.get("duration_text", "—")}
                    </div>
                    <div style="font-size:0.9rem;opacity:0.7;">
                        dont {option.get("wait_min", 0)} min d'attente
                    </div>
                </div>
            </div>

            <div style="display:flex;gap:1.5rem;margin-top:1rem;flex-wrap:wrap;">
                <div>
                    <div style="font-size:0.75rem;opacity:0.6;">Coût</div>
                    <div style="font-size:1.1rem;font-weight:600;">
                        {option.get("cost_eur", 0):.2f}€
                    </div>
                </div>
                <div>
                    <div style="font-size:0.75rem;opacity:0.6;">CO₂</div>
                    <div style="font-size:1.1rem;font-weight:600;">
                        {option.get("co2_g", 0)}g
                    </div>
                </div>
                <div>
                    <div style="font-size:0.75rem;opacity:0.6;">Correspondances</div>
                    <div style="font-size:1.1rem;font-weight:600;">
                        {option.get("transfers", 0)}
                    </div>
                </div>
                <div>
                    <div style="font-size:0.75rem;opacity:0.6;">Fiabilité</div>
                    <div style="font-size:1.1rem;font-weight:600;color:{accent};">
                        {option.get("confidence_pct", 0)}%
                    </div>
                </div>
            </div>

            <div style="margin-top:1rem;padding:0.8rem;background:rgba(76,175,80,0.1);
                        border-radius:6px;font-size:0.9rem;">
                <b>{option.get("confidence_text", "")}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if option.get("recommended"):
        if st.button(
            f"➡️ Partir en {option.get('mode_label', '')}",
            type="primary",
            use_container_width=True,
            key="recommendation_go",
        ):
            st.success(f"Trajet lancé en {option.get('mode_label', '')} — bon voyage !")


def render_steps(steps: list) -> None:
    """Affiche les étapes détaillées du trajet recommandé."""
    if not steps:
        return
    st.markdown("##### 🧭 Étapes du trajet")
    for i, step in enumerate(steps, 1):
        mode = step.get("mode", "")
        icon = {"walk": "🚶", "metro": "🚇", "tram": "🚊", "bus": "🚌", "bike": "🚲", "car": "🚗"}.get(mode, "•")
        line = step.get("line", "")
        line_str = f" ({line})" if line else ""
        st.markdown(
            f"{i}. {icon} **{step.get('from', '')}** → {step.get('to', '')} "
            f"({step.get('duration_min', 0)} min){line_str}"
        )
