"""Widget — Bloc narratif 'Synthèse exécutive' auto-généré.

Sprint 8 — KPIs via data_loader.load_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_elu_kpis_dict


def render_executive_summary() -> None:
    """Affiche un bloc narratif synthétisant la situation."""
    kpis = load_elu_kpis_dict(force_mock=False)
    pm = kpis.get("part_modale_tc", {}).get("current", 0)
    ponc = kpis.get("ponctualite", {}).get("current", 0)
    co2 = kpis.get("co2_evite_tonnes", {}).get("current", 0)
    bn = kpis.get("bottlenecks_actifs", {}).get("current", 0)
    sat = kpis.get("satisfaction_pct", {}).get("current", 0)

    # Tendance globale
    pm_delta = kpis.get("part_modale_tc", {}).get("delta_ytd", 0)
    ponc_delta = kpis.get("ponctualite", {}).get("delta_ytd", 0)
    bn_delta = kpis.get("bottlenecks_actifs", {}).get("delta_ytd", 0)

    if pm_delta > 0 and bn_delta < 0:
        tendance = "🟢 **AMÉLIORATION**"
        tendance_text = (
            "La politique de mobilité porte ses fruits : la part modale TC progresse, "
            "le nombre de bottlenecks diminue, et la satisfaction usager reste stable."
        )
    elif pm_delta < 0 or ponc_delta < -1:
        tendance = "🔴 **DÉGRADATION**"
        tendance_text = (
            "La situation se dégrade sur plusieurs axes. Action corrective "
            "prioritaire recommandée."
        )
    else:
        tendance = "🟡 **STABLE**"
        tendance_text = (
            "La situation est globalement stable, mais les marges de progression "
            "demeurent importantes."
        )

    st.markdown(
        f"""
        <div class="lyonflow-card" style="background:linear-gradient(135deg, #1A1D24 0%, #1F2540 100%);
                    border-left:4px solid #3F51B5;padding:1.2rem;">
            <div style="font-size:0.75rem;opacity:0.6;text-transform:uppercase;
                        letter-spacing:1px;">Synthèse exécutive</div>
            <div style="font-size:1.1rem;margin:0.4rem 0;">{tendance}</div>
            <div style="font-size:0.9rem;line-height:1.5;opacity:0.9;">
                {tendance_text}
            </div>
            <div style="margin-top:0.8rem;display:grid;grid-template-columns:repeat(5,1fr);
                        gap:0.5rem;font-size:0.8rem;">
                <div><b>{pm}%</b> part modale TC</div>
                <div><b>{ponc}%</b> ponctualité</div>
                <div><b>{co2:,}t</b> CO₂ évité</div>
                <div><b>{bn}</b> bottlenecks</div>
                <div><b>{sat}/10</b> satisfaction</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
