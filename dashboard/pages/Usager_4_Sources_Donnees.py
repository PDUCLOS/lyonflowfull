"""Page Usager — Sources de données (transparence sur les données utilisées).

 Ajout du menu MLOps Usager. Cette page montre en langage
simple d'où viennent les données qui alimentent le modèle : fréquence de
mise à jour, fraîcheur en minutes, score de santé 0-100. Aucun terme
technique (DAG, Bronze, Silver, Gold) — uniquement la signification
citoyenne de chaque source.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.colors import COLORS, STATUS_COLORS
from dashboard.components.data_cache import cached_source_health
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme

logger = logging.getLogger(__name__)


# =============================================================================
# Mapping source (clé SQL) → libellé citoyen + emoji + description
# =============================================================================
# Les libellés sont choisis pour rester parlants à un·e Lyonnais·e qui ne
# connaît ni SQL ni MLOps : on dit QUI fournit la donnée et À QUOI elle
# sert dans la prédiction.
_SOURCE_BLURB: dict[str, dict[str, str]] = {
    "bronze.trafic_boucles": {
        "label": "Boucles de comptage routières",
        "icon": "🚗",
        "who": "Métropole de Lyon (capteurs physiques au sol)",
        "use": "Vitesse et débit des voitures en temps réel",
        "freq": "Toutes les 5 min",
    },
    "bronze.velov": {
        "label": "Stations Vélo'v",
        "icon": "🚴",
        "who": "JCDecaux (opérateur Vélo'v)",
        "use": "Disponibilité des vélos et bornes en temps réel",
        "freq": "Toutes les 5 min",
    },
    "bronze.tcl_vehicles": {
        "label": "Bus, tramways et métros TCL",
        "icon": "🚌",
        "who": "TCL / SYTRAL (réseau de transport en commun)",
        "use": "Position des véhicules et retards en temps réel",
        "freq": "Toutes les 5 min",
    },
    "bronze.meteo": {
        "label": "Météo",
        "icon": "🌦️",
        "who": "Open-Meteo (service météo public)",
        "use": "Température, pluie, vent — influencent trafic et Vélov",
        "freq": "Toutes les heures",
    },
    "bronze.air_quality": {
        "label": "Qualité de l'air",
        "icon": "🌫️",
        "who": "Open-Meteo (indices air)",
        "use": "PM10, PM2.5, NO₂ — bonus sur la page Élu",
        "freq": "Toutes les heures",
    },
    "bronze.chantiers": {
        "label": "Travaux et chantiers",
        "icon": "🚧",
        "who": "Métropole de Lyon (open data)",
        "use": "Zones en chantier qui perturbent la circulation",
        "freq": "Tous les jours",
    },
    "bronze.tomtom_traffic": {
        "label": "Trafic TomTom (cross-validation)",
        "icon": "🛰️",
        "who": "TomTom (API publique, GPS flottes)",
        "use": "Comparaison indépendante avec les boucles Grand Lyon",
        "freq": "Toutes les 15 min",
    },
    "gold.trafic_predictions": {
        "label": "Prédictions du modèle",
        "icon": "🤖",
        "who": "LyonFlow (notre modèle XGBoost)",
        "use": "Vitesses prédites à H+1h — alimentent Mon trajet",
        "freq": "Toutes les 30 min",
    },
    "silver.trafic_boucles_clean": {
        "label": "Boucles nettoyées",
        "icon": "🚗",
        "who": "LyonFlow (déduplication + filtres)",
        "use": "Données boucles propres pour le modèle",
        "freq": "Toutes les 5 min",
    },
    "silver.tcl_vehicles_clean": {
        "label": "TCL nettoyés",
        "icon": "🚌",
        "who": "LyonFlow (parsing SIRI)",
        "use": "Retards et positions TCL normalisés",
        "freq": "Toutes les 5 min",
    },
    "silver.velov_clean": {
        "label": "Vélov nettoyés",
        "icon": "🚴",
        "who": "LyonFlow (déduplication)",
        "use": "Stations Vélov propres pour les prédictions H+30 / H+1",
        "freq": "Toutes les 5 min",
    },
    "silver.meteo_hourly": {
        "label": "Météo horaire",
        "icon": "🌦️",
        "who": "LyonFlow (agrégation horaire)",
        "use": "Variables météo injectées dans les features ML",
        "freq": "Toutes les heures",
    },
    "silver.chantiers_actifs": {
        "label": "Chantiers actifs",
        "icon": "🚧",
        "who": "LyonFlow (filtrage temporel)",
        "use": "Chantiers en cours (début ≤ maintenant ≤ fin)",
        "freq": "Toutes les 5 min",
    },
}


_STATUS_EMOJI = {
    "healthy": "OK",
    "delayed": "Attention",
    "stale": "Attention",
    "dead": "Alerte",
}


def _score_color(score: float) -> str:
    if score >= 80:
        return COLORS["status_ok"]
    if score >= 50:
        return COLORS["status_warning"]
    return COLORS["status_critical"]


def _score_label(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Bon"
    if score >= 50:
        return "Moyen"
    if score >= 25:
        return "Dégradé"
    return "Indisponible"


def _age_label(minutes: float | None) -> str:
    """Âge en minutes → phrase française lisible."""
    if minutes is None:
        return "Aucune donnée récente"
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {int(minutes)} min"
    hours = minutes / 60
    if hours < 24:
        return f"il y a {hours:.1f} h"
    days = hours / 24
    return f"il y a {days:.1f} j"


# =============================================================================
# Page
# =============================================================================
st.set_page_config(
    page_title="Sources de données — LyonFlow",
    page_icon="🌐",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("D'où viennent nos données")
render_data_status_banner()

st.caption(
    "Transparence sur les données qui alimentent les prédictions : qui les "
    "fournit, à quelle fréquence elles arrivent, et si elles sont à jour."
)

# ── 1. Bandeau synthétique ──────────────────────────────────────────────────
with loading_wrapper("Chargement des sources…", "🌐"):
    df = cached_source_health()

if df.empty:
    st.warning("Aucune information de santé des sources disponible.")
else:
    # KPI globaux
    n_total = len(df)
    n_healthy = int((df["status"] == "healthy").sum())
    n_delayed = int((df["status"] == "delayed").sum())
    n_dead = int((df["status"].isin(["stale", "dead"])).sum())
    score_moyen = float(df["health_score"].mean())

    score_color = _score_color(score_moyen)
    score_text = _score_label(score_moyen)

    st.markdown(
        f"""
        <div class="lyonflow-card" style="text-align:center;padding:1.25rem;
             border-left: 4px solid {score_color};">
            <div style="font-size:1rem;opacity:0.8;">Santé globale des données</div>
            <div style="font-size:2rem;font-weight:700;margin-top:0.3rem;
                 color:{score_color};">
                {score_text}
            </div>
            <div style="font-size:0.9rem;opacity:0.7;margin-top:0.5rem;">
                Score moyen {score_moyen:.0f}/100 · {n_healthy} sources à jour
                · {n_delayed} en retard · {n_dead} indisponibles
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    # 3 KPI cards simples
    k1, k2, k3 = st.columns(3)
    k1.metric("À jour", n_healthy, help="Sources dont la dernière donnée date de moins de 1.5× leur intervalle.")
    k2.metric("En retard", n_delayed, help="Données un peu anciennes mais encore exploitables.")
    k3.metric(
        "Indisponibles",
        n_dead,
        help="Pas de donnée depuis longtemps : prédictions moins fiables sur ces dimensions.",
    )

st.markdown("---")

# ── 2. Détail par source ─────────────────────────────────────────────────────
st.markdown("##### Détail par source de données")

if df.empty:
    st.info("Aucun détail disponible pour le moment.")
else:
    # Tri par score de santé croissant (les plus malades en premier → transparence)
    df_sorted = df.sort_values("health_score", ascending=True).reset_index(drop=True)

    for _, row in df_sorted.iterrows():
        source_key = str(row["source"])
        blurb = _SOURCE_BLURB.get(source_key, {})
        label = blurb.get("label", source_key)
        icon = blurb.get("icon", "📊")
        who = blurb.get("who", "Source inconnue")
        use = blurb.get("use", "—")
        freq = blurb.get("freq", "—")

        status = str(row["status"])
        score = float(row["health_score"])
        age = row.get("age_minutes")
        records_1h = row.get("records_1h")
        last_update = row.get("last_update")

        s_color = _score_color(score)
        s_emoji = _STATUS_EMOJI.get(status, "Inconnu")

        # Convertit last_update timestamp si dispo
        last_str = ""
        if last_update is not None and not (
            isinstance(last_update, float) and (last_update != last_update)  # NaN
        ):
            try:
                dt = last_update.to_pydatetime() if hasattr(last_update, "to_pydatetime") else last_update
                if isinstance(dt, datetime):
                    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
                    last_str = dt.strftime("%H:%M")
            except Exception:
                last_str = ""

        rec_str = f"{int(records_1h)}" if records_1h is not None else "—"

        st.markdown(
            f"""
            <div class="lyonflow-card" style="margin-bottom:0.6rem;
                 border-left: 4px solid {s_color};">
                <div style="display:flex;align-items:center;gap:0.75rem;">
                    <div style="font-size:1.6rem;">{icon}</div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:1.05rem;">
                            {s_emoji} {label}
                            <span style="opacity:0.6;font-weight:400;font-size:0.85rem;
                                  margin-left:0.5rem;">{source_key}</span>
                        </div>
                        <div style="opacity:0.8;font-size:0.88rem;margin-top:0.2rem;">
                            {who}
                        </div>
                        <div style="opacity:0.7;font-size:0.82rem;margin-top:0.15rem;">
                            {use} · {freq}
                        </div>
                    </div>
                    <div style="text-align:right;min-width:140px;">
                        <div style="font-size:0.78rem;opacity:0.6;">Dernière donnée</div>
                        <div style="font-weight:600;color:{s_color};">
                            {_age_label(age)}
                        </div>
                        <div style="font-size:0.78rem;opacity:0.55;margin-top:0.15rem;">
                            {rec_str} records/h · score {int(score)}/100
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("---")

# ── 3. Légende ──────────────────────────────────────────────────────────────
with st.expander("Comment on mesure la santé d'une source ?", expanded=False):
    st.markdown(
        """
Chaque source a un **intervalle de mise à jour attendu** (5 min, 1 h, 1 jour…).
On compare l'âge réel de la dernière donnée avec cet intervalle :

- **À jour (healthy)** : la donnée a moins de 1.5× l'intervalle attendu
- **En retard (delayed)** : entre 1.5× et 3× l'intervalle
- **Stale** : entre 3× et 6× l'intervalle
- **Morte (dead)** : plus de 6× l'intervalle, ou aucune donnée

Le **score 0-100** combine la fraîcheur avec le volume reçu sur la dernière
heure. Plus le score est haut, plus la source est fiable pour la prédiction.

Quand une source est dégradée, le modèle s'appuie davantage sur les
autres sources et un warning apparaît sur la page **Statut du service**.
        """,
    )

st.caption(
    "LyonFlow · 8 sources Bronze + 1 source Gold + tables Silver · "
    "Fraîcheur vérifiée toutes les 60s par la vue gold.v_source_health"
)

# Référence cohérente (utilisée dans les autres pages du persona).
_ = STATUS_COLORS
