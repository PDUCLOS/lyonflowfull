"""Widget — Tableau ranké des 10 bottlenecks avec ROI.

Sprint 8 — Bottlenecks via data_loader.load_bottlenecks_top().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_bottlenecks_top


def render_bottleneck_ranking(top_n: int | None = None) -> None:
    """Affiche le tableau ranké des bottlenecks.

    Args:
        top_n: nombre de bottlenecks à afficher. None = tous.
    """
    bottlenecks = load_bottlenecks_top(force_mock=False)
    if top_n:
        bottlenecks = bottlenecks[:top_n]

    for b in bottlenecks:
        zone = b.get("zone", "—")
        rank = b.get("rank", "—")
        lignes = ", ".join(b.get("lines_impacted", []))
        voyageurs = b.get("voyageurs_jour", 0)
        gain = b.get("gain_min", 0)
        cout = b.get("cout_M_euros", 0)
        roi = b.get("roi_mois", 0)
        delai = b.get("delai_mois", 0)

        # Couleur selon ROI
        if roi <= 12:
            roi_color = "#4CAF50"
            roi_emoji = "🟢"
        elif roi <= 24:
            roi_color = "#FF9800"
            roi_emoji = "🟡"
        else:
            roi_color = "#E74C3C"
            roi_emoji = "🔴"

        st.markdown(
            f"""
            <div class="lyonflow-card" style="padding:0.7rem 1rem;margin:0.4rem 0;">
                <div style="display:grid;grid-template-columns:50px 2fr 1fr 1fr 1fr 1fr 1fr;
                            gap:0.8rem;align-items:center;font-size:0.85rem;">
                    <div style="background:#3F51B5;color:white;border-radius:50%;width:36px;
                                height:36px;display:flex;align-items:center;justify-content:center;
                                font-weight:700;">
                        #{rank}
                    </div>
                    <div>
                        <div style="font-weight:600;">{zone}</div>
                        <div style="font-size:0.75rem;opacity:0.6;">{lignes}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">Voyageurs/j</div>
                        <div style="font-weight:600;">{voyageurs:,}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">Gain</div>
                        <div style="font-weight:600;color:#4CAF50;">{gain} min</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">Coût</div>
                        <div style="font-weight:600;">{cout} M€</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">Délai</div>
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
