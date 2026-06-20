"""Widget — Drift status badge (Élu — Synthèse).

Sprint 16 Axe A (2026-06-20) — Bandeau compact qui résume l'état de drift
détecté sur les prédictions XGBoost H+1h (via Evidently DataDriftPreset,
calculé par le DAG daily_drift_report à 05h30).

Lit ``gold.model_drift_reports`` (Sprint 10+, table pré-existante) via le
helper ``get_latest_drift_report()`` (déjà dans db_query.py). Combine
ensuite avec la MAE 24h depuis ``gold.v_xgb_accuracy_summary`` (migration
020) pour un diagnostic plus précis.

Affiche une ligne HTML :
- 🟢 Modèle stable — MAE 7.2 km/h, 0 feature en drift
- 🟡 Attention — MAE 12.4 km/h, 1 feature en drift
- 🔴 Drift détecté — MAE 18.1 km/h, retrain recommandé

Coût : 🟢 léger (1 requête scalaire). Pas besoin de button-gate.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_xgb_accuracy_summary
from src.data.db_query import get_latest_drift_report
from src.data.exceptions import DashboardDataError


# Seuils MAE pour le badge (km/h)
MAE_GREEN = 7.0
MAE_YELLOW = 12.0


def _classify(mae_kmh: float | None, drift_share: float | None) -> tuple[str, str, str]:
    """Détermine (couleur, icône, message) selon MAE + drift.

    Returns:
        Tuple (color, icon, message).
    """
    if mae_kmh is None:
        return ("#9E9E9E", "⚪", "Données MAE indisponibles")

    if mae_kmh < MAE_GREEN:
        if drift_share and drift_share > 0.0:
            return ("#FF9800", "🟡",
                    f"MAE {mae_kmh:.1f} km/h, {drift_share * 100:.0f}% features en drift")
        return ("#4CAF50", "🟢", f"Modèle stable — MAE {mae_kmh:.1f} km/h")
    if mae_kmh < MAE_YELLOW:
        return ("#FF9800", "🟡",
                f"Attention — MAE {mae_kmh:.1f} km/h"
                + (f", {drift_share * 100:.0f}% features en drift" if drift_share else ""))
    return ("#F44336", "🔴",
            f"Drift détecté — MAE {mae_kmh:.1f} km/h, retrain recommandé")


def render_drift_status_badge() -> None:
    """Affiche le bandeau de statut drift + MAE dans Elu_1_Synthese."""
    # Lecture des 2 sources
    try:
        summary = cached_xgb_accuracy_summary(hours=24)
        drift = get_latest_drift_report()
    except DashboardDataError as e:
        st.error(f"⚠️ Drift status indisponible : {e}")
        return

    # MAE 24h
    mae_kmh: float | None = None
    if not summary.empty and "mae_kmh" in summary.columns:
        # Pondération par nombre de paires (les heures avec plus de données
        # pèsent davantage — c'est le MAE global, pas une moyenne de MAE horaires)
        weights = summary["n_pairs"].astype(float)
        if weights.sum() > 0:
            mae_kmh = float((summary["mae_kmh"] * weights).sum() / weights.sum())

    # Drift share
    drift_share: float | None = None
    if drift and "drift_share" in drift:
        try:
            drift_share = float(drift["drift_share"])
        except (TypeError, ValueError):
            drift_share = None

    color, icon, message = _classify(mae_kmh, drift_share)
    st.markdown(
        f"""
        <div class="lyonflow-card" style="display:flex;align-items:center;gap:0.8rem;
                    padding:0.6rem 0.9rem;border-left:4px solid {color};
                    margin-bottom:0.5rem;">
            <span style="font-size:1.4rem;">{icon}</span>
            <span style="font-weight:600;">{message}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
