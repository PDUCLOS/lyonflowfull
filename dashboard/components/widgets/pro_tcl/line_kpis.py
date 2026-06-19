"""Widget — KPI cards denses par ligne (OTP, retard, fréquence, charge).

Sprint 8 — binding DB (zéro mock) :
* ``line_ids=None`` → ``data_loader.cached_line_kpis()`` (DB Gold vue matérialisée
  ``gold.mv_line_kpis_live``, fail loud via DashboardDataError si DB indispo).
* Le widget reste rétro-compatible (accepte un dict en arg).

Sprint VPS-5 — Mode explorable :
* Tri par n'importe quelle colonne (OTP, retard, charge, fréquence, line_id)
* Slider "top N" pour ne pas tout afficher d'un coup
* Bouton "Voir toutes les lignes" pour explorer
* Détails dépliables par ligne
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_line_kpis

SORT_OPTIONS = {
    "OTP (%) ↓": ("otp_pct", False),
    "OTP (%) ↑": ("otp_pct", True),
    "Retard min ↓": ("avg_delay_min", False),
    "Retard min ↑": ("avg_delay_min", True),
    "Charge (%) ↓": ("load_pct", False),
    "Charge (%) ↑": ("load_pct", True),
    "Fréquence min ↑": ("frequency_min", True),
    "Fréquence min ↓": ("frequency_min", False),
    "Line ID (A-Z)": ("line_id", True),
    "Line ID (Z-A)": ("line_id", False),
}


def _to_dataframe(kpis_dict: dict) -> pd.DataFrame:
    """Convertit le dict de KPIs en DataFrame pour tri/filtre Streamlit.

    Sprint 11+ (2026-06-17) — utilise ``line_label`` (calculé par
    ``get_line_kpis`` via ``clean_line_label``) pour l'affichage, et garde
    ``line_id`` brut pour le tri A-Z technique si besoin.
    """
    rows = []
    for line_id, kpis in kpis_dict.items():
        if not kpis:
            continue
        rows.append(
            {
                "line_id": line_id,
                "line_label": kpis.get("line_label", line_id),
                "otp_pct": float(kpis.get("otp_pct", 0)),
                "avg_delay_min": float(kpis.get("avg_delay_min", 0)),
                "frequency_min": float(kpis.get("frequency_min", 0)),
                "load_pct": float(kpis.get("load_pct", 0)),
                "trend": kpis.get("trend", "stable"),
                "trend_delta": float(kpis.get("trend_delta", 0)),
            }
        )
    df = pd.DataFrame(rows)
    return df


def render_line_kpis(
    line_ids: list | None = None,
    compact: bool = False,
    kpis_dict: dict | None = None,
) -> None:
    """Affiche les KPI cards denses par ligne.

    Args:
        line_ids: liste de line_id. Si None, toutes les lignes.
        compact: True pour 4 KPIs/ligne en mode compact, False pour layout large.
        kpis_dict: dict pré-calculé. Si None, charge via DB Gold (fail loud).
    """
    if kpis_dict is None:
        kpis_dict = cached_line_kpis()

    if line_ids is None:
        line_ids = list(kpis_dict.keys())

    df = _to_dataframe({lid: kpis_dict.get(lid) for lid in line_ids if kpis_dict.get(lid)})

    if df.empty:
        st.info("Aucun KPI ligne disponible.")
        return

    # ---- Contrôles de tri + exploration (Sprint VPS-5) ----
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 1])
    with ctrl_col1:
        sort_label = st.selectbox(
            "Trier par",
            options=list(SORT_OPTIONS.keys()),
            index=0,
            key="line_kpis_sort",
        )
    with ctrl_col2:
        top_n = st.slider(
            "Top N lignes affichées",
            min_value=5,
            max_value=min(50, len(df)),
            value=min(20, len(df)),
            step=5,
            key="line_kpis_top_n",
        )
    with ctrl_col3:
        show_details = st.checkbox(
            "Détails par ligne",
            value=False,
            key="line_kpis_details",
            help="Déplie chaque ligne pour voir les détails complets",
        )

    # ---- Tri + filtre ----
    col_name, ascending = SORT_OPTIONS[sort_label]
    df_sorted = df.sort_values(col_name, ascending=ascending, na_position="last").reset_index(drop=True)
    df_view = df_sorted.head(top_n)

    # ---- Tableau Streamlit avec sort natif en plus ----
    # Sprint 11+ — afficher le libellé lisible (``L66``) plutôt que le
    # ``line_ref`` brut (``ActIV:Line::66:SYTRAL``).
    display_cols = ["line_label", "otp_pct", "avg_delay_min", "frequency_min", "load_pct", "trend"]
    df_display = df_view[display_cols].rename(
        columns={
            "line_label": "Ligne",
            "otp_pct": "OTP (%)",
            "avg_delay_min": "Retard (min)",
            "frequency_min": "Fréq. (min)",
            "load_pct": "Charge (%)",
            "trend": "Tendance",
        }
    )
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "OTP (%)": st.column_config.ProgressColumn(
                "OTP (%)",
                min_value=0,
                max_value=100,
                format="%.0f",
            ),
            "Charge (%)": st.column_config.ProgressColumn(
                "Charge (%)",
                min_value=0,
                max_value=100,
                format="%.0f",
            ),
        },
    )

    st.caption(f"📊 {len(df)} lignes au total · affichage des {len(df_view)} premières après tri")

    # ---- Mode détails dépliables (optionnel) ----
    if show_details:
        st.markdown("##### 🔍 Détails par ligne")
        for _, row in df_view.iterrows():
            with st.expander(
                f"**{row['line_label']}** — OTP {row['otp_pct']:.0f}% · retard {row['avg_delay_min']:.1f} min"
            ):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("OTP", f"{row['otp_pct']:.1f}%")
                c2.metric("Retard moyen", f"{row['avg_delay_min']:.1f} min")
                c3.metric("Fréquence", f"{row['frequency_min']:.0f} min")
                c4.metric("Charge", f"{row['load_pct']:.0f}%")
                trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(row["trend"], "➡️")
                st.write(f"Tendance : {trend_icon} {row['trend_delta']:+.1f} pts")

    # Sprint 15+ (audit Pro TCL C1) — Suppression du bloc "Vue cartes (legacy)".
    # Le mode compact (param ``compact``, conservé pour rétro-compat) n'est plus
    # utilisé ; tout passe par le tableau Streamlit + mode détails dépliables.
