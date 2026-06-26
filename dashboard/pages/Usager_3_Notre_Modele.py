"""Page Usager — Notre modèle (transparence sur la prédiction).

 Ajout du menu MLOps pour le persona Usager (citizen-friendly).
3 pages au total : Notre modèle / Sources de données / Statut du service.

Cette page explique en langage simple comment LyonFlow prédit le
trafic et expose la précision réelle des 7 derniers jours (calculée
par le backtest engine vs données live). Aucun jargon ML.
"""

from __future__ import annotations

import logging

import plotly.graph_objects as go
import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.colors import COLORS, STATUS_COLORS
from dashboard.components.data_cache import (
    cached_predictions_vs_actuals,
    cached_xgb_accuracy_summary,
)
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.plotly_theme import apply_lyf_theme
from dashboard.components.theme import inject_theme

logger = logging.getLogger(__name__)


# Mapping code interne -> libellé citoyen + icône
_MODEL_BLURB = {
    "intro": (
        "🤖 **Comment on prédit le trafic à 1 heure ?**\n\n"
        "Notre modèle apprend en continu à partir de :\n"
        "- 🚗 **Boucles de comptage** Grand Lyon (~1 200 capteurs sur la voirie)\n"
        "- 🕐 **L'heure, le jour**, les vacances scolaires et jours fériés\n"
        "- 🌦️ **La météo** (température, pluie)\n"
        "- 📈 **Les vitesses des dernières heures** (tendances récentes)\n\n"
        "Toutes les 30 min, il met à jour sa prédiction pour l'heure suivante. "
        "C'est ce qui te permet de voir un temps de trajet ajusté dans "
        "**Mon trajet** au lieu d'une simple moyenne."
    ),
    "scope": (
        "🎯 **Ce que le modèle fait bien** : anticiper la tendance générale "
        "(ça va se charger ou ça va se fluidifier) sur les 60 prochaines minutes.\n\n"
        "⚠️ **Ce qu'il ne peut pas deviner** : un accident, une manifestation, "
        "une route coupée. Dans ces cas, la prédiction reste sur la tendance "
        "habituelle — les alertes temps réel de la page **🔔 Alertes** "
        "viennent compléter."
    ),
}


def _humanize_pct(pct: float | None) -> str:
    """Formate un ratio 0-1 en % lisible. None -> '—'."""
    if pct is None:
        return "—"
    return f"{pct * 100:.0f} %"


def _accuracy_pie(accurate: int, acceptable: int, poor: int) -> go.Figure:
    """Donut accuracy_band sur les 7 derniers jours.

    Bands :
    - accurate  : erreur < 5 km/h (vert)
    - acceptable : erreur 5-10 km/h (orange)
    - poor      : erreur > 10 km/h (rouge)
    """
    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Très précises (±5 km/h)", "Approximatives (5-10 km/h)", "Imprécises (>10 km/h)"],
                values=[accurate, acceptable, poor],
                hole=0.55,
                marker={
                    "colors": [
                        COLORS["status_ok"],
                        COLORS["status_warning"],
                        COLORS["status_critical"],
                    ]
                },
                textinfo="percent",
                textfont={"size": 13, "color": COLORS["text_primary"]},
                hovertemplate="<b>%{label}</b><br>%{value} prédictions (%{percent})<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title={"text": "Précision sur 7 jours", "font": {"size": 15}, "x": 0.5},
        showlegend=True,
        legend={"orientation": "v", "yanchor": "middle", "y": 0.5, "xanchor": "left", "x": 1.02},
        height=320,
        margin={"t": 50, "b": 20, "l": 20, "r": 20},
    )
    return apply_lyf_theme(fig)


def _mae_trend(mae_df) -> go.Figure:
    """Courbe MAE km/h sur les 7 derniers jours (par bucket horaire)."""
    if mae_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Pas encore assez de données (≥ 48h de production requises)",
            showarrow=False,
            font={"color": COLORS["text_muted"], "size": 13},
        )
        fig.update_layout(height=280)
        return apply_lyf_theme(fig)

    df_sorted = mae_df.sort_values("hour_bucket")
    fig = go.Figure(
        data=[
            go.Scatter(
                x=df_sorted["hour_bucket"],
                y=df_sorted["mae_kmh"],
                mode="lines+markers",
                line={"color": COLORS["persona_usager"], "width": 2.5},
                marker={"size": 5},
                name="MAE",
                hovertemplate="<b>%{x|%a %d %Hh}</b><br>Erreur moyenne : %{y:.1f} km/h<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title={"text": "Erreur moyenne de prédiction (km/h)", "font": {"size": 15}, "x": 0.5},
        xaxis_title="Heure",
        yaxis_title="km/h",
        height=300,
        margin={"t": 50, "b": 40, "l": 40, "r": 20},
    )
    return apply_lyf_theme(fig)


def _quality_card(score_accurate_pct: float | None, mae_kmh: float | None) -> tuple[str, str, str]:
    """Retourne (label, emoji, couleur) selon la précision globale.

    Heuristique citoyen :
    - >= 75% accurate ET mae <= 5  : "Très fiable"
    - >= 60% accurate ET mae <= 8  : "Fiable"
    - sinon : "Prudence sur les détails"
    """
    if score_accurate_pct is None or mae_kmh is None:
        return ("Pas encore de données", "⏳", COLORS["text_muted"])
    if score_accurate_pct >= 0.75 and mae_kmh <= 5.0:
        return ("Très fiable", "🟢", COLORS["status_ok"])
    if score_accurate_pct >= 0.60 and mae_kmh <= 8.0:
        return ("Fiable", "🟡", COLORS["status_warning"])
    return ("Prudence sur les détails", "🟠", COLORS["status_warning"])


# =============================================================================
# Page
# =============================================================================
st.set_page_config(
    page_title="Notre modèle — LyonFlow",
    page_icon="🤖",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("🤖 Notre modèle")
render_data_status_banner()

st.caption(
    "Transparence sur la prédiction : comment ça marche, et quelle est "
    "sa précision réelle sur les 7 derniers jours."
)

# ── 1. Bloc pédagogique ─────────────────────────────────────────────────────
with st.container():
    st.markdown(_MODEL_BLURB["intro"])
    with st.expander("👍 Voir ce que le modèle sait bien faire (et moins bien)", expanded=False):
        st.markdown(_MODEL_BLURB["scope"])

st.markdown("---")

# ── 2. Précision réelle 7 derniers jours ────────────────────────────────────
st.markdown("##### 🎯 Précision sur les 7 derniers jours")

with loading_wrapper("Chargement de la précision…", "🎯"):
    mae_df = cached_xgb_accuracy_summary(hours=168)
    pv_df = cached_predictions_vs_actuals(limit=200)

if mae_df.empty:
    st.info(
        "🌱 Pas encore 7 jours d'historique de production (le modèle a été "
        "mis en service récemment). Les chiffres apparaîtront au bout de "
        "quelques jours."
    )
else:
    # Agrégat global 7j : somme des 3 bands
    n_accurate = int(mae_df["n_accurate"].sum())
    n_acceptable = int(mae_df["n_acceptable"].sum())
    n_poor = int(mae_df["n_poor"].sum())
    n_total = n_accurate + n_acceptable + n_poor

    pct_accurate = n_accurate / n_total if n_total else None
    pct_acceptable = n_acceptable / n_total if n_total else None
    pct_poor = n_poor / n_total if n_total else None

    mae_global = float(mae_df["mae_kmh"].mean())
    p90_global = float(mae_df["p90_error_kmh"].mean())

    quality_label, quality_emoji, quality_color = _quality_card(pct_accurate, mae_global)

    # Bandeau qualité globale (citizen-first)
    st.markdown(
        f"""
        <div class="lyonflow-card" style="text-align:center;padding:1.5rem;
             border-left: 4px solid {quality_color};">
            <div style="font-size:1.1rem;opacity:0.8;">Qualité globale du modèle</div>
            <div style="font-size:2.2rem;font-weight:700;margin-top:0.3rem;
                 color:{quality_color};">
                {quality_emoji} {quality_label}
            </div>
            <div style="font-size:0.9rem;opacity:0.7;margin-top:0.5rem;">
                Sur {n_total:,} prédictions évaluées — marge d'erreur moyenne {mae_global:.1f} km/h
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    # 4 KPI cards simples
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "🎯 Précises (±5 km/h)",
        _humanize_pct(pct_accurate),
        help="Prédictions dont l'erreur absolue est inférieure à 5 km/h.",
    )
    k2.metric(
        "🟡 Approximatives",
        _humanize_pct(pct_acceptable),
        help="Prédictions dont l'erreur est entre 5 et 10 km/h.",
    )
    k3.metric(
        "🟠 Imprécises (>10 km/h)",
        _humanize_pct(pct_poor),
        help="Prédictions dont l'erreur dépasse 10 km/h (souvent incident exceptionnel).",
    )
    k4.metric(
        "📏 Erreur moyenne",
        f"{mae_global:.1f} km/h",
        help="Moyenne de l'erreur absolue sur 7 jours. Plus c'est bas, plus c'est précis.",
    )

    st.write("")

    # Pie + tendance côte à côte
    col_pie, col_trend = st.columns([1, 1])
    with col_pie:
        st.plotly_chart(
            _accuracy_pie(n_accurate, n_acceptable, n_poor),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with col_trend:
        st.plotly_chart(
            _mae_trend(mae_df),
            use_container_width=True,
            config={"displayModeBar": False},
        )

st.markdown("---")

# ── 3. Limites assumées ──────────────────────────────────────────────────────
with st.container():
    st.markdown("##### 🧭 Ce qu'il faut garder en tête")
    st.markdown(
        """
- ⏱️ **Horizon 1 heure** : on prédit l'état du trafic dans 60 minutes,
  pas dans 3 heures. Au-delà, la précision baisse naturellement.
- 🌧️ **Météo extrême** : les fortes pluies ou le brouillard dense peuvent
  dégrader la précision (le modèle connaît la pluie, mais l'ampleur du
  trafic qui en résulte varie).
- 🚧 **Événements imprévus** : accident, manifestation, route coupée —
  le modèle suit la tendance habituelle. C'est pour ça que la page
  **🔔 Alertes** existe : elle te prévient en cas d'incident détecté.
- 📍 **Précision géographique** : les grands axes (périphérique, quais)
  sont très bien couverts. Les petites rues peuvent avoir plus de variance.
        """,
    )

st.caption(
    "LyonFlow · Modèle XGBoost H+1h, ré-entraîné quotidiennement · "
    "Évaluation = comparaison prédiction vs vitesse réelle observée sur 7 jours"
)

# Évite le warning pylint sur STATUS_COLORS (utilisé pour la cohérence
# avec les autres pages du persona, même si pas employé ici).
_ = STATUS_COLORS
