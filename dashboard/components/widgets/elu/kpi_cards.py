"""Widget — 5 KPI cards ronds (part modale, ponctualité, CO2, bottlenecks, satisfaction).

Sprint 8 — KPIs chargés via data_loader.load_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import delta_color
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

        d_color = delta_color(delta)
        delta_str = f"{delta:+.1f}" if isinstance(delta, float) else f"{delta:+d}"

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
                <div class="lyonflow-kpi">
                    <div class="lyonflow-kpi-label">{k.get("label", "—")}</div>
                    <div class="lyonflow-kpi-value">
                        {value_str}<span class="lyonflow-kpi-unit">{unit}</span>
                    </div>
                    <div>
                        <div class="lyonflow-kpi-delta" style="color:{d_color};">
                            {delta_str} YTD
                        </div>
                        <div class="lyonflow-kpi-target">{target_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
