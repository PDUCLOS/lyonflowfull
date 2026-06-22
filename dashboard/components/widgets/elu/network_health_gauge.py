"""Widget Élu — Jauge "santé réseau" 0-100 (Axe 5, Sprint 15+).

Affiche un KPI de synthèse exécutive basé sur ``gold.fn_network_health_score()``
(migration 019). Le score combine trafic routier + TCL temps réel + Vélov +
météo avec redistribution des poids si une source est indisponible.

Composants :
    * Jauge principale Plotly (mode='gauge+number+delta') — score 0-100 coloré
    * 4 sous-jauges (trafic, TCL, vélov, météo) — montrent les composantes
    * Bannière diagnostic (healthy / stressed / degraded / critical)
    * Sparkline 24h : TODO Sprint suivant (nécessite table d'historique)

V1 (Sprint 15+) : pas de sparkline. La fonction SQL est stateless, donc
l'historique serait à snapshoter via un DAG périodique (15 min) dans une
table ``gold.network_health_history``. Estimation : 0.5 jour additionnel.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_network_health_score
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.plotly_theme import apply_lyf_theme
from src.data.exceptions import DashboardDataError

_DIAGNOSIS_COLORS = {
    "healthy": COLORS["status_ok"],
    "stressed": COLORS["status_warning"],
    "degraded": "#FF8C00",  # dark orange, distinct from warning yellow
    "critical": COLORS["status_critical"],
}

_DIAGNOSIS_LABELS = {
    "healthy": "🟢 Réseau fluide",
    "stressed": "🟡 Réseau sous tension",
    "degraded": "🟠 Réseau dégradé",
    "critical": "🔴 Réseau critique",
}


def _render_main_gauge(score: float, diagnosis: str) -> None:
    """Jauge Plotly principale — score 0-100 coloré par palier."""
    color = _DIAGNOSIS_COLORS.get(diagnosis, COLORS["text_muted"])
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100", "font": {"size": 48}},
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Score santé réseau", "font": {"size": 18}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": color, "thickness": 0.4},
                "bgcolor": "white",
                "steps": [
                    {"range": [0, 25], "color": "#FEE2E2"},  # critical red tint
                    {"range": [25, 50], "color": "#FFEDD5"},  # degraded orange tint
                    {"range": [50, 75], "color": "#FEF3C7"},  # stressed yellow tint
                    {"range": [75, 100], "color": "#DCFCE7"},  # healthy green tint
                ],
                "threshold": {
                    "threshold": 75,
                    "line": {"color": COLORS["status_ok"], "width": 3},
                    "value": score,
                },
            },
        )
    )
    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    apply_lyf_theme(fig)
    plotly_with_alt(fig, use_container_width=True)


def _render_subgauges(
    pct_congestion: float,
    pct_tcl_delayed: float,
    pct_velov_empty: float,
    meteo_penalty: float,
    traffic_avail: bool,
    tcl_avail: bool,
    velov_avail: bool,
    meteo_avail: bool,
) -> None:
    """4 sous-jauges — 1 par composante. Couleur rouge si élevé."""
    cols = st.columns(4)

    subgauges = [
        (
            "Trafic routier",
            f"{pct_congestion:.1f}% congestion",
            pct_congestion if traffic_avail else 0,
            traffic_avail,
            100,
        ),
        (
            "TCL en retard",
            f"{pct_tcl_delayed:.1f}% véhicules retard",
            pct_tcl_delayed if tcl_avail else 0,
            tcl_avail,
            100,
        ),
        (
            "Vélov vides",
            f"{pct_velov_empty:.1f}% stations vides",
            pct_velov_empty if velov_avail else 0,
            velov_avail,
            100,
        ),
        (
            "Météo",
            f"Pénalité {meteo_penalty:.1f} pts",
            meteo_penalty if meteo_avail else 0,
            meteo_avail,
            15,
        ),
    ]

    for col, (label, sublabel, raw_value, available, max_value) in zip(cols, subgauges):
        with col:
            if available:
                if label == "Météo":
                    # Météo : pénalité 0-15, vert=0, orange=8, rouge=15
                    color = (
                        COLORS["status_ok"]
                        if raw_value < 5
                        else COLORS["status_warning"]
                        if raw_value < 12
                        else COLORS["status_critical"]
                    )
                else:
                    # Autres : 0-100%, vert < 25, orange < 50, rouge >= 50
                    color = (
                        COLORS["status_ok"]
                        if raw_value < 25
                        else COLORS["status_warning"]
                        if raw_value < 50
                        else COLORS["status_critical"]
                    )
                bar_color = color
            else:
                color = COLORS["text_muted"]
                bar_color = COLORS["text_muted"]

            fig = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=raw_value if available else 0,
                    number={"font": {"size": 32, "color": color}},
                    domain={"x": [0, 1], "y": [0, 1]},
                    gauge={
                        "axis": {"range": [0, max_value]},
                        "bar": {"color": bar_color, "thickness": 0.3},
                        "bgcolor": "white",
                        "steps": [
                            {"range": [0, max_value], "color": "#F3F4F6"},
                        ],
                    },
                )
            )
            fig.update_layout(
                height=180,
                margin=dict(l=10, r=10, t=30, b=30),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                title={"text": label, "font": {"size": 13}},
            )
            apply_lyf_theme(fig)
            plotly_with_alt(fig, use_container_width=True)
            st.caption(sublabel)
            if not available:
                st.caption("⚠️ Source indisponible (poids redistribué)")


def render_network_health_gauge() -> None:
    with loading_wrapper("Chargement Network health gauge…", "⏳"):
        """Bandeau KPI santé réseau — page Élu Synthèse (Axe 5, Sprint 15+).

    Fail loud via DashboardDataError si DB indispo OU fonction SQL
    migration 019 non appliquée. Le widget affiche alors ``st.error``.
    """
    st.markdown("##### 💚 Santé du réseau — temps réel")

    try:
        df = cached_network_health_score()
    except DashboardDataError as e:
        show_error("db_down", f"⚠️ Score santé réseau indisponible : {e}")
        return

    if df.empty:
        st.error(
            "⚠️ ``gold.fn_network_health_score()`` ne retourne aucune ligne. "
            "Vérifier que la migration 019 est appliquée."
        )
        return

    row = df.iloc[0]
    score = float(row["score"])
    pct_congestion = float(row["pct_congestion"])
    pct_tcl_delayed = float(row["pct_tcl_delayed"])
    pct_velov_empty = float(row["pct_velov_empty"])
    meteo_penalty = float(row["meteo_penalty"])
    traffic_avail = bool(row["traffic_available"])
    tcl_avail = bool(row["tcl_available"])
    velov_avail = bool(row["velov_available"])
    meteo_avail = bool(row["meteo_available"])
    diagnosis = str(row["diagnosis"])
    computed_at = row["computed_at"]

    # Bannière diagnostic (au-dessus des jauges)
    st.markdown(f"**{_DIAGNOSIS_LABELS.get(diagnosis, diagnosis)}** · Dernier calcul : {computed_at}")

    # Layout : jauge principale + 4 sous-jauges côte à côte
    col_main, col_subs = st.columns([1, 2])
    with col_main:
        _render_main_gauge(score, diagnosis)
    with col_subs:
        _render_subgauges(
            pct_congestion=pct_congestion,
            pct_tcl_delayed=pct_tcl_delayed,
            pct_velov_empty=pct_velov_empty,
            meteo_penalty=meteo_penalty,
            traffic_avail=traffic_avail,
            tcl_avail=tcl_avail,
            velov_avail=velov_avail,
            meteo_avail=meteo_avail,
        )

    # Sources indisponibles : avertissement explicite
    unavailable = []
    if not traffic_avail:
        unavailable.append("Trafic routier")
    if not tcl_avail:
        unavailable.append("TCL")
    if not velov_avail:
        unavailable.append("Vélov")
    if not meteo_avail:
        unavailable.append("Météo")
    if unavailable:
        st.info(
            f"ℹ️ Sources temporairement indisponibles ({', '.join(unavailable)}) "
            f"— leurs poids ont été redistribués sur les autres composantes."
        )

    # Sprint 21 P4.3 : sparkline 24h via gold.network_health_history.
    # Lit les 96 derniers snapshots (24h × 4/h) et affiche une mini-tendance.
    # Si la table est vide (< 24h de données après déploiement du DAG), la
    # sparkline affiche "Historique bientôt disponible".
    from dashboard.components.sparkline import render_sparkline
    from src.data.db_query import get_network_health_history

    history = get_network_health_history(hours=24)
    if history:
        timestamps = [row["recorded_at"] for row in history]
        scores = [float(row["score"]) for row in history]
        fig = render_sparkline(values=scores, timestamps=timestamps, height=80)
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        st.caption(
            "📈 Sparkline 24h — l'historique s'affichera après 24h de collecte "
            "(DAG `record_network_health` */15 min, table `gold.network_health_history`)."
        )
