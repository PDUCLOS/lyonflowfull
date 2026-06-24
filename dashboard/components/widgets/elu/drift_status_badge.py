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

import json

import streamlit as st

from dashboard.components.data_cache import cached_xgb_accuracy_summary
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.db_query import get_latest_drift_report
from src.data.exceptions import DashboardDataError

# Seuils MAE pour le badge (km/h)
MAE_GREEN = 7.0
MAE_YELLOW = 12.0


def _diagnose_drift(report: dict) -> tuple[str, str]:
    """Diagnostic métier à partir du rapport PSI (cf spec §5).

    Logique :
    - XGB drift + TomTom stable + errors ↑ → critical "Modèle dégradé"
    - XGB drift + TomTom drift → warning "Changement trafic réel"
    - TomTom confidence drop seul → warning "Oracle moins fiable"
    - errors en hausse seules → warning "Erreurs en hausse"
    - tout stable → ok "Modèle stable"

    Returns:
        Tuple (status, message) où status ∈ {"ok", "warning", "critical"}.
    """
    psi_details = report.get("details", {})

    def _status(col: str) -> str:
        """Lit le statut PSI d'une colonne (stable / moderate / significant)."""
        return psi_details.get(col, {}).get("status", "stable")

    xgb_drift = _status("xgb_speed_kmh") in ("moderate", "significant")
    tomtom_drift = _status("tomtom_speed_kmh") in ("moderate", "significant")
    error_drift = _status("error_abs_kmh") in ("moderate", "significant")
    error_pct_drift = _status("error_pct") in ("moderate", "significant")
    confidence_drift = _status("tomtom_confidence") in ("moderate", "significant")

    if error_drift and xgb_drift and not tomtom_drift:
        return ("critical", "Modèle dégradé — retrain recommandé")
    if xgb_drift and tomtom_drift:
        return ("warning", "Changement trafic réel détecté (vacances, chantier)")
    if confidence_drift and not error_drift and not error_pct_drift:
        return ("warning", "Oracle TomTom moins fiable (vérifier quota/confiance)")
    if error_drift or error_pct_drift:
        return ("warning", "Erreurs en hausse — surveiller")
    if xgb_drift and not tomtom_drift:
        return ("warning", "Prédictions XGBoost décalées")
    return ("ok", "Modèle stable")


def _classify(
    mae_kmh: float | None,
    drift_share: float | None,
    drift_diag: tuple[str, str] | None = None,
) -> tuple[str, str, str]:
    """Détermine (couleur, icône, message) selon MAE + drift.

    Si ``drift_diag`` est fourni (sortie de ``_diagnose_drift``), il prend
    priorité sur la classification générique MAE/drift_share.

    Returns:
        Tuple (color, icon, message).
    """
    if mae_kmh is None and drift_diag is None:
        return ("#9E9E9E", "⚪", "Données MAE indisponibles")

    # Priorité au diagnostic différentiel PSI (plus précis)
    if drift_diag is not None and drift_diag[0] != "ok":
        status, msg = drift_diag
        if status == "critical":
            return ("#F44336", "🔴", msg)
        return ("#FF9800", "🟡", msg)

    # Fallback classification MAE + drift_share (avant PSI)
    if mae_kmh is None:
        return ("#9E9E9E", "⚪", "Données MAE indisponibles")

    if mae_kmh < MAE_GREEN:
        if drift_share and drift_share > 0.0:
            return ("#FF9800", "🟡", f"MAE {mae_kmh:.1f} km/h, {drift_share * 100:.0f}% features en drift")
        return ("#4CAF50", "🟢", f"Modèle stable — MAE {mae_kmh:.1f} km/h")
    if mae_kmh < MAE_YELLOW:
        return (
            "#FF9800",
            "🟡",
            f"Attention — MAE {mae_kmh:.1f} km/h"
            + (f", {drift_share * 100:.0f}% features en drift" if drift_share else ""),
        )
    return ("#F44336", "🔴", f"Drift détecté — MAE {mae_kmh:.1f} km/h, retrain recommandé")


def render_drift_status_badge() -> None:
    """Affiche le bandeau de statut drift + MAE dans Elu_1_Synthese."""
    with st.popover("ℹ️ Qu'est-ce que le PSI ?"):
        st.markdown(
            "Le **PSI (Population Stability Index)** compare la distribution "
            "des features entre 2 périodes (J-14→J-7 vs J-7→J). "
            "**PSI < 0.1** = stable, **0.1-0.2** = modéré, **> 0.2** = drift "
            "significatif → **retrain recommandé** du modèle."
        )
    with loading_wrapper("Chargement Drift status badge…", "⏳"):
        # Lecture des 2 sources
        try:
            summary = cached_xgb_accuracy_summary(hours=24)
            drift = get_latest_drift_report()
        except DashboardDataError as e:
            show_error("db_down", f"⚠️ Drift status indisponible : {e}")
            return

        # MAE 24h
        mae_kmh: float | None = None
        if not summary.empty and "mae_kmh" in summary.columns:
            # Pondération par nombre de paires (les heures avec plus de données
            # pèsent davantage — c'est le MAE global, pas une moyenne de MAE horaires)
            weights = summary["n_pairs"].astype(float)
            if weights.sum() > 0:
                mae_kmh = float((summary["mae_kmh"] * weights).sum() / weights.sum())

        # Drift share + diagnostic différentiel
        drift_share: float | None = None
        drift_diag: tuple[str, str] | None = None
        if drift:
            if "drift_share" in drift:
                try:
                    drift_share = float(drift["drift_share"])
                except (TypeError, ValueError):
                    drift_share = None
            # Le rapport stocke les détails dans 'report' (JSONB).
            # On reconstruit un dict compatible _diagnose_drift.
            report_details = drift.get("report", {})
            if report_details and isinstance(report_details, str):
                try:
                    report_details = json.loads(report_details)
                except (TypeError, ValueError):
                    report_details = {}
            if report_details:
                # report_details est le dict {col: {psi, status, ...}, ...}
                # _diagnose_drift attend {"details": {col: {status, ...}, ...}}
                drift_diag = _diagnose_drift({"details": report_details})

        color, icon, message = _classify(mae_kmh, drift_share, drift_diag)
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
