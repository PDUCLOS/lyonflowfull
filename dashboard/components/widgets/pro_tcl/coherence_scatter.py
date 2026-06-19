"""Widget — Cohérence TomTom ↔ Grand Lyon (cross-validation sources).

Sprint 13+ (2026-06-18) — Nouveau widget. Compare les 2 sources
indépendantes de vitesse routière :
* **TomTom** (GPS flottes, agrégat tuiles 0.02°, ~2 km) —
  ``bronze.tomtom_traffic`` → ``gold.v_tomtom_traffic_live``
* **Boucles Grand Lyon** (capteurs inductifs au sol, ~1100 capteurs) —
  ``gold.channels_ref`` + ``gold.traffic_features_live``

JOIN spatial dans ``gold.v_coherence_tomtom_vs_grandlyon`` (migration 14) :
pour chaque tuile TomTom, on trouve les capteurs GL à < 200 m et on
calcule le delta de vitesse.

Affiche :
1. **KPI cards** : compteurs par status (ok / minor_drift / drift / no_data)
2. **Scatter plot** : TomTom_speed (x) vs GL_speed (y), colorisé par status,
   ligne y=x en pointillés. Les points loin de la ligne = drift à investiguer.
3. **Heatmap delta** : delta_kmh par (tile_key, channel_id), top 20 pires.
4. **Tableau capteurs HS suspects** : depuis ``gold.v_tomtom_gl_drift``
   (>= 60% drift sur 24h).

Si PostgreSQL indispo → fail loud via DashboardDataError.
Si TomTom pas encore alimenté → message "TomTom pas encore collecté".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import (
    cached_tomtom_coherence,
    cached_tomtom_gl_drift,
)
from src.data.exceptions import DashboardDataError

# Libellés FR pour les status SQL (cohérent avec labels.py ailleurs)
STATUS_LABELS = {
    "ok": "Cohérent",
    "minor_drift": "Drift léger",
    "drift": "Drift fort",
    "no_data": "Pas de mesure GL",
}
STATUS_COLORS = {
    "ok": COLORS.get("status_ok", "#4CAF50"),
    "minor_drift": COLORS.get("status_warning", "#FF9800"),
    "drift": COLORS.get("status_critical", "#F44336"),
    "no_data": "#9E9E9E",
}
SENSOR_HEALTH_LABELS = {
    "healthy": "Sain",
    "watch": "À surveiller",
    "suspect": "Suspect HS",
    "no_data": "Pas de données",
}
SENSOR_HEALTH_COLORS = {
    "healthy": COLORS.get("status_ok", "#4CAF50"),
    "watch": COLORS.get("status_warning", "#FF9800"),
    "suspect": COLORS.get("status_critical", "#F44336"),
    "no_data": "#9E9E9E",
}


def _status_counts(df: pd.DataFrame) -> dict[str, int]:
    """Compte les paires par status."""
    counts = {"ok": 0, "minor_drift": 0, "drift": 0, "no_data": 0}
    if df.empty or "status" not in df.columns:
        return counts
    for s, n in df["status"].value_counts().items():
        if s in counts:
            counts[s] = int(n)
    return counts


def _scatter_tomtom_vs_gl(df: pd.DataFrame) -> None:
    """Scatter Plotly : TomTom speed (x) vs GL speed (y), colorisé par status."""
    import plotly.graph_objects as go

    if df.empty:
        st.info("Aucune paire (tile TomTom, capteur GL) à comparer.")
        return

    # Filtrer les no_data pour le scatter (sinon ça pollue)
    plot_df = df.dropna(subset=["tomtom_speed_kmh", "gl_speed_kmh"]).copy()
    if plot_df.empty:
        st.info("Aucune paire avec mesure GL + TomTom disponible.")
        return

    fig = go.Figure()

    # Ligne y=x (cohérence parfaite) en pointillé gris
    speed_max = max(
        float(plot_df["tomtom_speed_kmh"].max()),
        float(plot_df["gl_speed_kmh"].max()),
        80.0,
    )
    fig.add_trace(
        go.Scatter(
            x=[0, speed_max],
            y=[0, speed_max],
            mode="lines",
            line=dict(color="#9E9E9E", dash="dash", width=1),
            name="y = x (parfait)",
            hoverinfo="skip",
            showlegend=True,
        )
    )

    # Bandes de tolérance ±10 km/h (status=ok) et ±20 km/h (minor_drift)
    fig.add_trace(
        go.Scatter(
            x=[0, speed_max],
            y=[10, speed_max + 10],
            mode="lines",
            line=dict(color="rgba(76,175,80,0.2)", width=0),
            fill="tonexty",
            fillcolor="rgba(76,175,80,0.08)",
            name="±10 km/h (ok)",
            hoverinfo="skip",
            showlegend=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[10, speed_max + 10],
            y=[0, speed_max],
            mode="lines",
            line=dict(color="rgba(76,175,80,0.2)", width=0),
            fill="tonexty",
            fillcolor="rgba(76,175,80,0.08)",
            name="±10 km/h (ok)",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Points par status (couleur)
    for status, color in STATUS_COLORS.items():
        if status == "no_data":
            continue  # déjà filtré
        sub = plot_df[plot_df["status"] == status]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["tomtom_speed_kmh"],
                y=sub["gl_speed_kmh"],
                mode="markers",
                marker=dict(color=color, size=10, opacity=0.75, line=dict(color="white", width=1)),
                name=f"{STATUS_LABELS[status]} ({len(sub)})",
                customdata=sub[["tile_key", "channel_id", "site_name", "delta_kmh"]].values,
                hovertemplate=(
                    "<b>%{customdata[1]}</b> %{customdata[2]}<br>"
                    "Tuile : %{customdata[0]}<br>"
                    "TomTom : %{x:.1f} km/h<br>"
                    "GL : %{y:.1f} km/h<br>"
                    "Δ : %{customdata[3]:+.1f} km/h<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="TomTom (x) vs Grand Lyon (y) — vitesse km/h",
        xaxis_title="TomTom (km/h)",
        yaxis_title="Grand Lyon (km/h)",
        height=520,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(range=[0, speed_max * 1.05])
    fig.update_yaxes(range=[0, speed_max * 1.05])
    st.plotly_chart(fig, use_container_width=True)


def _heatmap_delta(df: pd.DataFrame, top_n: int = 20) -> None:
    """Heatmap horizontale : top N pires paires par |delta|."""
    if df.empty or "delta_kmh" not in df.columns:
        st.info("Aucun delta à afficher.")
        return

    plot_df = df.dropna(subset=["delta_kmh"]).copy()
    plot_df["abs_delta"] = plot_df["delta_kmh"].abs()
    plot_df = plot_df.nlargest(top_n, "abs_delta")

    label = plot_df["channel_id"].astype(str) + " · " + plot_df["site_name"].fillna("?").astype(str)

    import plotly.graph_objects as go

    fig = go.Figure(
        go.Bar(
            x=plot_df["delta_kmh"],
            y=label,
            orientation="h",
            marker_color=[
                STATUS_COLORS["drift"]
                if abs(d) > 20
                else STATUS_COLORS["minor_drift"]
                if abs(d) > 10
                else STATUS_COLORS["ok"]
                for d in plot_df["delta_kmh"]
            ],
            text=[f"{d:+.1f}" for d in plot_df["delta_kmh"]],
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Δ : %{x:+.1f} km/h<br>"
                "TomTom : %{customdata[0]:.1f}<br>"
                "GL : %{customdata[1]:.1f}<extra></extra>"
            ),
            customdata=plot_df[["tomtom_speed_kmh", "gl_speed_kmh"]].values,
        )
    )
    fig.update_layout(
        title=f"Top {top_n} paires par |delta| km/h (détection drift)",
        xaxis_title="Delta (TomTom − GL) en km/h",
        yaxis_title="Capteur Grand Lyon",
        height=max(280, 22 * len(plot_df) + 80),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def _drift_table(drift_df: pd.DataFrame) -> None:
    """Tableau des capteurs GL suspectés HS."""
    if drift_df.empty:
        st.info("Aucun capteur GL avec drift significatif détecté sur 24h.")
        return

    rows = []
    for _, r in drift_df.iterrows():
        health = str(r.get("sensor_health", "no_data"))
        rows.append(
            {
                "Channel": r.get("channel_id", "?"),
                "Site": r.get("site_name", "—") or "—",
                "Paires (24h)": int(r.get("n_pairs", 0) or 0),
                "En drift": int(r.get("n_drift", 0) or 0),
                "Ratio drift": f"{float(r.get('drift_ratio', 0) or 0) * 100:.0f} %",
                "Δ̄ abs (km/h)": f"{float(r.get('avg_abs_delta_kmh', 0) or 0):.1f}",
                "Δ max (km/h)": f"{float(r.get('max_abs_delta_kmh', 0) or 0):.1f}",
                "Santé": SENSOR_HEALTH_LABELS.get(health, health),
            }
        )
    df_disp = pd.DataFrame(rows)

    # Badge de couleur sur la colonne Santé via Styler
    def _color_health(val: str) -> str:
        for k, label in SENSOR_HEALTH_LABELS.items():
            if val == label:
                color = SENSOR_HEALTH_COLORS.get(k, "#9E9E9E")
                return f"background-color: {color}; color: white; font-weight: 600; text-align: center;"
        return ""

    st.dataframe(
        df_disp.style.map(_color_health, subset=["Santé"]),
        use_container_width=True,
        hide_index=True,
    )


def render_coherence_scatter() -> None:
    """Affiche le widget Cohérence TomTom ↔ Grand Lyon.

    Sprint 13+ (2026-06-18). Si DB indispo → fail loud via DashboardDataError.
    Si TomTom pas encore collecté (table vide) → bandeau info "TomTom vide".
    """
    try:
        df = cached_tomtom_coherence(limit=500)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if df.empty:
        st.info(
            "Aucune donnée de cohérence TomTom ↔ Grand Lyon disponible. "
            "Causes possibles : (1) DAG `collect_tomtom_traffic` n'a pas encore "
            "tourné, (2) `TOMTOM_API_KEY` non configuré côté Airflow, "
            "(3) aucun capteur Grand Lyon à < 200 m d'une tuile TomTom. "
            "Lancez le DAG manuellement depuis l'UI Airflow pour amorcer."
        )
        return

    # KPI cards par status
    counts = _status_counts(df)
    n_total = sum(counts.values())
    st.markdown(f"##### {n_total} paires (tuile TomTom × capteur GL à < 200 m)")

    cols = st.columns(4)
    for col, (status, color) in zip(cols, STATUS_COLORS.items()):
        with col:
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                    <div style="font-size:0.85rem;opacity:0.8;">
                        {STATUS_LABELS[status]}
                    </div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.2rem 0;">
                        {counts[status]}
                    </div>
                    <div style="font-size:0.75rem;opacity:0.6;">
                        {counts[status] / max(n_total, 1) * 100:.0f}% des paires
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Scatter TomTom vs GL
    _scatter_tomtom_vs_gl(df)

    st.markdown("---")

    # Top pires deltas
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("##### Top 20 pires deltas (détection drift)")
        _heatmap_delta(df, top_n=20)
    with col2:
        st.markdown("##### Capteurs GL suspectés HS (24h)")
        try:
            drift_df = cached_tomtom_gl_drift(limit=50)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            drift_df = pd.DataFrame()
        # Filtre : on priorise suspect et watch
        if not drift_df.empty and "sensor_health" in drift_df.columns:
            drift_df = drift_df[drift_df["sensor_health"].isin(["suspect", "watch"])].head(15)
        _drift_table(drift_df)

    st.caption(
        "Données : `bronze.tomtom_traffic` (DAG `collect_tomtom_traffic */15`) "
        "× `gold.channels_ref` (jointure spatiale < 200 m via PostGIS ST_DWithin). "
        "Statut : ok |Δ|≤10, minor_drift ≤20, drift >20 km/h."
    )
