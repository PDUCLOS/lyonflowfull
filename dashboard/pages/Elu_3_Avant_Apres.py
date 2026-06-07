"""Page Élu — Avant / Après aménagement."""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_delta_kpis,
    render_project_selector,
)

st.set_page_config(
    page_title="Avant / Après — Élu · LyonFlowFull",
    page_icon="⏪",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()

st.title("⏪ Avant / Après aménagement")

st.caption(
    "Analyse comparative des aménagements passés — preuve par les données "
    "de l'impact des politiques d'infrastructure mobilité."
)

st.markdown("---")

# Sélecteur de projet
amgt = render_project_selector(key_suffix="avant_apres")

if amgt:
    nom = amgt.get("nom", "—")
    annee = amgt.get("annee", "")
    cout = amgt.get("cout_M_euros", 0)
    avant = amgt.get("avant", {})
    apres = amgt.get("apres", {})

    st.markdown(f"##### 📋 {nom} ({annee}) — Coût : {cout} M€")

    st.markdown("---")

    # AVANT
    st.markdown("##### 🔴 AVANT aménagement")
    if avant:
        # Présenter en 4 colonnes de cards
        c1, c2, c3, c4 = st.columns(4)
        keys = list(avant.keys())
        for col, k in zip([c1, c2, c3, c4], keys):
            with col:
                v = avant.get(k, "—")
                if isinstance(v, (int, float)):
                    v_str = f"{v:,}" if isinstance(v, int) and v > 1000 else f"{v}"
                else:
                    v_str = str(v)
                st.markdown(
                    f"""
                    <div style="background:#1A1D24;border:1px solid #E74C3C;border-left:4px solid #E74C3C;
                                border-radius:6px;padding:0.6rem;text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">{k.replace("_", " ").title()}</div>
                        <div style="font-size:1.4rem;font-weight:700;color:#E74C3C;margin-top:0.3rem;">
                            {v_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # APRÈS
    st.markdown("##### 🟢 APRÈS aménagement")
    if apres:
        c1, c2, c3, c4 = st.columns(4)
        keys = list(apres.keys())
        for col, k in zip([c1, c2, c3, c4], keys):
            with col:
                v = apres.get(k, "—")
                if isinstance(v, (int, float)):
                    v_str = f"{v:,}" if isinstance(v, int) and v > 1000 else f"{v}"
                else:
                    v_str = str(v)
                st.markdown(
                    f"""
                    <div style="background:#1A1D24;border:1px solid #4CAF50;border-left:4px solid #4CAF50;
                                border-radius:6px;padding:0.6rem;text-align:center;">
                        <div style="font-size:0.7rem;opacity:0.6;">{k.replace("_", " ").title()}</div>
                        <div style="font-size:1.4rem;font-weight:700;color:#4CAF50;margin-top:0.3rem;">
                            {v_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Delta
    if avant and apres:
        st.markdown("##### 📈 Delta (delta_kpis)")
        render_delta_kpis(avant, apres)

st.caption("LyonFlowFull · Avant/Après · Données ouvertes Grand Lyon + Open data")
