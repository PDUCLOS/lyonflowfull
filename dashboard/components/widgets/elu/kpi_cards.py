"""Widget — 5 KPI cards ronds avec sparklines Altair (Sprint 11).

Sprint 8  — KPIs chargés via data_loader.cached_elu_kpis_dict().
Sprint 11 — Ajout sparklines 12 mois via Altair.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_elu_kpis_dict


def _build_sparkline(history: list, target: float = 0) -> alt.Chart | None:
    """Construit un sparkline Altair compact pour un historique de valeurs."""
    n = len(history)
    if n == 0:
        return None

    today = datetime.now()
    start = (today.replace(day=1) - timedelta(days=30 * 11)).replace(day=1)
    month_labels = [
        (start + timedelta(days=30 * i)).strftime("%b") for i in range(n)
    ]

    df = pd.DataFrame({"month": month_labels, "value": history})
    if target and target > 0:
        df["target"] = target

    base = alt.Chart(df).encode(
        x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=-30))
    )

    line = base.mark_line(
        color=COLORS["persona_elu_accent"],
        strokeWidth=2,
        point=alt.MarkPointConfig(color=COLORS["persona_elu_accent"], size=30),
    ).encode(
        y=alt.Y("value:Q", title=None, axis=alt.Axis(ticks=False, labels=False))
    )

    layers = [line]

    if target and target > 0:
        rule = (
            alt.Chart(pd.DataFrame({"target": [target]}))
            .mark_rule(
                color=COLORS["status_ok"],
                strokeDash=[4, 3],
                strokeWidth=1.5,
            )
            .encode(y="target:Q")
        )
        layers.append(rule)

    return (
        alt.layer(*layers)
        .properties(height=80)
        .configure_view(stroke="transparent")
        .configure_axis(domainOpacity=0)
    )


def render_kpi_cards() -> None:
    """Affiche les 5 KPI cards ronds avec sparklines Altair (12 mois)."""
    kpis = cached_elu_kpis_dict(force_mock=False)
    kpi_keys = list(kpis.keys())
    if not kpi_keys:
        st.info("Aucun KPI disponible.")
        return

    # Ligne 1 : cards de métriques
    cols = st.columns(len(kpi_keys))
    for col, key in zip(cols, kpi_keys):
        k = kpis[key]
        current = k.get("current", 0) or 0
        unit = k.get("unit", "") or ""
        delta = k.get("delta_ytd", 0) or 0
        target = k.get("target_2026", 0) or 0

        d_color = COLORS["status_ok"] if delta >= 0 else COLORS["status_critical"]
        if isinstance(delta, bool):
            delta_str = "—"
        elif isinstance(delta, float):
            delta_str = f"{delta:+.1f}"
        else:
            delta_str = f"{delta:+d}"

        if isinstance(current, bool):
            value_str = "✅" if current else "❌"
        elif isinstance(current, int) and abs(current) > 1000:
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

    # Ligne 2 : sparklines 12 mois
    spark_cols = st.columns(len(kpi_keys))
    for col, key in zip(spark_cols, kpi_keys):
        k = kpis[key]
        history = k.get("history", [])
        target = k.get("target_2026", 0) or 0

        with col:
            if not history:
                st.caption(f"Pas d'historique — {k.get('label', key)}")
            else:
                chart = _build_sparkline(history, target)
                if chart:
                    st.altair_chart(chart, use_container_width=True)