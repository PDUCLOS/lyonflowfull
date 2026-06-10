"""Widget — Carte de recommandation principale (top trajet).

Carte colorée mise en avant, affiche mode, durée, coût, CO2, probabilité.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_recommendation_card(option: dict) -> None:
    """Affiche la carte de recommandation top (mise en avant).

    Args:
        option: dict avec clés mode_label, mode_icon, duration_text,
                cost_eur, co2_g, confidence_pct, why (list), etc.
    """
    bg_color = COLORS["bg_card"]
    confidence = option.get("confidence_pct", 0)

    if confidence >= 90:
        accent = COLORS["status_ok"]
        bg_accent = "rgba(76,175,80,0.1)"  # Green tinted
    elif confidence >= 70:
        accent = COLORS["status_warning"]
        bg_accent = "rgba(255,152,0,0.1)"  # Orange tinted
    else:
        accent = COLORS["status_critical"]
        bg_accent = "rgba(244,67,54,0.1)"  # Red tinted

    border = f"4px solid {accent}"

    # Helpers défensifs — None / string / float manquant
    def _fmt_eur(v) -> str:
        try:
            return f"{float(v):.2f}€"
        except (TypeError, ValueError):
            return "—"

    def _fmt_g(v) -> str:
        try:
            return f"{int(float(v))}g"
        except (TypeError, ValueError):
            return "—g"

    st.html(
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
                        {_fmt_eur(option.get("cost_eur"))}
                    </div>
                </div>
                <div>
                    <div style="font-size:0.75rem;opacity:0.6;">CO₂</div>
                    <div style="font-size:1.1rem;font-weight:600;">
                        {_fmt_g(option.get("co2_g"))}
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
                        {confidence}%
                    </div>
                </div>
            </div>
            <div style="margin-top:1rem;padding:0.8rem;background:{bg_accent};
                        border-radius:6px;font-size:0.9rem;color:{accent};">
                <b>{option.get("confidence_text", "")}</b>
            </div>
        </div>
        """
    )

    # Bouton "Partir" rendu TOUJOURS visible (avant : sous if option.get("recommended")
    # → invisible si aucune option mock n'a recommended=True).
    # Le badge "Recommended" est maintenant un label visuel séparé.
    if st.button(
        f"➡️ Partir en {option.get('mode_label', '')}",
        type="primary",
        use_container_width=True,
        key=f"recommendation_go_{option.get('mode', 'default')}",
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
