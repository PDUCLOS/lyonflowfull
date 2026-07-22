"""Page Usager — Statut du service (santé globale en direct).

 Ajout du menu MLOps Usager. Cette page est le "tableau de
bord" citoyen du service : 4 voyants simples (Données / Modèle / Service /
Alertes) + incidents récents + un encart pédagogique sur ce qui peut
affecter la fiabilité des prédictions.
"""

from __future__ import annotations

import logging

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.colors import COLORS, STATUS_COLORS
from dashboard.components.data_cache import (
    cached_predictions_vs_actuals,
    cached_recent_alerts,
    cached_source_health,
    cached_xgb_accuracy_summary,
)
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers
# =============================================================================
def _kpi_data() -> dict | None:
    """KPI #1 — Santé des données (toutes sources Bronze + Gold)."""
    df = cached_source_health()
    if df.empty:
        return None
    n_total = len(df)
    n_healthy = int((df["status"] == "healthy").sum())
    score_moyen = float(df["health_score"].mean())
    return {
        "score": score_moyen,
        "ratio": n_healthy / n_total if n_total else 0,
        "n_total": n_total,
        "n_healthy": n_healthy,
    }


def _kpi_model() -> dict | None:
    """KPI #2 — Fraîcheur + précision du modèle."""
    mae_df = cached_xgb_accuracy_summary(hours=168)
    if mae_df.empty:
        return None
    n_accurate = int(mae_df["n_accurate"].sum())
    n_acceptable = int(mae_df["n_acceptable"].sum())
    n_poor = int(mae_df["n_poor"].sum())
    n_total = n_accurate + n_acceptable + n_poor
    pct_accurate = n_accurate / n_total if n_total else 0
    mae_global = float(mae_df["mae_kmh"].mean())
    return {
        "pct_accurate": pct_accurate,
        "mae_kmh": mae_global,
        "n_total": n_total,
    }


def _kpi_predictions() -> dict | None:
    """KPI #3 — Service (la dernière prédiction tourne-t-elle ?)."""
    df = cached_predictions_vs_actuals(limit=10)
    if df.empty:
        return None
    # Si on a des données, le service produit bien des prédictions
    return {"n_rows": len(df)}


def _kpi_alerts() -> dict:
    """KPI #4 — Alertes actives 6h."""
    df = cached_recent_alerts(hours=6, limit=50)
    n_total = len(df)
    n_critical = int((df["severity"] == "critical").sum()) if "severity" in df.columns else 0
    return {"n_total": n_total, "n_critical": n_critical}


def _status_pill(label: str, score: float) -> tuple[str, str]:
    """Traduit un score 0-100 en (emoji, label) citoyen."""
    if score >= 80:
        return "OK", label.format(status="Opérationnel")
    if score >= 50:
        return "Attention", label.format(status="Dégradé")
    return "Alerte", label.format(status="Perturbé")


def _gauge_card(emoji: str, title: str, value: str, subtitle: str, color: str) -> str:
    """HTML d'une carte KPI 1/4."""
    return f"""
    <div class="lyonflow-card" style="text-align:center;padding:1.1rem;height:100%;
         border-left: 4px solid {color};">
        <div style="font-size:0.85rem;opacity:0.7;text-transform:uppercase;
             letter-spacing:0.05em;">{title}</div>
        <div style="font-size:2.2rem;font-weight:700;margin:0.4rem 0;color:{color};">
            {emoji}
        </div>
        <div style="font-size:1rem;font-weight:600;">{value}</div>
        <div style="font-size:0.78rem;opacity:0.65;margin-top:0.3rem;">{subtitle}</div>
    </div>
    """


# =============================================================================
# Page
# =============================================================================
st.set_page_config(
    page_title="Statut du service — LyonFlow",
    page_icon="🩺",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("Santé du service en direct")
render_data_status_banner()

st.caption(
    "Un coup d'œil en 30 secondes : les données arrivent-elles ? le modèle "
    "est-il à jour ? et y a-t-il des perturbations en cours ?"
)

# ── 1. 4 voyants synthétiques ───────────────────────────────────────────────
with loading_wrapper("Vérification du service…", "🩺"):
    k_data = _kpi_data()
    k_model = _kpi_model()
    k_pred = _kpi_predictions()
    k_alerts = _kpi_alerts()

# --- Données
if k_data:
    score = k_data["score"]
    pill, status = _status_pill("{status}", score)
    data_value = f"{pill} {status}"
    data_sub = f"{k_data['n_healthy']}/{k_data['n_total']} sources à jour · score {score:.0f}/100"
    data_color = (
        COLORS["status_ok"] if score >= 80 else (COLORS["status_warning"] if score >= 50 else COLORS["status_critical"])
    )
else:
    data_value = "Indéterminé"
    data_sub = "Source de données momentanément indisponible"
    data_color = COLORS["text_muted"]

# --- Modèle
if k_model:
    pct = k_model["pct_accurate"]
    mae = k_model["mae_kmh"]
    if pct >= 0.75 and mae <= 5.0:
        pill, status = "OK", "Très fiable"
        color = COLORS["status_ok"]
    elif pct >= 0.60 and mae <= 8.0:
        pill, status = "Attention", "Fiable"
        color = COLORS["status_warning"]
    else:
        pill, status = "Attention", "Prudence"
        color = COLORS["status_warning"]
    model_value = f"{pill} {status}"
    model_sub = f"{pct * 100:.0f}% précises (±5 km/h) · erreur moy. {mae:.1f} km/h"
else:
    model_value = "Indéterminé"
    model_sub = "Pas encore 7 jours d'historique de production"
    color = COLORS["text_muted"]
model_color = color

# --- Service (prédictions)
if k_pred:
    pill, status = "OK", "En ligne"
    serv_color = COLORS["status_ok"]
    serv_sub = f"{k_pred['n_rows']} prédictions récentes (échantillon)"
else:
    pill, status = "Attention", "À surveiller"
    serv_color = COLORS["status_warning"]
    serv_sub = "Pas de prédiction récente trouvée"
serv_value = f"{pill} {status}"
serv_color = serv_color

# --- Alertes
n_alerts = k_alerts["n_total"]
n_critical = k_alerts["n_critical"]
if n_critical == 0 and n_alerts <= 3:
    pill, status = "OK", "Tout roule"
    alert_color = COLORS["status_ok"]
    alert_sub = f"{n_alerts} alerte(s) info sur les 6 dernières heures"
elif n_critical <= 1:
    pill, status = "Attention", "Quelques incidents"
    alert_color = COLORS["status_warning"]
    alert_sub = f"{n_critical} critique · {n_alerts - n_critical} info sur 6h"
else:
    pill, status = "Alerte", "Plusieurs incidents"
    alert_color = COLORS["status_critical"]
    alert_sub = f"{n_critical} critiques · {n_alerts - n_critical} info sur 6h"
alert_value = f"{pill} {status}"

# Render 4 KPI cards
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(
        _gauge_card("🌐", "Données", data_value, data_sub, data_color),
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        _gauge_card("🤖", "Modèle", model_value, model_sub, model_color),
        unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        _gauge_card("⚡", "Service", serv_value, serv_sub, serv_color),
        unsafe_allow_html=True,
    )
with col4:
    st.markdown(
        _gauge_card("🔔", "Alertes", alert_value, alert_sub, alert_color),
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── 2. Incidents récents (résumé des alertes) ──────────────────────────────
st.markdown("##### Derniers incidents détectés")

with loading_wrapper("Chargement des alertes…", "🚨"):
    alerts_df = cached_recent_alerts(hours=24, limit=10)

if alerts_df.empty:
    st.success("Aucun incident détecté sur les dernières 24 heures.")
else:
    # Limite à 5 alertes max pour ne pas noyer l'usager
    top = alerts_df.head(5)
    for _, row in top.iterrows():
        severity = str(row.get("severity", "info"))
        if severity == "critical":
            icon = "Alerte"
            color = COLORS["status_critical"]
        elif severity == "warning":
            icon = "Attention"
            color = COLORS["status_warning"]
        else:
            icon = "Attention"
            color = COLORS["status_info"]

        title = str(row.get("title") or row.get("description") or "Alerte")
        # Tronque si trop long
        if len(title) > 90:
            title = title[:87] + "…"
        action = str(row.get("action") or "—")

        st.markdown(
            f"""
            <div class="lyonflow-card" style="margin-bottom:0.5rem;
                 border-left: 3px solid {color};padding:0.7rem 1rem;">
                <div style="font-weight:600;color:{color};">
                    {icon} {severity.upper()}
                </div>
                <div style="margin-top:0.2rem;font-size:0.95rem;">{title}</div>
                <div style="opacity:0.7;font-size:0.82rem;margin-top:0.2rem;">
                    {action}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if len(alerts_df) > 5:
        st.caption(f"+ {len(alerts_df) - 5} autres alertes — voir la page Alertes")

st.markdown("---")

# ── 3. Ce qui peut affecter la fiabilité ─────────────────────────────────────
with st.container():
    st.markdown("##### Qu'est-ce qui peut affecter la fiabilité ?")
    st.markdown(
        """
- **Conditions météo extrêmes** (forte pluie, neige, brouillard dense) :
  le modèle connaît la pluie mais ne peut pas deviner l'ampleur de la réaction
  des automobilistes.
- **Travaux non programmés** : si une voirie est coupée sans signalement
  dans l'open data Grand Lyon, le modèle suit la tendance habituelle.
- **Pics exceptionnels** (événements sportifs, salons, grèves) : le
  modèle apprend en continu mais un événement rare peut dégrader la précision
  ponctuellement.
- **Panne d'une source** : si une source Bronze est indisponible, le
  modèle compense avec les autres sources. La page
  **Sources de données** te dit lesquelles sont à jour.
- **Nuit et week-end** : la précision peut être légèrement différente
  car les patterns historiques sont moins denses (moins de données
  d'entraînement à ces heures).

**Conseil pratique** : si tu vois un voyant Attention ou Alerte sur cette page,
compte ~5-10% de marge d'erreur supplémentaire sur les temps de trajet
estimés dans **Mon trajet**.
        """,
    )

st.caption("LyonFlow · 4 voyants synthétiques · 8 sources Bronze · Modèle XGBoost H+1h · Alertes 24h glissantes")

# Cohérence inter-pages
_ = STATUS_COLORS
