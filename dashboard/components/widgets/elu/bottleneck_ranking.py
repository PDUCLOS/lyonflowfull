"""Widget — Tableau ranké des 10 bottlenecks avec ROI.

Sprint 8 — Bottlenecks via data_loader.cached_bottlenecks_top().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_bottlenecks_top
from dashboard.components.loading_state import loading_wrapper


def render_bottleneck_ranking(top_n: int | None = None) -> None:
    with loading_wrapper("Chargement Bottleneck ranking…", "⏳"):
        """Affiche le tableau ranké des bottlenecks.

    Args:
        top_n: nombre de bottlenecks à afficher. None = tous.
    """
    bottlenecks = cached_bottlenecks_top()
    if top_n:
        bottlenecks = bottlenecks[:top_n]

    for b in bottlenecks:
        zone = b.get("zone") or "—"
        rank = b.get("rank", "—")
        lignes = ", ".join(b.get("lines_impacted") or []) or "—"
        voyageurs = b.get("voyageurs_jour", 0) or 0
        gain = b.get("gain_min", 0) or 0
        cout = b.get("cout_M_euros", 0) or 0
        roi = b.get("roi_mois", 0) or 0
        delai = b.get("delai_mois", 0) or 0

        # Couleur selon ROI
        if roi <= 12:
            roi_color = COLORS["status_ok"]
            roi_emoji = "🟢"
        elif roi <= 24:
            roi_color = COLORS["status_warning"]
            roi_emoji = "🟡"
        else:
            roi_color = COLORS["status_critical"]
            roi_emoji = "🔴"

        # Format cout en M€ (avant : "{cout} M€" brut → "1500000 M€" si DB renvoie euros)
        cout_str = f"{cout:.1f} M€" if cout < 1000 else f"{cout / 1_000_000:.1f} M€"

        st.markdown(
            f"""
            <div class="lyonflow-card" style="padding:0.7rem 1rem;margin:0.4rem 0;">
                <div class="lyf-detail" style="display:grid;grid-template-columns:50px 2fr 1fr 1fr 1fr 1fr 1fr;gap:0.8rem;align-items:center;">
                    <div style="background:var(--persona-elu);color:white;border-radius:50%;width:36px;
                                height:36px;display:flex;align-items:center;justify-content:center;
                                font-weight:700;">
                        #{rank}
                    </div>
                    <div>
                        <div style="font-weight:600;">{zone}</div>
                        <div class="lyf-detail" style="opacity:0.6;">{lignes}</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="lyf-detail" style="opacity:0.6;">Voyageurs/j</div>
                        <div style="font-weight:600;">{voyageurs:,}</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="lyf-detail" style="opacity:0.6;">Gain</div>
                        <div style="font-weight:600;color:var(--status-ok);">{gain} min</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="lyf-detail" style="opacity:0.6;">Coût</div>
                        <div style="font-weight:600;">{cout_str}</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="lyf-detail" style="opacity:0.6;">Délai</div>
                        <div style="font-weight:600;">{delai} mois</div>
                    </div>
                    <div style="text-align:center;color:{roi_color};font-weight:600;">
                        {roi_emoji} ROI {int(roi)}m
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
