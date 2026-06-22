"""Widget — Source Health Monitor (Pro TCL — Pipeline).

Sprint 16 Axe B (2026-06-20) — Monitoring multi-source. Remplace les
6 health checks séquentiels de ``src.monitoring.health_checks.py`` par
une vue agrégée (``gold.v_source_health``, migration 021) + jauge Plotly
synthétique 0-100 + grille par source + section complétude Silver.

Cible : Pro_6_Pipeline_Mgmt (en haut de page, avant les DAG KPIs).

Contenu :
1. **Score global** (bandeau) : moyenne pondérée des health_score.
   Poids : trafic=3, TCL=2, Vélov=2, météo=1, air_quality=1, chantiers=1,
   tomtom=1, predictions=2.
2. **Jauge Plotly 0-100** : score global + delta vs seuil acceptable 70.
3. **Grille source × statut** : 8 sources, code couleur ligne.
4. **Complétude Silver** : 3 barres de progression (trafic, TCL, vélov).

Si DB indispo → fail loud via DashboardDataError.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_data_completeness, cached_source_health
from src.data.exceptions import DashboardDataError

# Poids par source pour le score global
SOURCE_WEIGHTS = {
    "bronze.trafic_boucles": 3,
    "bronze.tcl_vehicles": 2,
    "bronze.velov": 2,
    "bronze.meteo": 1,
    "bronze.air_quality": 1,
    "bronze.chantiers": 1,
    "bronze.tomtom_traffic": 1,
    "gold.trafic_predictions": 2,
}

# Couleurs par statut
STATUS_COLORS = {
    "healthy": "#4CAF50",
    "delayed": "#FF9800",
    "stale": "#FF5722",
    "dead": "#F44336",
}


def _global_score(df: pd.DataFrame) -> float:
    """Calcule le score global pondéré 0-100.

    Si le df est vide, retourne 0.
    """
    if df.empty:
        return 0.0
    total_weight = 0
    weighted_sum = 0
    for _, row in df.iterrows():
        w = SOURCE_WEIGHTS.get(row["source"], 1)
        weighted_sum += float(row["health_score"]) * w
        total_weight += w
    return round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0


def _gauge_plotly(score: float) -> plotly.graph_objects.Figure:
    """Jauge Plotly 0-100 avec seuils colorés."""
    import plotly.graph_objects as go

    color = (
        "#4CAF50" if score >= 70
        else "#FF9800" if score >= 40
        else "#F44336"
    )
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Score santé global", "font": {"size": 18}},
            number={"suffix": " / 100", "font": {"size": 28}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": color},
                "bgcolor": "white",
                "steps": [
                    {"range": [0, 40], "color": "#FFCDD2"},
                    {"range": [40, 70], "color": "#FFE0B2"},
                    {"range": [70, 100], "color": "#C8E6C9"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 2},
                    "thickness": 0.75,
                    "value": 70,
                },
            },
        )
    )
    fig.update_layout(height=250, margin={"t": 0, "b": 0, "l": 0, "r": 0})
    return fig


def render_source_health_monitor() -> None:
    """Affiche le monitoring multi-source dans Pro_6_Pipeline_Mgmt."""
    try:
        health_df = cached_source_health()
        completeness_df = cached_data_completeness()
    except DashboardDataError as e:
        st.error(f"⚠️ Source health indisponible : {e}")
        return

    if health_df.empty:
        st.info("ℹ️ Aucune donnée de santé source (DB vide ?).")
        return

    # ── 1. Score global + jauge ────────────────────────────────────────────
    global_score = _global_score(health_df)
    col_gauge, col_kpi = st.columns([1, 2])
    with col_gauge:
        st.plotly_chart(_gauge_plotly(global_score), use_container_width=True)
    with col_kpi:
        n_healthy = int((health_df["status"] == "healthy").sum())
        n_delayed = int((health_df["status"] == "delayed").sum())
        n_stale = int((health_df["status"] == "stale").sum())
        n_dead = int((health_df["status"] == "dead").sum())
        st.markdown(
            f"""
            <div class="lyonflow-card" style="padding:0.8rem;">
                <div class="lyf-sublabel">Statut par source (8 sources Bronze + 1 Gold)</div>
                <div style="font-size:1.4rem;margin-top:0.4rem;">
                    🟢 <b>{n_healthy}</b> healthy
                    &nbsp; 🟡 <b>{n_delayed}</b> delayed
                    &nbsp; 🟠 <b>{n_stale}</b> stale
                    &nbsp; 🔴 <b>{n_dead}</b> dead
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── 2. Grille source × statut ──────────────────────────────────────────
    st.markdown("##### 📊 Santé par source (triée par score asc)")
    # Renommage pour affichage
    display = health_df.rename(columns={
        "source": "Source",
        "last_update": "Dernière MAJ",
        "age_minutes": "Âge (min)",
        "records_1h": "Records/1h",
        "expected_interval_min": "Intervalle attendu (min)",
        "health_score": "Score",
        "status": "Statut",
    }).copy()
    # Pastille de couleur via emoji (Streamlit ne supporte pas la couleur HTML dans dataframe)
    status_emoji = {
        "healthy": "🟢",
        "delayed": "🟡",
        "stale": "🟠",
        "dead": "🔴",
    }
    display["Statut"] = display["Statut"].map(lambda s: f"{status_emoji.get(s, '⚪')} {s}")
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 3. Complétude Silver (24h) ────────────────────────────────────────
    st.markdown("##### 🧪 Complétude Silver (24h glissantes)")
    if completeness_df.empty:
        st.info("ℹ️ Aucune donnée de complétude Silver (24h).")
        return

    cols = st.columns(len(completeness_df))
    for col, (_, row) in zip(cols, completeness_df.iterrows()):
        with col:
            total = int(row.get("total_rows", 0) or 0)
            geo_pct = float(row.get("geo_pct", 0) or 0)
            id_pct = float(row.get("id_pct", 0) or 0)
            speed_pct = float(row.get("speed_pct", 0) or 0)
            source_label = row["source"].replace("silver.", "").replace("_clean", "")
            st.markdown(f"**{source_label}** ({total:,} rows)")
            if speed_pct > 0:
                st.progress(speed_pct / 100.0, text=f"Vitesse: {speed_pct:.1f}%")
            st.progress(geo_pct / 100.0, text=f"Géo: {geo_pct:.1f}%")
            st.progress(id_pct / 100.0, text=f"ID: {id_pct:.1f}%")
