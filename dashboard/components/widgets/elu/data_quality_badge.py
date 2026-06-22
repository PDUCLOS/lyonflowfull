"""Widget — Data Quality badge (Élu — Synthèse).

Sprint 16 Axe B (2026-06-20) — Bandeau compact qui résume la santé
multi-source. Lit ``gold.v_source_health`` (migration 021) et affiche
un badge 1 ligne :
- 🟢 Données OK — 8/8 sources actives, score 94/100
- 🟡 1 source retardée — air_quality stale (2h), score 82/100
- 🔴 Source en panne — tomtom_traffic dead (6h), score 61/100

Coût : 🟢 léger (1 requête). Pas besoin de button-gate.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_source_health
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.exceptions import DashboardDataError


def _classify(n_healthy: int, n_dead: int, n_stale: int, score: float) -> tuple[str, str, str]:
    """Détermine (couleur, icône, message) selon compteurs sources.

    Returns:
        Tuple (color, icon, message).
    """
    if n_dead > 0:
        return ("#F44336", "🔴",
                f"Source en panne — {n_dead} morte(s), score {score:.0f}/100")
    if n_stale > 0:
        return ("#FF9800", "🟡",
                f"{n_stale} source(s) stale — score {score:.0f}/100")
    if score >= 70:
        return ("#4CAF50", "🟢",
                f"Données OK — {n_healthy} sources actives, score {score:.0f}/100")
    return ("#9E9E9E", "⚪", f"Score {score:.0f}/100")


def _global_score(df) -> float:
    """Score global pondéré (mêmes poids que source_health_monitor)."""
    if df.empty:
        return 0.0
    weights = {
        "bronze.trafic_boucles": 3,
        "bronze.tcl_vehicles": 2,
        "bronze.velov": 2,
        "bronze.meteo": 1,
        "bronze.air_quality": 1,
        "bronze.chantiers": 1,
        "bronze.tomtom_traffic": 1,
        "gold.trafic_predictions": 2,
    }
    total_w, sum_w = 0, 0
    for _, row in df.iterrows():
        w = weights.get(row["source"], 1)
        total_w += w
        sum_w += float(row["health_score"]) * w
    return round(sum_w / total_w, 1) if total_w else 0.0


def render_data_quality_badge() -> None:
    """Affiche le bandeau data quality dans Elu_1_Synthese."""
    with loading_wrapper("Chargement Data quality badge…", "⏳"):
        try:
            df = cached_source_health()
        except DashboardDataError as e:
            show_error("db_down", f"⚠️ Data quality indisponible : {e}")
            return

        if df.empty:
            st.info("ℹ️ Données de santé source indisponibles.")
            return

        n_healthy = int((df["status"] == "healthy").sum())
        n_dead = int((df["status"] == "dead").sum())
        n_stale = int((df["status"] == "stale").sum())
        score = _global_score(df)
        color, icon, message = _classify(n_healthy, n_dead, n_stale, score)

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
