"""Widget — Alerte report modal Vélov ↔ TC (Axe 4, Sprint 17, 2026-06-20).

Vue matérialisée ``gold.mv_velov_transit_coupling`` (migration 023) qui
calcule, pour chaque station Vélov située à < 300m d'une zone où circule
une ligne TC, le **z-score** du nombre de vélos disponibles (= combien
d'écarts-types en dessous de la moyenne horaire 7j).

**Hypothèse** : si plusieurs stations Vélov proches d'une même ligne TC
sont en alarme simultanée (z_score < -2), c'est probablement un **report
modal** : un incident sur cette ligne TC (panne métro, tram interrompu,
travaux) fait basculer les usagers vers le Vélov. Les stations se vident
plus vite que d'habitude.

Affiche :
1. **Bandeau KPI** : compteur d'anomalies + lignes TC en alerte
   (critical si >= 3 stations, warning si >= 1).
2. **Tableau** : stations en alerte, triées par z-score croissant
   (les plus extrêmes en premier).
3. **Bar chart Plotly** : top 10 lignes TC en alerte (nb stations).

Si PostgreSQL indispo → fail loud via ``DashboardDataError``. Si vue vide
(DAG refresh pas encore passé) → message d'attente explicite.

Cf. docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §5 pour la spec complète.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.data_cache import (
    cached_velov_transit_coupling,
    cached_velov_transit_coupling_summary,
)
from src.data.exceptions import DashboardDataError

# Libellés FR pour les alertes (cohérent avec le reste du dashboard)
ALERT_LEVEL_LABELS = {
    "critical": "🔴 Critique",
    "warning": "🟠 Vigilance",
    "ok": "🟢 OK",
}

# Couleurs par alert level (cohérent avec couleurs bottlenecks carte Folium)
ALERT_LEVEL_COLORS = {
    "critical": "#F44336",  # rouge
    "warning": "#FF9800",  # orange
    "ok": "#4CAF50",  # vert
}

# Seuil z-score pour anomalie (constant — doit matcher celui de la MV migration 023)
ANOMALY_Z_THRESHOLD = -2.0


def _format_z_score(val: float | None) -> str:
    """Format z-score : rouge si < seuil, vert sinon, gris si None."""
    if pd.isna(val):
        return "—"
    if val < ANOMALY_Z_THRESHOLD:
        return f"🔴 {val:.2f}"
    if val < 0:
        return f"🟡 {val:.2f}"
    return f"🟢 +{val:.2f}"


def _count_anomalies(df: pd.DataFrame) -> int:
    """Compte le nombre de stations en alarme (anomaly_detected = TRUE)."""
    if df.empty or "anomaly_detected" not in df.columns:
        return 0
    return int(df["anomaly_detected"].sum())


def _count_critical_lines(summary_df: pd.DataFrame) -> tuple[int, int]:
    """Compte les lignes TC en alerte (critical + warning).

    Returns:
        (n_critical, n_warning)
    """
    if summary_df.empty or "alert_level" not in summary_df.columns:
        return 0, 0
    n_critical = int((summary_df["alert_level"] == "critical").sum())
    n_warning = int((summary_df["alert_level"] == "warning").sum())
    return n_critical, n_warning


def _render_kpi_banner(df: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    """4 KPI cards résumant l'état du report modal."""
    n_anomalies = _count_anomalies(df)
    n_critical, n_warning = _count_critical_lines(summary_df)
    n_stations_total = len(df)
    n_lines_total = len(summary_df)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "🚲 Stations Vélov en alarme",
            value=n_anomalies,
            help="Stations avec z_score < -2 (vidange anormale)",
        )
    with col2:
        st.metric(
            "🔴 Lignes TC critiques",
            value=n_critical,
            help="Lignes avec >= 3 stations Vélov en alarme",
        )
    with col3:
        st.metric(
            "🟠 Lignes TC en vigilance",
            value=n_warning,
            help="Lignes avec 1-2 stations en alarme",
        )
    with col4:
        st.metric(
            "📊 Couverture",
            value=f"{n_stations_total} stations / {n_lines_total} lignes",
            help="Stations Vélov < 300m d'une zone TC, lignes TC distinctes",
        )


def _render_anomaly_table(df: pd.DataFrame) -> None:
    """Tableau des stations en alarme (anomaly_detected = TRUE), triées par z-score."""
    anomalies = df[df["anomaly_detected"]].copy() if not df.empty else pd.DataFrame()
    if anomalies.empty:
        st.info(
            "Aucune station Vélov en alarme. Le réseau est nominal. "
            "(Pour rappel : alarme = z_score < -2σ, soit 2 écarts-types en "
            "dessous de la moyenne horaire 7 jours.)"
        )
        return

    rows = []
    for _, r in anomalies.iterrows():
        rows.append(
            {
                "Station": str(r["station_name"] or r["station_id"]),
                "Ligne TC": str(r["transit_line"]),
                "Vélo maintenant": int(r["bikes_now"]) if pd.notna(r["bikes_now"]) else "—",
                "Baseline 7j": (f"{float(r['baseline_avg_bikes']):.1f}" if pd.notna(r["baseline_avg_bikes"]) else "—"),
                "Z-score": _format_z_score(r.get("z_score")),
                "Distance (m)": int(r["distance_to_line_m"]) if pd.notna(r["distance_to_line_m"]) else "—",
            }
        )
    df_disp = pd.DataFrame(rows)
    st.dataframe(df_disp, use_container_width=True, hide_index=True)
    st.caption(f"**{len(anomalies)} stations** en alarme. Triées par z-score croissant (les plus extrêmes en premier).")


def _render_lines_chart(summary_df: pd.DataFrame) -> None:
    """Bar chart Plotly : top 10 lignes TC par nb stations en alarme."""
    if summary_df.empty:
        return
    top = summary_df[summary_df["n_stations_anomaly"] > 0].head(10)
    if top.empty:
        st.info("Aucune ligne TC avec stations en alarme.")
        return

    top = top.copy()
    top["alert_label"] = top["alert_level"].map(lambda lvl: ALERT_LEVEL_LABELS.get(lvl, lvl))
    top["color"] = top["alert_level"].map(lambda lvl: ALERT_LEVEL_COLORS.get(lvl, "#9E9E9E"))

    fig = go.Figure(
        go.Bar(
            x=top["transit_line"],
            y=top["n_stations_anomaly"],
            marker_color=top["color"],
            text=top["n_stations_anomaly"],
            textposition="outside",
            hovertemplate=("<b>Ligne %{x}</b><br>Stations en alarme : %{y}<br>Niveau : %{customdata}<extra></extra>"),
            customdata=top["alert_label"],
        )
    )
    fig.update_layout(
        title="Top 10 lignes TC par nombre de stations Vélov en alarme",
        xaxis_title="Ligne TC",
        yaxis_title="Stations en alarme (z < -2)",
        height=380,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_modal_shift_alert() -> None:
    """Affiche l'alerte report modal Vélov ↔ TC (Axe 4, Sprint 17).

    Sprint 17 (2026-06-20). Si DB indispo → fail loud via DashboardDataError.
    Si vue matérialisée pas encore alimentée → message d'attente explicite.
    """
    try:
        df = cached_velov_transit_coupling(anomalies_only=False)
        summary_df = cached_velov_transit_coupling_summary()
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if df.empty:
        st.info(
            "Vue matérialisée `gold.mv_velov_transit_coupling` pas encore "
            "alimentée. Le DAG `refresh_velov_transit_coupling` doit tourner "
            "(toutes les 15 min). Causes possibles : (1) DAG en attente de "
            "son 1er cycle, (2) `migration_023_velov_transit_coupling.sql` "
            "non appliquée, (3) `gold.tcl_vehicle_realtime` ou "
            "`silver.velov_clean` vides."
        )
        return

    # Bandeau KPI
    st.markdown("##### Report modal Vélov ↔ TC (rayon 300m, z-score < -2σ)")
    _render_kpi_banner(df, summary_df)

    st.markdown("---")

    # Tableau des anomalies
    st.markdown("##### Stations Vélov en alarme")
    _render_anomaly_table(df)

    st.markdown("---")

    # Bar chart : top lignes TC
    st.markdown("##### Lignes TC avec stations en alarme")
    _render_lines_chart(summary_df)

    st.caption(
        "Données : `silver.velov_clean` × `gold.tcl_vehicle_realtime` (centres "
        "de zone par ligne) — JOIN spatial PostGIS `ST_DWithin < 300 m`. "
        "Z-score calculé sur baseline horaire 7j par (station, hour_of_day). "
        "Vue `gold.mv_velov_transit_coupling` (migration 023). "
        "Refresh */15 min par `dags/maintenance/refresh_velov_transit_coupling.py`. "
        "Spec : `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` §5."
    )
