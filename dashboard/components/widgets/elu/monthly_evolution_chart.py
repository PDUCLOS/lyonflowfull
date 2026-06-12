"""Widget — Évolution mensuelle multi-KPI en Altair (Sprint 11).

Affiche un graphique multi-lignes Altair avec un onglet par KPI_key,
plus une vue agrégée avec tous les KPIs normalisés.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_elu_kpis_dict


KPI_LABEL_MAP = {
    "part_modale_tc": "Part modale TC (%)",
    "ponctualite": "Ponctualité (%)",
    "co2_evite_tonnes": "CO₂ évité (t)",
    "bottlenecks_actifs": "Bottlenecks",
    "satisfaction_pct": "Satisfaction (%)",
}

KPI_COLOR_MAP = {
    "part_modale_tc": "#818CF8",  # indigo clair
    "ponctualite": "#10B981",  # emerald
    "co2_evite_tonnes": "#F59E0B",  # amber
    "bottlenecks_actifs": "#EF4444",  # red
    "satisfaction_pct": "#3B82F6",  # blue
}


def _make_month_labels(n: int) -> list[str]:
    """Génère les labels de mois glissants (12 derniers mois)."""
    today = datetime.now()
    start = (today.replace(day=1) - timedelta(days=30 * 11)).replace(day=1)
    return [(start + timedelta(days=30 * i)).strftime("%b %Y") for i in range(n)]


def _build_kpi_chart(df: pd.DataFrame, kpi_key: str) -> alt.Chart | None:
    """Construit un graphique ligne + target pour un KPI donné."""
    sub = df[df["kpi_key"] == kpi_key].copy()
    if sub.empty:
        return None

    color = KPI_COLOR_MAP.get(kpi_key, COLORS["persona_elu_accent"])
    label = KPI_LABEL_MAP.get(kpi_key, kpi_key)

    chart = (
        alt.Chart(sub)
        .mark_line(strokeWidth=3, point=alt.MarkPointConfig(color=color, size=60))
        .encode(
            x=alt.X("month_idx:Q", title="Mois", axis=alt.Axis(labelExpr="datum.label")),
            y=alt.Y("value:Q", title=label, scale=alt.Scale(zero=False)),
            tooltip=["month_label:N", "value:Q"],
        )
        .properties(title=f"Évolution — {label}", height=280)
        .configure_view(stroke="transparent")
        .configure_axis(domainOpacity=0)
    )

    # Ligne cible
    target = sub["target_value"].iloc[0] if not sub.empty else None
    if target and target > 0:
        rule = (
            alt.Chart(pd.DataFrame({"target": [target]}))
            .mark_rule(color=COLORS["status_ok"], strokeDash=[5, 4], strokeWidth=1.5)
            .encode(y="target:Q")
        )
        chart = alt.layer(chart, rule)

    return chart


def render_monthly_evolution() -> None:
    """Affiche les graphiques d'évolution mensuelle pour chaque KPI."""
    kpis = cached_elu_kpis_dict(force_mock=False)

    if not kpis:
        st.info("Aucun KPI disponible.")
        return

    # Construire le DataFrame multi-KPI pour la vue agrégée
    rows = []
    for kpi_key, kpi_data in kpis.items():
        history = kpi_data.get("history", [])
        target = kpi_data.get("target_2026", 0) or 0
        for idx, val in enumerate(history):
            rows.append(
                {
                    "kpi_key": kpi_key,
                    "month_idx": idx,
                    "value": val,
                    "target_value": target,
                    "label": KPI_LABEL_MAP.get(kpi_key, kpi_key),
                    "color": KPI_COLOR_MAP.get(kpi_key, COLORS["persona_elu_accent"]),
                }
            )

    if not rows:
        st.info("Historique KPI vide.")
        return

    df = pd.DataFrame(rows)

    # Labels de mois pour l'axe X
    n = max((r["month_idx"] + 1 for r in rows), default=0)
    month_labels = _make_month_labels(n)

    # Tab 1 : Vue agrégée (tous les KPIs superposés, normalisés 0-100)
    with st.expander("📊 Vue agrégée — tous les KPIs superposés", expanded=False):
        # Normalisation min-max pour comparer les tendances
        from numpy import nanmin, nanmax

        def norm(s: pd.Series) -> pd.Series:
            mn, mx = nanmin(s), nanmax(s)
            if mx == mn:
                return s * 0
            return (s - mn) / (mx - mn) * 100

        df_norm = df.copy()
        df_norm["value_norm"] = df_norm.groupby("kpi_key")["value"].transform(norm)
        df_norm["month_label"] = df_norm["month_idx"].map(
            lambda i: month_labels[int(i)] if i < len(month_labels) else ""
        )

        norm_chart = (
            alt.Chart(df_norm)
            .mark_line(strokeWidth=2, point=alt.MarkPointConfig(size=40))
            .encode(
x=alt.X("month_idx:Q", title="Mois", axis=alt.Axis(labelExpr="datum.label")),
                y=alt.Y("value_norm:Q", title="% normalisé", scale=alt.Scale(zero=False)),
                color=alt.Color("kpi_key:N", title="KPI", legend=alt.Legend(orient="bottom")),
                tooltip=["month_label:N", "label:N", "value:Q"],
            )
            .properties(title="Tous les KPIs — tendances normalisées", height=300)
            .configure_view(stroke="transparent")
            .configure_axis(domainOpacity=0)
        )
        st.altair_chart(norm_chart, use_container_width=True)

    # Tab 2..N+2 : un graphique par KPI
    tabs = st.tabs(
        [KPI_LABEL_MAP.get(k, k) for k in kpis.keys()]
        + ["Tous"]
        if len(kpis) < 5
        else list(kpis.keys())
    )

    for tab, (kpi_key, kpi_data) in zip(tabs[: len(kpis)], kpis.items()):
        with tab:
            sub = df[df["kpi_key"] == kpi_key].copy()
            sub["month_label"] = sub["month_idx"].map(
                lambda i: month_labels[int(i)] if i < len(month_labels) else ""
            )
            chart = _build_kpi_chart(sub, kpi_key)
            if chart:
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption(f"Pas de données pour {kpi_key}.")