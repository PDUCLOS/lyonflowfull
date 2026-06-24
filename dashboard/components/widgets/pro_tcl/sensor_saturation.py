"""Widget — Saturation + amplitude par capteur (Sprint 22+).

Affiche pour chaque capteur du réseau routier lyonnais :
* Saturation actuelle (vitesse / v85 7j) en %
* Amplitude 24h normalisée (%)
* Statut de santé (ok / stale / stuck / no_data)
* Code couleur : 🟢 ok · 🟡 stale · 🔴 stuck · ⚪ no_data

Sources :
* ``gold.mv_sensor_saturation`` (migration 034 (matérialisée)) via
  ``cached_sensor_saturation()`` (TTL 60s)

Câblage : Pro_6_Pipeline_Mgmt (cohérent avec render_source_health_monitor
et render_data_quality_badge, autres widgets de health).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_sensor_saturation
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.exceptions import DashboardDataError

_STATUS_COLOR = {
    "ok": "#4CAF50",       # vert
    "stale": "#FFC107",    # jaune (warning)
    "stuck": "#F44336",    # rouge (critical)
    "no_data": "#9E9E9E",  # gris
}

_STATUS_EMOJI = {
    "ok": "🟢",
    "stale": "🟡",
    "stuck": "🔴",
    "no_data": "⚪",
}


def _render_kpi_banner(counts: dict[str, int], n_total: int) -> None:
    """Bandeau 4 KPIs : nb capteurs par statut."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🟢 OK", counts.get("ok", 0))
    col2.metric("🟡 Stale (>15min)", counts.get("stale", 0))
    col3.metric("🔴 Stuck", counts.get("stuck", 0))
    col4.metric("⚪ No data (>7j)", counts.get("no_data", 0))


def _status_counts(df: pd.DataFrame) -> dict[str, int]:
    """Compte les capteurs par statut."""
    if df.empty or "status" not in df.columns:
        return {"ok": 0, "stale": 0, "stuck": 0, "no_data": 0}
    return df["status"].value_counts().to_dict()


def _render_status_table(df: pd.DataFrame, top_n: int = 20) -> None:
    """Table des capteurs stuck/stale triés par priorité."""
    if df.empty:
        st.caption("Aucun capteur à afficher.")
        return

    # Priorité : stuck > stale > no_data > ok
    priority = {"stuck": 0, "stale": 1, "no_data": 2, "ok": 3}
    df = df.copy()
    df["__priority"] = df["status"].map(priority).fillna(99)

    cols = [
        "channel_id",
        "status",
        "sat_now_pct",
        "current_speed_kmh",
        "v85_7j",
        "amp_pct",
        "std_24h",
        "vmin_24h",
        "vmax_24h",
        "n_obs_7d",
        "last_24h_at",
    ]
    cols = [c for c in cols if c in df.columns]
    df_top = df.sort_values(["__priority", "sat_now_pct"], ascending=[True, True]).head(top_n)

    st.dataframe(
        df_top[cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "sat_now_pct": st.column_config.ProgressColumn(
                "Saturation %v85",
                help="Vitesse actuelle / v85 sur 7j. < 50% fluide, > 100% congestion",
                min=0,
                max=200,
            ),
            "amp_pct": st.column_config.ProgressColumn(
                "Amplitude 24h %",
                help="(max_24h - min_24h) / v85. < 2% = stuck suspect",
                min=0,
                max=100,
            ),
        },
    )


def _render_summary_text(df: pd.DataFrame) -> None:
    """Bandeau texte d'alerte si capteurs stuck ou stale."""
    counts = _status_counts(df)
    n_stuck = counts.get("stuck", 0)
    n_stale = counts.get("stale", 0)
    n_total = len(df)
    if n_total == 0:
        return
    pct_stuck = (n_stuck / n_total) * 100
    pct_stale = (n_stale / n_total) * 100

    if pct_stuck > 5:
        st.error(
            f"🔴 **{n_stuck} capteurs stuck** ({pct_stuck:.1f}% du réseau) — "
            f"variation < 2% sur 24h (suspect panne). À investiguer."
        )
    elif pct_stale > 10:
        st.warning(
            f"🟡 **{n_stale} capteurs stale** ({pct_stale:.1f}% du réseau) — "
            f"pas de mesure depuis > 15 min. DAG `transform_silver_to_gold` à vérifier."
        )


def render_sensor_saturation() -> None:
    """Affiche le dashboard saturation + amplitude par capteur.

    Fail loud via ``DashboardDataError`` si PostgreSQL indispo ou si
    la migration 034 (matérialisée) n'est pas appliquée.
    """
    st.markdown("##### 📡 Saturation + amplitude par capteur (Sprint 22+)")

    with loading_wrapper("Chargement Sensor saturation…", "📡"):
        try:
            df = cached_sensor_saturation()
        except DashboardDataError as e:
            show_error("db_down", f"⚠️ Saturation indisponible : {e}")
            return

    if df.empty:
        st.info(
            "Aucune donnée de saturation. Vérifier : (1) migration 034 (matérialisée) "
            "appliquée (`scripts/sql/migration_033_sensor_saturation.sql`), "
            "(2) `gold.traffic_features_live` alimentée (DAG `*/10min`), "
            "(3) ≥ 7 jours d'historique pour le calcul v85."
        )
        return

    # Texte d'alerte
    _render_summary_text(df)

    # Bandeau KPIs
    st.markdown("---")
    counts = _status_counts(df)
    _render_kpi_banner(counts, n_total=len(df))

    # Table
    st.markdown("---")
    st.markdown("##### Capteurs par priorité (stuck en premier)")
    _render_status_table(df, top_n=20)

    st.caption(
        "Source : `gold.mv_sensor_saturation` (migration 034 (matérialisée)) — "
        "v85 sur 7j + amplitude 24h + seuil stuck à 2%. "
        "Refresh via vue (cache Streamlit 60s)."
    )
