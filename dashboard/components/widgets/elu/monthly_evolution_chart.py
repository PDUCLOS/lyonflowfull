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


def _kpi_label(kpi_key: str) -> str:
    """Dérive un label lisible depuis le kpi_key (fallback si non reconnu)."""
    label_map = {
        "part_modale_tc": "Part modale TC",
        "ponctualite": "Ponctualité",
        "co2_evite_tonnes": "CO₂ évité",
        "bottlenecks_actifs": "Bottlenecks",
        "satisfaction_pct": "Satisfaction",
        "total_trips": "Trajets totaux",
        "avg_speed_kmh": "Vitesse moy. (km/h)",
        "prediction_accuracy": "Précision prédiction",
        "congestion_index": "Indice congestion",
    }
    return label_map.get(kpi_key, kpi_key.replace("_", " ").title())


def _kpi_unit(kpi_key: str) -> str:
    """Dérive l'unité depuis le kpi_key."""
    unit_map = {
        "part_modale_tc": "%",
        "ponctualite": "%",
        "co2_evite_tonnes": "t",
        "bottlenecks_actifs": "",
        "satisfaction_pct": "/10",
        "total_trips": "",
        "avg_speed_kmh": "km/h",
        "prediction_accuracy": "%",
        "congestion_index": "",
    }
    return unit_map.get(kpi_key, "")


KPI_COLOR_LIST = [
    "#818CF8",  # indigo clair
    "#10B981",  # emerald
    "#F59E0B",  # amber
    "#EF4444",  # red
    "#3B82F6",  # blue
    "#A78BFA",  # violet
    "#34D399",  # emerald light
    "#FBBF24",  # amber light
]


def _kpi_color(kpi_key: str, idx: int) -> str:
    """Dérive une couleur depuis l'index du KPI."""
    color_map = {
        "part_modale_tc": "#818CF8",
        "ponctualite": "#10B981",
        "co2_evite_tonnes": "#F59E0B",
        "bottlenecks_actifs": "#EF4444",
        "satisfaction_pct": "#3B82F6",
        "total_trips": "#818CF8",
        "avg_speed_kmh": "#10B981",
        "prediction_accuracy": "#F59E0B",
        "congestion_index": "#EF4444",
    }
    return color_map.get(kpi_key, KPI_COLOR_LIST[idx % len(KPI_COLOR_LIST)])


def _make_month_labels(n: int) -> list[str]:
    """Génère les labels de mois glissants (12 derniers mois)."""
    today = datetime.now()
    start = (today.replace(day=1) - timedelta(days=30 * 11)).replace(day=1)
    return [(start + timedelta(days=30 * i)).strftime("%b %Y") for i in range(n)]


def _build_kpi_chart(df_sub: pd.DataFrame, kpi_key: str, month_labels: list[str]) -> alt.Chart:
    """Construit un graphique ligne + target pour un sous-ensemble de données."""
    color = _kpi_color(kpi_key, 0)
    label = _kpi_label(kpi_key)

    chart = (
        alt.Chart(df_sub)
        .mark_line(strokeWidth=3, point=alt.MarkPointConfig(color=color, size=60))
        .encode(
            x=alt.X("month_idx:Q", title="Mois"),
            y=alt.Y("value:Q", title=label, scale=alt.Scale(zero=False)),
            tooltip=["month_label:N", "value:Q"],
        )
        .properties(title=f"Évolution — {label}", height=280)
        .configure_view(stroke="transparent")
        .configure_axis(domainOpacity=0)
    )

    target = df_sub["target_value"].iloc[0] if not df_sub.empty and "target_value" in df_sub.columns else None
    if target and target > 0:
        rule = (
            alt.Chart(pd.DataFrame({"target": [float(target)]}))
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

    rows = []
    for idx, (kpi_key, _kpi_data) in enumerate(kpis.items()):
        history = kpi_data.get("history", [])
        target = kpi_data.get("target_2026", 0) or 0
        label = kpi_data.get("label", _kpi_label(kpi_key))
        for j, val in enumerate(history):
            rows.append(
                {
                    "kpi_key": kpi_key,
                    "month_idx": j,
                    "value": val,
                    "target_value": target,
                    "label": label,
                    "color": _kpi_color(kpi_key, idx),
                }
            )

    if not rows:
        st.info("Historique KPI vide.")
        return

    df = pd.DataFrame(rows)
    n = max((r["month_idx"] + 1 for r in rows), default=0)
    month_labels = _make_month_labels(n)

    # Vue agrégée (expander) — tous les KPIs superposés, normalisés 0-100
    with st.expander("📊 Vue agrégée — tous les KPIs superposés", expanded=False):
        try:
            from numpy import nanmax, nanmin

            def norm(s: pd.Series) -> pd.Series:
                mn, mx = nanmin(s), nanmax(s)
                if mx == mn:
                    return s * 0.0
                return (s - mn) / (mx - mn) * 100.0

            df_norm = df.copy()
            df_norm["value_norm"] = df_norm.groupby("kpi_key")["value"].transform(norm)
            df_norm["month_label"] = df_norm["month_idx"].map(
                lambda i: month_labels[int(i)] if int(i) < len(month_labels) else ""
            )

            norm_chart = (
                alt.Chart(df_norm)
                .mark_line(strokeWidth=2, point=alt.MarkPointConfig(size=40))
                .encode(
                    x=alt.X("month_idx:Q", title="Mois"),
                    y=alt.Y("value_norm:Q", title="% normalisé", scale=alt.Scale(zero=False)),
                    color=alt.Color("kpi_key:N", title="KPI", legend=alt.Legend(orient="bottom")),
                    tooltip=["month_label:N", "label:N", "value:Q"],
                )
                .properties(title="Tous les KPIs — tendances normalisées", height=300)
                .configure_view(stroke="transparent")
                .configure_axis(domainOpacity=0)
            )
            st.altair_chart(norm_chart, use_container_width=True)
        except Exception:
            st.warning("Impossible de générer la vue agrégée.")

    # Tabs : un onglet par KPI
    tab_labels = [_kpi_label(k) for k in kpis]
    tabs = st.tabs(tab_labels)

    for tab, (kpi_key, _kpi_data) in zip(tabs, kpis.items()):
        with tab:
            sub = df[df["kpi_key"] == kpi_key].copy()
            sub["month_label"] = sub["month_idx"].map(
                lambda i: month_labels[int(i)] if int(i) < len(month_labels) else ""
            )
            if sub.empty:
                st.caption(f"Pas de données pour {kpi_key}.")
            else:
                chart = _build_kpi_chart(sub, kpi_key, month_labels)
                st.altair_chart(chart, use_container_width=True)
