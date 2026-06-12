"""Widget — Bloc narratif 'Synthèse exécutive' auto-généré.

Sprint 8 — KPIs via data_loader.cached_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_elu_kpis_dict


def render_executive_summary() -> None:
    """Affiche un bloc narratif synthétisant la situation."""
    kpis = cached_elu_kpis_dict(force_mock=False)
    pm = kpis.get("part_modale_tc", {}).get("current", 0)
    ponc = kpis.get("ponctualite", {}).get("current", 0)
    co2 = kpis.get("co2_evite_tonnes", {}).get("current", 0) or 0
    bn = kpis.get("bottlenecks_actifs", {}).get("current", 0) or 0
    sat = kpis.get("satisfaction_pct", {}).get("current", 0) or 0

    pm_delta = kpis.get("part_modale_tc", {}).get("delta_ytd", 0)
    ponc_delta = kpis.get("ponctualite", {}).get("delta_ytd", 0)
    bn_delta = kpis.get("bottlenecks_actifs", {}).get("delta_ytd", 0)

    if pm_delta > 0 and bn_delta < 0:
        tendance = "🟢 <b>AMÉLIORATION</b>"
        tendance_text = (
            "La politique de mobilité porte ses fruits : la part modale TC progresse, "
            "le nombre de bottlenecks diminue, et la satisfaction usager reste stable."
        )
    elif pm_delta < 0 or ponc_delta < -1:
        tendance = "🔴 <b>DÉGRADATION</b>"
        tendance_text = "La situation se dégrade sur plusieurs axes. Action corrective prioritaire recommandée."
    else:
        tendance = "🟡 <b>STABLE</b>"
        tendance_text = "La situation est globalement stable, mais les marges de progression demeurent importantes."

    st.markdown(
        f"""
        <div class="lyonflow-card" style="padding:1.3rem 1.4rem;">
            <div class="lyonflow-kpi-label" style="margin-bottom:0.4rem;">
                Synthèse exécutive
            </div>
            <div style="font-size:1.15rem;margin:0.4rem 0;">{tendance}</div>
            <div style="font-size:0.92rem;line-height:1.55;opacity:0.9;">
                {tendance_text}
            </div>
            <div style="margin-top:1rem;display:grid;grid-template-columns:repeat(5,1fr);
                        gap:0.6rem;font-size:0.82rem;">
                <div><b>{pm}%</b><br><span style="opacity:0.65;">part modale TC</span></div>
                <div><b>{ponc}%</b><br><span style="opacity:0.65;">ponctualité</span></div>
                <div><b>{co2:,}t</b><br><span style="opacity:0.65;">CO₂ évité</span></div>
                <div><b>{bn}</b><br><span style="opacity:0.65;">bottlenecks</span></div>
                <div><b>{sat}/10</b><br><span style="opacity:0.65;">satisfaction</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
