"""Page Élu — Avant / Après aménagement."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.elu import (
    render_delta_kpis,
    render_project_selector,
)

st.set_page_config(
    page_title="Avant / Après — Élu · LyonFlow",
    page_icon="⏪",
    layout="wide",
)

apply_persona_guard(expected_persona="elu")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("⏪ Avant / Après aménagement")
render_data_status_banner()

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

    st.markdown(f"##### {nom} ({annee}) — Coût : {cout} M€")

    st.markdown("---")

    # AVANT
    st.markdown("##### AVANT aménagement")
    if avant:
        # Adapter le nb de colonnes au nb de clés (sinon clés 5+ silencieusement perdues)
        keys = list(avant.keys())
        cols = st.columns(len(keys))
        for col, k in zip(cols, keys):
            with col:
                v = avant.get(k, "—")
                # Exclure bool (sous-classe de int → serait formaté comme un nombre)
                if isinstance(v, bool):
                    v_str = "Oui" if v else "Non"
                elif isinstance(v, (int, float)):
                    v_str = f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) and v > 1000 else f"{v}"
                else:
                    v_str = str(v) if v is not None else "—"
                st.markdown(
                    f"""
                    <div style="background:#1A1D24;border:1px solid #E74C3C;border-left:4px solid #E74C3C;
                                border-radius:6px;padding:0.6rem;text-align:center;">
                        <div class="lyf-sublabel" style="opacity:0.6;">{k.replace("_", " ").title()}</div>
                        <div class="lyf-value" style="font-weight:700;color:#E74C3C;margin-top:0.3rem;">
                            {v_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # APRÈS
    st.markdown("##### APRÈS aménagement")
    if apres:
        keys = list(apres.keys())
        cols = st.columns(len(keys))
        for col, k in zip(cols, keys):
            with col:
                v = apres.get(k, "—")
                if isinstance(v, bool):
                    v_str = "Oui" if v else "Non"
                elif isinstance(v, (int, float)):
                    v_str = f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) and v > 1000 else f"{v}"
                else:
                    v_str = str(v) if v is not None else "—"
                st.markdown(
                    f"""
                    <div style="background:#1A1D24;border:1px solid #4CAF50;border-left:4px solid #4CAF50;
                                border-radius:6px;padding:0.6rem;text-align:center;">
                        <div class="lyf-sublabel" style="opacity:0.6;">{k.replace("_", " ").title()}</div>
                        <div class="lyf-value" style="font-weight:700;color:#4CAF50;margin-top:0.3rem;">
                            {v_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Delta
    if avant and apres:
        st.markdown("##### Delta (delta_kpis)")
        render_delta_kpis(avant, apres)

st.caption("LyonFlow · Avant/Après · Données ouvertes Grand Lyon + Open data")
