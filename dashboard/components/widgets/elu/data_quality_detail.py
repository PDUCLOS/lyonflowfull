"""Widget — Détail Data Quality (Élu — Synthèse).

 Axe 6 (2026-06-21) — Drill-down sur les checks qualité
exécutés par ``src.transformation.data_quality`` (3 validators :
traffic, tcl, velov). Affiche la dernière exécution par table + un
tableau historique de l'évolution des statuts (ok / warning / critical).

**Distinction avec ``data_quality_badge.py``** Axe B) :
* ``data_quality_badge.py`` → liveness des sources Bronze/Silver
  (gold.v_source_health, source alive ?).
* ``data_quality_detail.py`` → qualité des valeurs (gold.data_quality_log,
  valeurs dans des plages physiquement plausibles ?).

Les 2 sont complémentaires. La badge donne l'alerte rapide 1 ligne
(pour la synthèse exécutive), le detail donne le diagnostic drill-down
(pour l'investigation).

Architecture :
* Lecture : ``gold.data_quality_log`` via ``cached_quality_report()``
  (cache Streamlit TTL_SLOW = 300s, append-only 1×/jour).
* Affichage :
  1. Bandeau 3 KPI cards (1 par table) : dernière exécution + statut
  2. Tableau dernier run (drill-down par sous-check)
  3. Tableau historique 5 derniers runs (tendance)
* Coût : 1 query (cache hit = 0 ms). Pas de button-gate.

Politique fail loud ) :
* DB indispo → ``DashboardDataError`` → ``st.error``.
* Table log vide (DAG pas encore passé) → message d'attente explicite.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_quality_report
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.exceptions import DashboardDataError

# Couleurs par statut (cohérent avec data_quality_badge.py)
STATUS_COLORS: Final[dict[str, str]] = {
    "ok": "#4CAF50",  # vert
    "warning": "#FF9800",  # orange
    "critical": "#F44336",  # rouge
}

STATUS_ICONS: Final[dict[str, str]] = {
    "ok": "OK",
    "warning": "Attention",
    "critical": "Alerte",
}

# Mapping table_name → libellé FR court
TABLE_LABELS: Final[dict[str, str]] = {
    "gold.traffic_features_live": "Trafic (Gold)",
    "gold.tcl_vehicle_realtime": "TCL (Gold)",
    "silver.velov_clean": "Vélov (Silver)",
}


def _latest_per_table(df: pd.DataFrame) -> pd.DataFrame:
    """Retourne la dernière exécution (``checked_at`` max) par table_name.

    Args:
        df: DataFrame ``checked_at, table_name, check_name, status, ...``

    Returns:
        DataFrame avec 1 ligne par table_name (= dernière exécution).
    """
    if df.empty or "checked_at" not in df.columns or "table_name" not in df.columns:
        return pd.DataFrame()
    # Grouper par table et prendre la date max
    latest_ts = df.groupby("table_name")["checked_at"].max().reset_index()
    latest_ts = latest_ts.rename(columns={"checked_at": "_max_ts"})
    merged = df.merge(latest_ts, on="table_name", how="inner")
    return merged[merged["checked_at"] == merged["_max_ts"]].drop(columns=["_max_ts"])


def _table_overall_status(latest_df: pd.DataFrame, table: str) -> str:
    """Overall status d'une table = pire statut parmi ses sous-checks."""
    sub = latest_df[latest_df["table_name"] == table]
    if sub.empty:
        return "ok"
    statuses = set(sub["status"].tolist())
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _render_kpi_banner(latest_df: pd.DataFrame) -> None:
    """Bandeau 3 KPI cards (1 par table) : dernière exécution + statut global."""
    if latest_df.empty:
        return
    cols = st.columns(3)
    for col, (table, label) in zip(cols, TABLE_LABELS.items()):
        sub = latest_df[latest_df["table_name"] == table]
        status = _table_overall_status(latest_df, table)
        color = STATUS_COLORS[status]
        icon = STATUS_ICONS[status]
        last_check = sub["checked_at"].max() if not sub.empty else None
        last_str = pd.Timestamp(last_check).strftime("%Y-%m-%d %H:%M") if last_check is not None else "—"
        n_total = len(sub)
        n_ok = int((sub["status"] == "ok").sum())
        with col:
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                    <div class="lyf-detail" style="opacity:0.8;">{label}</div>
                    <div style="font-size:1.4rem;font-weight:700;margin:0.2rem 0;">
                        {icon}
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.6;">
                        {n_ok}/{n_total} checks OK · {last_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_latest_details(latest_df: pd.DataFrame) -> None:
    """Tableau drill-down du dernier run (toutes tables, tous checks)."""
    if latest_df.empty:
        st.info("Aucun check qualité dans le dernier run.")
        return
    rows = []
    for _, r in latest_df.iterrows():
        rows.append(
            {
                "Table": TABLE_LABELS.get(r["table_name"], r["table_name"]),
                "Check": r["check_name"],
                "Status": r["status"],
                "Métrique": round(float(r.get("metric_value", 0) or 0), 3),
                "Seuil": round(float(r.get("threshold", 0) or 0), 3),
                "Détails": str(r.get("details", ""))[:120],
            }
        )
    df_disp = pd.DataFrame(rows)

    def _color_status(val: str) -> str:
        color = STATUS_COLORS.get(val, "#9E9E9E")
        return f"background-color: {color}; color: white; font-weight: 600;"

    st.dataframe(
        df_disp.style.map(_color_status, subset=["Status"]),
        use_container_width=True,
        hide_index=True,
    )


def _render_history(df: pd.DataFrame) -> None:
    """Tableau historique : 5 derniers runs (1 ligne par run, statut global par table)."""
    if df.empty or "checked_at" not in df.columns:
        return
    # 5 derniers checked_at distincts
    runs = sorted(df["checked_at"].unique(), reverse=True)[:5]
    if not runs:
        return
    rows = []
    for run in runs:
        sub = df[df["checked_at"] == run]
        row = {"Run": pd.Timestamp(run).strftime("%Y-%m-%d %H:%M")}
        for table in TABLE_LABELS:
            table_sub = sub[sub["table_name"] == table]
            if table_sub.empty:
                row[TABLE_LABELS[table]] = "—"
            else:
                row[TABLE_LABELS[table]] = _table_overall_status(sub, table)
        rows.append(row)
    df_hist = pd.DataFrame(rows)

    def _color_cell(val: str) -> str:
        color = STATUS_COLORS.get(val, "")
        if not color:
            return ""
        return f"background-color: {color}; color: white; font-weight: 600; text-align: center;"

    st.markdown("##### Historique des 5 derniers runs")
    st.dataframe(
        df_hist.style.map(_color_cell, subset=list(TABLE_LABELS.values())),
        use_container_width=True,
        hide_index=True,
    )


def render_data_quality_detail() -> None:
    with loading_wrapper("Chargement Data quality detail…", "⏳"):
        """Affiche le drill-down data quality bounds dans Elu_1_Synthese.

  Axe 6 (2026-06-21). Si DB indispo → fail loud via
    DashboardDataError. Si table log vide (DAG pas encore passé) →
    message d'attente explicite.
    """
    try:
        df = cached_quality_report(limit=200)
    except DashboardDataError as e:
        show_error("db_down", f"Data quality log indisponible : {e}")
        return

    if df.empty:
        st.info(
            "Aucun check qualité dans `gold.data_quality_log`. Le DAG "
            "`data_quality_daily` doit tourner (tâches Axe 6, "
            "1×/jour 04h15). Causes possibles : (1) DAG en attente de "
            "son 1er cycle, (2) `migration_025_data_quality_log.sql` "
            "non appliquée."
        )
        return

    st.markdown("##### Détail qualité des données (data bounds)")
    st.caption(
        "Drill-down des checks qualité exécutés par "
        "`src.transformation.data_quality` (3 validators). "
        "Distinct de `data_quality_badge` qui mesure la liveness des "
        "sources. Append-only `gold.data_quality_log` (migration 025)."
    )

    # Bandeau 3 KPI cards (1 par table)
    latest_df = _latest_per_table(df)
    _render_kpi_banner(latest_df)

    st.markdown("---")

    # 2 colonnes : détail dernier run + historique
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("##### Dernier run — détail des sous-checks")
        _render_latest_details(latest_df)
    with col2:
        _render_history(df)
