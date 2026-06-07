"""Widget — 5 KPI cards ronds (part modale, ponctualité, CO2, bottlenecks, satisfaction).

Sprint 8 — KPIs chargés via data_loader.load_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_elu_kpis_dict


def render_kpi_cards() -> None:
    """Affiche les 5 KPI cards ronds avec deltas colorés."""
    kpis = load_elu_kpis_dict(force_mock=False)
    cols = st.columns(5)
    kpi_keys = list(kpis.keys())

    for col, key in zip(cols, kpi_keys):
        k = kpis[key]
        current = k.get("current", 0)
        unit = k.get("unit", "")
        delta = k.get("delta_ytd", 0)
        target = k.get("target_2026", 0)

        delta_color = "#4CAF50" if delta > 0 else "#E74C3C" if delta < 0 else "#FF9800"
        delta_str = f"{delta:+.1f}" if isinstance(delta, float) else f"{delta:+d}"

        # Format value
        if isinstance(current, int) and current > 1000:
            value_str = f"{current:,}"
        elif isinstance(current, float):
            value_str = f"{current:.1f}"
        else:
            value_str = str(current)

        target_str = f"Cible 2026 : {target}{unit}"

        with col:
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg, #1A1D24 0%, #2A2D34 100%);
                            border:1px solid #3F51B5;border-radius:12px;padding:1rem;
                            text-align:center;height:170px;display:flex;flex-direction:column;
                            justify-content:space-between;">
                    <div style="font-size:0.75rem;opacity:0.7;text-transform:uppercase;
                                letter-spacing:0.5px;">{k.get('label', '—')}</div>
                    <div style="font-size:2.2rem;font-weight:700;color:#5C6BC0;line-height:1;">
                        {value_str}<span style="font-size:1rem;opacity:0.6;">{unit}</span>
                    </div>
                    <div>
                        <div style="font-size:0.85rem;color:{delta_color};font-weight:600;">
                            {delta_str} YTD
                        </div>
                        <div style="font-size:0.7rem;opacity:0.6;margin-top:2px;">{target_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
