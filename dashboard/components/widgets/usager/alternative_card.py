"""Widget — Carte d'alternative (plus compact que recommendation)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def _safe_eur(v) -> str:
    """Formate un montant en EUR, safe si None / str."""
    try:
        return f"{float(v):.2f}€"
    except (TypeError, ValueError):
        return "—"


def _safe_g(v) -> str:
    """Formate un poids en grammes, safe si None / str."""
    try:
        return f"{int(float(v))}g"
    except (TypeError, ValueError):
        return "—g"


def render_alternative_card(option: dict) -> None:
    """Affiche une carte d'alternative (rank 2, 3, ...).

    Args:
        option: dict avec mode_icon, mode_label, duration_text, cost_eur, co2_g, why
    """
    bg = COLORS["bg_card_alt"]
    st.html(
        f"""
        <div style="background:{bg};border:1px solid var(--border-card);border-radius:8px;
                    padding:0.8rem 1rem;margin:0.5rem 0;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="display:flex;align-items:center;gap:0.8rem;">
                    <div style="font-size:1.8rem;">{option.get("mode_icon", "🚦")}</div>
                    <div>
                        <div style="font-weight:600;">{option.get("mode_label", "—")}</div>
                        <div style="font-size:0.8rem;opacity:0.6;">{option.get("why", "") or "—"}</div>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:1.2rem;font-weight:600;">{option.get("duration_text", "—")}</div>
                    <div style="font-size:0.8rem;opacity:0.7;">
                        {_safe_eur(option.get("cost_eur"))} · {_safe_g(option.get("co2_g"))} CO₂
                    </div>
                </div>
            </div>
        </div>
        """
    )
