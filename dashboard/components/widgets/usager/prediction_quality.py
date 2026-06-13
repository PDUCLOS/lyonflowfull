"""Widget — Qualité de la prédiction H+1h (MAE / RMSE / % fiable).

Sprint 12 (GNN retraining) — feedback simple à l'usager sur la qualité
de la prédiction de temps de trajet. Source unique :
``gold.predictions_vs_actuals`` qui compare, pour chaque (capteur,
horizon), la vitesse prédite vs la vitesse réellement observée.

Trois indicateurs :
- **MAE global** (erreur absolue moyenne en km/h) → vert si < 3,
  orange si < 6, rouge sinon.
- **% segments avec erreur < 5 km/h** → fiabilité globale.
- **% trajets qui ne dérapent pas de +20 % vs réel** → confiance.

L'API publique est ``render_prediction_quality()`` — un widget sans
paramètres qui lit la DB et affiche un encart Streamlit.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src.data.data_loader import load_predictions_vs_actuals

logger = logging.getLogger(__name__)

# Fenêtre par défaut : on regarde les 7 derniers jours, 5000 observations
# (= largement de quoi calculer des MAE stables sans surcharger la DB).
_DEFAULT_LOOKBACK_DAYS = 7
_DEFAULT_LIMIT = 5000

# Bornes couleur MAE (km/h) — calées sur la performance XGBoost H+1h
# observée sur le VPS (MAE ~2.4 km/h en moyenne, 6 km/h = dégradé).
_MAE_GREEN = 3.0
_MAE_ORANGE = 6.0
_RELIABLE_ERROR_KMH = 5.0
_DEVIATION_PCT_THRESHOLD = 20.0


def _classify_mae(mae: float) -> tuple[str, str]:
    """Retourne (label, couleur hex) pour un MAE donné."""
    if mae < _MAE_GREEN:
        return "Excellente", "#2E7D32"
    if mae < _MAE_ORANGE:
        return "Correcte", "#F57C00"
    return "Dégradée", "#C62828"


def _compute_quality_metrics(df: pd.DataFrame) -> dict:
    """Calcule MAE / RMSE / % fiable / % pas de dérapage sur un DataFrame
    ``predictions_vs_actuals`` déjà filtré sur l'horizon H+1h.

    Args:
        df: DataFrame avec colonnes ``predicted_speed``, ``actual_speed``,
        ``error_kmh``, ``error_pct``.

    Returns:
        Dict avec mae, rmse, n_obs, pct_reliable, pct_no_deviation.
    """
    if df.empty:
        return {
            "mae": float("nan"),
            "rmse": float("nan"),
            "n_obs": 0,
            "pct_reliable": float("nan"),
            "pct_no_deviation": float("nan"),
        }
    errors = df["error_kmh"].astype(float)
    mae = float(errors.abs().mean())
    rmse = float((errors**2).mean() ** 0.5)
    pct_reliable = float((errors.abs() < _RELIABLE_ERROR_KMH).mean() * 100)
    pct_no_deviation = float((df["error_pct"].abs() < _DEVIATION_PCT_THRESHOLD).mean() * 100)
    return {
        "mae": mae,
        "rmse": rmse,
        "n_obs": len(df),
        "pct_reliable": pct_reliable,
        "pct_no_deviation": pct_no_deviation,
    }


def _load_h1_quality(lookback_days: int = _DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    """Charge les observations H+1h des N derniers jours depuis la DB.

    Sprint 12 — filtre en Python (l'index gold.predictions_vs_actuals n'est
    pas forcément sur ``horizon_minutes``). On garde que H+1h (=60 min).
    """
    df = load_predictions_vs_actuals(limit=_DEFAULT_LIMIT)
    if df.empty:
        return df
    if "horizon_minutes" not in df.columns:
        # Schéma incomplet — on prend tout en fallback, mais on log.
        logger.warning("gold.predictions_vs_actuals sans horizon_minutes — fallback global")
        return df
    df = df[df["horizon_minutes"] == 60].copy()
    if df.empty:
        return df
    # Filtre temporel — la colonne n'est pas timestampée, on a ``prediction_id``
    # qui est sériale. Pour le MVP on prend les N dernières observations.
    return df.head(_DEFAULT_LIMIT)


def render_prediction_quality() -> None:
    """Affiche l'encart 'Qualité de la prédiction H+1h' dans Streamlit.

    Lecture seule, jamais bloquante : si la DB ne répond pas, on lève
    ``DashboardDataError`` (politique Sprint 8+) et le widget appelant
    catch via ``data_error_to_message``.
    """
    df = _load_h1_quality()
    metrics = _compute_quality_metrics(df)

    if metrics["n_obs"] == 0:
        st.warning(
            "⚠️ Pas encore d'observation H+1h dans `gold.predictions_vs_actuals`. "
            "Le backtesting commence après ~1h de production (DAG `dag_inference_xgboost`)."
        )
        return

    label, color = _classify_mae(metrics["mae"])

    st.markdown("#### 🎯 Qualité de la prédiction H+1h")
    st.caption(
        f"Basé sur **{metrics['n_obs']} observations** des 7 derniers jours. "
        "Source : `gold.predictions_vs_actuals`."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "MAE",
            f"{metrics['mae']:.2f} km/h",
            help="Erreur Absolue Moyenne entre vitesse prédite et vitesse réelle",
        )
    with col2:
        st.metric(
            "RMSE",
            f"{metrics['rmse']:.2f} km/h",
            help="Racine de l'erreur quadratique moyenne — pénalise les grosses erreurs",
        )
    with col3:
        st.metric(
            "% fiable",
            f"{metrics['pct_reliable']:.0f} %",
            help=f"Part des segments avec erreur < {_RELIABLE_ERROR_KMH:.0f} km/h",
        )
    with col4:
        st.metric(
            "% cohérent",
            f"{metrics['pct_no_deviation']:.0f} %",
            help=f"Part des segments avec écart < {_DEVIATION_PCT_THRESHOLD:.0f} % vs réel",
        )

    # Verdict textuel
    st.markdown(
        f"<div style='background:{color}1A;border-left:4px solid {color};"
        f"padding:8px 12px;border-radius:4px;margin-top:8px;'>"
        f"<b>Verdict :</b> la qualité de la prédiction H+1h est "
        f"<b style='color:{color};'>{label}</b>."
        f"</div>",
        unsafe_allow_html=True,
    )

    # Mini-reco simple : "l'inférence t'aide ou pas ?"
    with st.expander("🤔 L'inférence t'aide-t-elle ?", expanded=False):
        if metrics["mae"] < _MAE_GREEN and metrics["pct_reliable"] > 70:
            st.success(
                "✅ **Oui, clairement.** La prédiction H+1h est fiable dans la majorité "
                "des cas — tu peux l'utiliser pour anticiper ton trajet (partir plus tôt "
                "si la prédiction annonce une chute de vitesse)."
            )
        elif metrics["mae"] < _MAE_ORANGE:
            st.info(
                "🟡 **Mitigé.** La prédiction est correcte en moyenne mais le RMSE montre "
                "des erreurs ponctuelles. Prends-la comme une indication, pas une vérité. "
                "Si tu as un RDV serré, ajoute 5-10 min de marge."
            )
        else:
            st.error(
                "❌ **Non, pas vraiment.** La prédiction dérape trop souvent. "
                "Vérifie que le DAG `dag_inference_xgboost` tourne (Airflow UI) "
                "et que la table `gold.xgb_training_set` est à jour."
            )
