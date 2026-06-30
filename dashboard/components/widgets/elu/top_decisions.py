"""Widget — Top décisions à arbitrer ce trimestre.

Bottlenecks via data_loader.cached_bottlenecks_top().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_bottlenecks_top
from dashboard.components.loading_state import loading_wrapper


def render_top_decisions(n: int = 5) -> None:
    with loading_wrapper("Chargement Top decisions…", "⏳"):
        """Affiche les N décisions à arbitrer ce trimestre.

    Args:
        n: nombre de décisions à afficher.
    """
    st.markdown(f"##### 🎯 Top {n} décisions à arbitrer")

    bottlenecks = cached_bottlenecks_top()
    for i, b in enumerate(bottlenecks[:n], 1):
        zone = b.get("zone", "—")
        lignes = ", ".join(b.get("lines_impacted", []))
        voyageurs = b.get("voyageurs_jour", 0)
        gain = b.get("gain_min", 0)
        cout = b.get("cout_M_euros", 0)
        roi = b.get("roi_mois", 0)
        delai = b.get("delai_mois", 0)

        st.markdown(
            f"""
            <div class="lyonflow-card" style="margin:0.5rem 0;">
                <div style="display:flex;align-items:start;gap:1rem;">
                    <div style="background:var(--persona-elu);color:white;width:32px;height:32px;
                                border-radius:50%;display:flex;align-items:center;
                                justify-content:center;font-weight:700;flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:1rem;">{zone}</div>
                        <div class="lyf-detail" style="opacity:0.7;margin:2px 0;">
                            Lignes : {lignes} · {voyageurs:,} voyageurs/jour
                        </div>
                        <div style="font-size:0.9rem;margin-top:0.4rem;">
                            💡 <b>{b.get("description", "—")}</b>
                        </div>
                        <div class="lyf-detail" style="display:flex;gap:1.2rem;margin-top:0.5rem;">
                            <span>⏱ <b>{gain} min</b> gagnées</span>
                            <span>💰 <b>{cout} M€</b></span>
                            <span>📅 <b>{delai} mois</b> travaux</span>
                            <span style="color:var(--status-ok);">📈 ROI <b>{int(roi)} mois</b></span>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
