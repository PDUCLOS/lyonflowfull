"""Widget — Impact météo sur les 3 modes (Axe 7, Sprint 17, 2026-06-20).

Vue matérialisée ``gold.mv_meteo_impact`` (migration 022) qui agrège 30 jours
d'historique pour comparer l'effet de **5 conditions météo** sur les **3
modes de transport** (trafic routier, TCL bus/tram/métro, Vélov) :

| Bande météo     | Critère                                |
|-----------------|----------------------------------------|
| ``fair``        | baseline (beau temps)                  |
| ``light_rain``  | précipitations 1-5 mm/h                |
| ``heavy_rain``  | précipitations > 5 mm/h                |
| ``frost``       | température < 0 °C                     |
| ``heatwave``    | température > 35 °C                    |

Pour chaque bande, on calcule :

* **Trafic** : ``avg_speed_kmh`` + delta vs fair (négatif = congestion).
* **TCL** : ``avg_delay_seconds`` + delta vs fair (positif = plus de retard).
* **Vélov** : ``avg_bikes_available`` + delta vs fair (négatif = moins
  de vélos disponibles, les usagers fuient le vélo).

Affiche :
1. **Bandeau KPI** (3 cards) : effet le plus marquant par mode.
2. **Tableau comparatif** : 5 lignes × 11 colonnes (modes + deltas).
3. **Bar chart Plotly** : visualisation deltas trafic / TCL / Vélov.

Si PostgreSQL indispo → fail loud via ``DashboardDataError``. Si vue vide
(DAG refresh pas encore passé) → message d'attente explicite.

Cf. docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §8 pour la spec complète.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.data_cache import cached_meteo_impact
from dashboard.components.plotly_theme import apply_lyf_theme
from src.data.exceptions import DashboardDataError

# Libellés FR pour les bandes météo (cohérent avec axe 1 multimodal_heatmap)
METEO_BAND_LABELS = {
    "fair": "☀ Beau temps (baseline)",
    "light_rain": "🌦 Pluie légère",
    "heavy_rain": "🌧 Forte pluie",
    "frost": "❄ Gel",
    "heatwave": "🔥 Canicule",
}

# Emojis + couleurs par bande (utilisés dans le bar chart)
METEO_BAND_COLORS = {
    "fair": "#4CAF50",  # vert
    "light_rain": "#FFC107",  # ambre
    "heavy_rain": "#F44336",  # rouge
    "frost": "#2196F3",  # bleu
    "heatwave": "#FF5722",  # orange foncé
}


def _format_delta_traffic(val: float) -> str:
    """Delta vitesse (km/h) — négatif = congestion vs fair."""
    if pd.isna(val):
        return "—"
    # 0 et valeurs positives = pas de congestion vs fair (signe +)
    sign = "−" if val < 0 else "+"
    return f"{sign}{abs(val):.1f} km/h"


def _format_delta_tcl(val: float) -> str:
    """Delta retard TCL (s) — positif = plus de retard."""
    if pd.isna(val):
        return "—"
    # 0 = pas de retard additionnel (signe +), > 0 = plus de retard
    sign = "+" if val >= 0 else "−"
    return f"{sign}{abs(val):.0f} s"


def _format_delta_velov(val: float) -> str:
    """Delta vélos dispos — négatif = moins de vélos."""
    if pd.isna(val):
        return "—"
    # 0 = pas de changement (signe +), > 0 = plus de vélos
    sign = "+" if val >= 0 else "−"
    return f"{sign}{abs(val):.1f} vélos"


def _find_worst_band(df: pd.DataFrame, col: str, mode: str) -> tuple[str | None, float]:
    """Trouve la bande (hors fair) avec le delta le plus impactant.

    Pour le trafic : cherche le delta le plus négatif (plus de congestion).
    Pour TCL/Vélov : cherche le delta le plus extrême dans le sens négatif
    (plus de retard / moins de vélos).
    """
    if df.empty or col not in df.columns:
        return None, float("nan")
    non_fair = df[df["meteo_band"] != "fair"]
    if non_fair.empty:
        return None, float("nan")
    if mode == "traffic":
        # Plus négatif = pire congestion
        worst = non_fair.loc[non_fair[col].idxmin()]
    else:
        # TCL : plus positif = pire retard. Vélov : plus négatif = moins de vélos.
        if mode == "tcl":
            worst = non_fair.loc[non_fair[col].idxmax()]
        else:
            worst = non_fair.loc[non_fair[col].idxmin()]
    return str(worst["meteo_band"]), float(worst[col])


def _render_kpi_banner(df: pd.DataFrame) -> None:
    """3 KPI cards résumant l'effet météo le plus marquant par mode."""
    traffic_band, traffic_delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
    tcl_band, tcl_delta = _find_worst_band(df, "tcl_delay_delta_sec_vs_fair", "tcl")
    velov_band, velov_delta = _find_worst_band(df, "velov_delta_bikes_vs_fair", "velov")

    col1, col2, col3 = st.columns(3)

    with col1:
        if traffic_band:
            label = METEO_BAND_LABELS.get(traffic_band, traffic_band)
            st.metric(
                label="🚗 Trafic : pire condition",
                value=label,
                delta=_format_delta_traffic(traffic_delta),
                delta_color="inverse",  # négatif = pire (rouge)
            )
        else:
            st.metric("🚗 Trafic", "—", "Aucune donnée hors fair")

    with col2:
        if tcl_band:
            label = METEO_BAND_LABELS.get(tcl_band, tcl_band)
            st.metric(
                label="🚌 TCL : pire condition",
                value=label,
                delta=_format_delta_tcl(tcl_delta),
                delta_color="inverse",  # positif = pire (rouge)
            )
        else:
            st.metric("🚌 TCL", "—", "Aucune donnée hors fair")

    with col3:
        if velov_band:
            label = METEO_BAND_LABELS.get(velov_band, velov_band)
            st.metric(
                label="🚲 Vélov : pire condition",
                value=label,
                delta=_format_delta_velov(velov_delta),
                delta_color="inverse",
            )
        else:
            st.metric("🚲 Vélov", "—", "Aucune donnée hors fair")


def _render_comparison_table(df: pd.DataFrame) -> None:
    """Tableau comparatif 5 bandes × 11 colonnes."""
    rows = []
    for _, r in df.iterrows():
        band = str(r["meteo_band"])
        rows.append(
            {
                "Météo": METEO_BAND_LABELS.get(band, band),
                "🚗 Vitesse (km/h)": (f"{float(r['avg_speed_kmh']):.1f}" if pd.notna(r["avg_speed_kmh"]) else "—"),
                "🚗 Δ vs beau": _format_delta_traffic(r.get("traffic_delta_kmh_vs_fair")),
                "🚌 Retard (s)": (f"{float(r['avg_delay_seconds']):.0f}" if pd.notna(r["avg_delay_seconds"]) else "—"),
                "🚌 Δ vs beau": _format_delta_tcl(r.get("tcl_delay_delta_sec_vs_fair")),
                "🚲 Vélos dispo": (
                    f"{float(r['avg_bikes_available']):.1f}" if pd.notna(r["avg_bikes_available"]) else "—"
                ),
                "🚲 Δ vs beau": _format_delta_velov(r.get("velov_delta_bikes_vs_fair")),
                "Obs. trafic": int(r.get("traffic_n_obs", 0) or 0),
                "Obs. TCL": int(r.get("tcl_n_obs", 0) or 0),
                "Obs. Vélov": int(r.get("velov_n_obs", 0) or 0),
            }
        )
    df_disp = pd.DataFrame(rows)
    st.dataframe(df_disp, use_container_width=True, hide_index=True)


def _render_delta_chart(df: pd.DataFrame) -> None:
    """Bar chart Plotly : deltas normalisés par mode (visualisation rapide)."""
    if df.empty:
        return

    # Prépare les données : on exclut 'fair' (baseline = 0 par définition)
    non_fair = df[df["meteo_band"] != "fair"].copy()
    if non_fair.empty:
        return

    non_fair["label"] = non_fair["meteo_band"].map(lambda b: METEO_BAND_LABELS.get(b, b))

    fig = go.Figure()
    # Trafic : delta en km/h, plus négatif = pire
    fig.add_trace(
        go.Bar(
            name="🚗 Trafic (km/h)",
            x=non_fair["label"],
            y=non_fair["traffic_delta_kmh_vs_fair"],
            marker_color="#FF9800",
            hovertemplate="<b>%{x}</b><br>Trafic : %{y:.1f} km/h<extra></extra>",
        )
    )
    # TCL : delta en secondes, plus positif = pire
    fig.add_trace(
        go.Bar(
            name="🚌 TCL retard (s)",
            x=non_fair["label"],
            y=non_fair["tcl_delay_delta_sec_vs_fair"],
            marker_color="#F44336",
            hovertemplate="<b>%{x}</b><br>TCL retard : +%{y:.0f} s<extra></extra>",
        )
    )
    # Vélov : delta vélos, plus négatif = pire
    fig.add_trace(
        go.Bar(
            name="🚲 Vélos dispo",
            x=non_fair["label"],
            y=non_fair["velov_delta_bikes_vs_fair"],
            marker_color="#2196F3",
            hovertemplate="<b>%{x}</b><br>Vélos : %{y:.1f}<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="group",
        title="Impact météo vs beau temps (baseline = 0)",
        xaxis_title="Condition météo",
        yaxis_title="Δ vs fair weather",
        height=400,
        hovermode="x unified",
    )
    apply_lyf_theme(fig)
    st.plotly_chart(fig, use_container_width=True)


def render_meteo_impact() -> None:
    """Affiche l'impact météo sur les 3 modes (Axe 7, Sprint 17).

    Sprint 17 (2026-06-20). Si DB indispo → fail loud via DashboardDataError.
    Si vue matérialisée pas encore alimentée → message d'attente explicite.
    """
    try:
        df = cached_meteo_impact()
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if df.empty:
        st.info(
            "Vue matérialisée `gold.mv_meteo_impact` pas encore alimentée. "
            "Le DAG `refresh_meteo_impact` doit tourner (1×/jour à 04h30). "
            "Causes possibles : (1) DAG en attente de son 1er cycle, "
            "(2) `migration_022_meteo_impact.sql` non appliquée, "
            "(3) moins de 30 jours d'historique météo (Sprint 8+ OK)."
        )
        return

    # Bandeau KPI
    st.markdown("##### Effet météo par mode (30 jours d'historique)")
    _render_kpi_banner(df)

    st.markdown("---")

    # Tableau comparatif + bar chart
    st.markdown("##### Tableau comparatif (5 bandes × 3 modes)")
    _render_comparison_table(df)

    st.markdown("---")
    st.markdown("##### Visualisation rapide (deltas vs beau temps)")
    _render_delta_chart(df)

    st.caption(
        "Données : `silver.meteo_hourly` × `gold.traffic_features_live` "
        "× `gold.tcl_vehicle_realtime` × `silver.velov_clean` agrégées par "
        "bande météo (CASE WHEN sur pluie + température) dans "
        "`gold.mv_meteo_impact` (migration 022). "
        "Refresh quotidien 04h30 par `dags/maintenance/refresh_meteo_impact.py`. "
        "Spec : `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` §8."
    )
