"""Widget — Corrélation bus × trafic spatialisée (Axe 3, ).

Corrige la lacune du bottleneck actuel (gold.infrastructure_bottlenecks)
qui fait un JOIN bus × trafic par HEURE GLOBALE. Cette version fait un
JOIN SPATIAL : les positions GPS des véhicules TCL sont corrélées au
trafic routier de la MÊME zone (résolution 0.001° ≈ 100 m).

Option B (non-breaking) : coexiste avec ``correlation_matrix.py`` qui
continue de lire ``gold.infrastructure_bottlenecks``. Bascule vers
remplacement (Option A) quand la MV aura fait ses preuves.

Vue matérialisée ``gold.mv_bus_traffic_spatial`` (migration 18).

Affiche :
1. **Bandeau KPI** : compteurs par diagnostic (infra / operations /
   bus_lane_ok / ok)
2. **Scatter plot** : bus_delay_sec (x) vs traffic_speed_kmh (y), colorisé
   par diagnostic, avec seuils visuels (120s delay, 25 km/h speed).
3. **Tableau top zones problématiques** : triées par bus_delay_sec DESC.

Si PostgreSQL indispo → fail loud via DashboardDataError.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.data_cache import (
    cached_bus_traffic_spatial,
    cached_bus_traffic_spatial_diagnosis_counts,
)
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.plotly_theme import apply_lyf_theme
from src.data.db_query import clean_line_label
from src.data.exceptions import DashboardDataError
from src.data.labels import DIAGNOSIS_LABELS

SPATIAL_DIAGNOSIS_COLORS = {
    "ok": "#4CAF50",
    "infra": "#F44336",
    "operations": "#FF9800",
    "bus_lane_ok": "#2196F3",
}

DELAY_THRESHOLD = 120
SPEED_THRESHOLD = 25


def _diagnosis_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = dict.fromkeys(SPATIAL_DIAGNOSIS_COLORS, 0)
    if df.empty or "diagnosis" not in df.columns:
        return counts
    for d, n in df["diagnosis"].value_counts().items():
        if d in counts:
            counts[d] = int(n)
    return counts


def _render_kpi_banner(counts: dict[str, int], n_total: int) -> None:
    cards = [
        (
            "Infrastructure",
            counts.get("infra", 0),
            SPATIAL_DIAGNOSIS_COLORS["infra"],
            "Bus ET trafic souffrent (même zone)",
        ),
        (
            "Exploitation",
            counts.get("operations", 0),
            SPATIAL_DIAGNOSIS_COLORS["operations"],
            "Bus retard, trafic fluide",
        ),
        (
            "Voie bus OK",
            counts.get("bus_lane_ok", 0),
            SPATIAL_DIAGNOSIS_COLORS["bus_lane_ok"],
            "Trafic congestionné, bus OK",
        ),
        ("OK", counts.get("ok", 0), SPATIAL_DIAGNOSIS_COLORS["ok"], f"Sur {n_total} zones analysées"),
    ]
    cols = st.columns(4)
    for col, (label, n, color, sub) in zip(cols, cards):
        with col:
            pct = (n / max(n_total, 1)) * 100
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                    <div class="lyf-detail" style="opacity:0.8;">{label}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.2rem 0;">
                        {n} <span style="font-size:0.8rem;font-weight:400;">
                        zones</span>
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.6;">
                        {pct:.0f}% · {sub}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_scatter(df: pd.DataFrame) -> None:
    """Scatter plot bus_delay_sec (x) vs traffic_speed_kmh (y)."""
    if df.empty:
        st.info("Pas de données pour le scatter plot.")
        return

    import plotly.express as px

    plot_df = df.copy()
    plot_df["diagnosis_label"] = plot_df["diagnosis"].map(lambda d: DIAGNOSIS_LABELS.get(d, d))
    plot_df["line_label"] = plot_df["line_ref"].apply(clean_line_label)

    fig = px.scatter(
        plot_df,
        x="bus_delay_sec",
        y="traffic_speed_kmh",
        color="diagnosis",
        color_discrete_map=SPATIAL_DIAGNOSIS_COLORS,
        hover_data=["line_label", "hour", "bus_observations"],
        labels={
            "bus_delay_sec": "Retard bus moyen (s)",
            "traffic_speed_kmh": "Vitesse trafic (km/h)",
            "diagnosis": "Diagnostic",
        },
        height=400,
    )
    fig.add_hline(
        y=SPEED_THRESHOLD,
        line_dash="dash",
        line_color="#999",
        annotation_text=f"Seuil trafic ({SPEED_THRESHOLD} km/h)",
        annotation_position="top right",
    )
    fig.add_vline(
        x=DELAY_THRESHOLD,
        line_dash="dash",
        line_color="#999",
        annotation_text=f"Seuil retard ({DELAY_THRESHOLD}s)",
        annotation_position="top right",
    )
    fig.update_layout(
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    apply_lyf_theme(fig)
    plotly_with_alt(fig, use_container_width=True)


def _render_top_zones(df: pd.DataFrame, top_n: int = 20) -> None:
    """Tableau top N zones problématiques."""
    if df.empty:
        st.info("Aucune zone à analyser.")
        return

    problem_df = df[df["diagnosis"].isin(["infra", "operations"])].copy()
    if problem_df.empty:
        st.info("Aucune zone problématique détectée (bus à l'heure partout).")
        return

    problem_df = problem_df.nlargest(top_n, "bus_delay_sec")
    rows = []
    for _, r in problem_df.iterrows():
        rows.append(
            {
                "Ligne": clean_line_label(r.get("line_ref", "?")),
                "Heure": f"{int(r.get('hour', 0))}h",
                "Retard (s)": float(r.get("bus_delay_sec", 0)),
                "Vitesse trafic": float(r.get("traffic_speed_kmh", 0)),
                "Diagnostic": DIAGNOSIS_LABELS.get(r.get("diagnosis", "ok"), "—"),
                "Obs. bus": int(r.get("bus_observations", 0)),
                "Capteurs": int(r.get("traffic_sensors", 0)),
                "Lat": float(r.get("lat", 0)),
                "Lon": float(r.get("lon", 0)),
            }
        )
    df_disp = pd.DataFrame(rows)
    df_disp = df_disp.round({"Retard (s)": 0, "Vitesse trafic": 1})

    def _color_diag(val: str) -> str:
        for key, label in DIAGNOSIS_LABELS.items():
            if val == label:
                color = SPATIAL_DIAGNOSIS_COLORS.get(key, "#9E9E9E")
                return f"background-color: {color}; color: white; font-weight: 600;"
        return ""

    st.dataframe(
        df_disp.style.map(_color_diag, subset=["Diagnostic"]),
        use_container_width=True,
        hide_index=True,
    )


def render_bus_traffic_spatial(
    line_id: str | None = None,
) -> None:
    with loading_wrapper("Chargement Bus traffic spatial…", "⏳"):
        """Affiche la corrélation bus × trafic spatialisée (Axe 3).

  (2026-06-19). Widget parallèle (Option B) — non-breaking.
    """
    try:
        df = cached_bus_traffic_spatial(line_ref=line_id)
        diag_df = cached_bus_traffic_spatial_diagnosis_counts(line_ref=line_id)
    except DashboardDataError as e:
        show_error("db_down", str(e))
        return

    if df.empty or diag_df.empty:
        st.info(
            "Corrélation spatialisée pas encore alimentée. "
            "Vérifier : (1) `migration_018_bus_traffic_spatial.sql` "
            "appliquée, (2) DAG refresh `*/15 min` a tourné, "
            "(3) données TCL + trafic présentes sur 7 jours."
        )
        return

    counts = _diagnosis_counts(diag_df)
    n_total = sum(counts.values())
    _render_kpi_banner(counts, n_total)

    st.markdown("---")

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("##### Scatter : retard bus × vitesse trafic (par zone)")
        _render_scatter(df)
    with col2:
        st.markdown("##### Top zones problématiques")
        _render_top_zones(df, top_n=20)

    st.caption(
        "Données : `gold.tcl_vehicle_realtime` × `gold.traffic_features_live` "
        "agrégées par zone 0.001° (~100 m) × heure dans "
        "`gold.mv_bus_traffic_spatial` (migration 18). "
        "Refresh DAG `transform_silver_to_gold` toutes les 15 min. "
        "JOIN spatial : le retard bus est corrélé au trafic de la MÊME zone, "
        "pas au trafic global Lyon."
    )
