"""Widget — 5 KPI cards ronds (part modale, ponctualité, CO2, bottlenecks, satisfaction).

Sprint 8 — KPIs chargés via data_loader.cached_elu_kpis_dict().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import delta_color
from dashboard.components.data_cache import cached_elu_kpis_dict


def render_kpi_cards() -> None:
    """Affiche les 5 KPI cards ronds avec deltas colorés."""
    kpis = cached_elu_kpis_dict()
    kpi_keys = list(kpis.keys())
    # Adapter le nb de colonnes au nb de KPIs (sinon clés 6+ silencieusement perdues)
    if not kpi_keys:
        st.info("Aucun KPI disponible.")
        return
    cols = st.columns(len(kpi_keys))

    for col, key in zip(cols, kpi_keys):
        k = kpis[key]
        # None-safe : DB peut renvoyer NULL
        current = k.get("current", 0) or 0
        unit = k.get("unit", "") or ""
        delta = k.get("delta_ytd", 0) or 0
        target = k.get("target_2026", 0) or 0

        d_color = delta_color(delta)
        # Exclure bool (sous-classe de int)
        if isinstance(delta, bool):
            delta_str = "—"
        elif isinstance(delta, float):
            delta_str = f"{delta:+.1f}"
        else:
            delta_str = f"{delta:+d}"

        if isinstance(current, bool):
            value_str = "✅" if current else "❌"
        elif isinstance(current, int) and current > 1000:
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
                            {delta_str}
                        </div>
                        <div class="lyonflow-kpi-target">{target_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
