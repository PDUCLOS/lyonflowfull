"""Widget — Panneau 'Pourquoi cette reco ?' (explicabilité).

Affiche les 3 raisons principales qui ont conduit à la recommandation.
"""

from __future__ import annotations

import streamlit as st


def render_why_explainer(reasons: list[str]) -> None:
    """Affiche un panneau repliable expliquant la recommandation.

    Args:
        reasons: liste de 3 raisons (strings)
    """
    with st.expander("💡 Pourquoi cette recommandation ?", expanded=False):
        if not reasons:
            st.caption("Aucune raison particulière — trajet par défaut.")
            return
        for i, r in enumerate(reasons, 1):
            st.markdown(
                f"""
                <div style="display:flex;align-items:flex-start;gap:0.8rem;
                            margin:0.4rem 0;">
                    <div style="background:var(--status-ok);color:white;border-radius:50%;
                                width:24px;height:24px;display:flex;align-items:center;
                                justify-content:center;font-weight:600;flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">{r}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_why_summary(reasons: list[str], max_items: int = 2) -> str:
    """Retourne un résumé court en markdown (pour carte compacte)."""
    if not reasons:
        return ""
    items = reasons[:max_items]
    return "💡 " + " · ".join(items)
