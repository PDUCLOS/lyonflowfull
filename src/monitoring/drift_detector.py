"""Drift detector — Compare distribution XGBoost vs TomTom via Evidently.

Sprint 16 Axe A (2026-06-20) — Remplace le placeholder ``check_drift_evidently()``
qui ne faisait que compter les rapports. Utilise ``evidently.DataDriftPreset``
pour détecter un shift dans la distribution des erreurs XGBoost vs TomTom.

Appelé par le DAG ``daily_drift_report`` à 05h30 (après le refresh de
``gold.mv_xgb_vs_tomtom``). Résultat stocké dans ``gold.model_drift_reports``.

Voir ``docs/SPEC_SPRINT_16.md`` §A.4 et §A.11.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from src.data.db_query import get_xgb_vs_tomtom

logger = logging.getLogger(__name__)


# Colonnes numériques à surveiller pour le drift
NUMERICAL_FEATURES = [
    "xgb_speed_kmh",
    "tomtom_speed_kmh",
    "error_abs_kmh",
    "error_pct",
    "tomtom_confidence",
]


def _fetch_reference_current(
    hours_current: int = 24,
    hours_reference: int = 168,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Charge les paires (XGBoost, TomTom) pour les fenêtres reference et current.

    Reference = J-7 → J-1 (168h glissantes, on prend les 6 derniers jours
    pour éviter le chevauchement avec current).
    Current = dernières 24h.

    Returns:
        Tuple (reference_df, current_df). DataFrames vides si pas de données.
    """
    # Récupère toutes les paires sur 7 jours puis splitte
    pairs_7d = get_xgb_vs_tomtom(hours=hours_reference, limit=5000)
    if pairs_7d.empty:
        return pd.DataFrame(), pd.DataFrame()

    if "calculated_at" not in pairs_7d.columns:
        return pairs_7d, pairs_7d  # fallback : tout en current

    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=hours_current)
    current = pairs_7d[pairs_7d["calculated_at"] >= cutoff]
    reference = pairs_7d[pairs_7d["calculated_at"] < cutoff]
    return reference, current


def run_drift_report(
    reference_df: pd.DataFrame | None = None,
    current_df: pd.DataFrame | None = None,
    hours_current: int = 24,
    hours_reference: int = 168,
) -> dict[str, Any]:
    """Compare reference vs current via Evidently DataDriftPreset.

    Args:
        reference_df: DataFrame de référence (None = fetch auto J-7→J-1).
        current_df: DataFrame current (None = fetch auto dernières 24h).
        hours_current: fenêtre current (défaut 24h).
        hours_reference: fenêtre reference (défaut 168h = 7j).

    Returns:
        Dict avec ``dataset_drift`` (bool), ``n_drifted_features`` (int),
        ``share_drifted_features`` (float), ``n_ref`` (int), ``n_current`` (int),
        ``details`` (dict Evidently complet).
    """
    # Import Evidently paresseux (sinon startup lourd)
    try:
        from evidently import ColumnMapping
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report
    except ImportError as e:
        logger.error("Evidently non installé : %s", e)
        return {
            "dataset_drift": False,
            "n_drifted_features": 0,
            "share_drifted_features": 0.0,
            "n_ref": 0,
            "n_current": 0,
            "details": {"error": "evidently not installed"},
        }

    # Fetch si non fourni
    if reference_df is None or current_df is None:
        reference_df, current_df = _fetch_reference_current(
            hours_current=hours_current, hours_reference=hours_reference,
        )

    if reference_df.empty or current_df.empty:
        logger.warning(
            "Drift report impossible : reference=%d, current=%d",
            len(reference_df), len(current_df),
        )
        return {
            "dataset_drift": False,
            "n_drifted_features": 0,
            "share_drifted_features": 0.0,
            "n_ref": len(reference_df),
            "n_current": len(current_df),
            "details": {"info": "empty reference or current"},
        }

    # Filtre colonnes
    available = [c for c in NUMERICAL_FEATURES if c in reference_df.columns and c in current_df.columns]
    if not available:
        return {
            "dataset_drift": False,
            "n_drifted_features": 0,
            "share_drifted_features": 0.0,
            "n_ref": len(reference_df),
            "n_current": len(current_df),
            "details": {"info": "no numerical features available"},
        }

    ref = reference_df[available].dropna()
    cur = current_df[available].dropna()

    column_mapping = ColumnMapping(numerical_features=available)
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=ref, current_data=cur, column_mapping=column_mapping)
    result = report.as_dict()
    drift_info = result.get("metrics", [{}])[0].get("result", {})

    return {
        "dataset_drift": bool(drift_info.get("dataset_drift", False)),
        "n_drifted_features": int(drift_info.get("number_of_drifted_columns", 0)),
        "share_drifted_features": float(drift_info.get("share_of_drifted_columns", 0.0)),
        "n_ref": int(len(ref)),
        "n_current": int(len(cur)),
        "details": drift_info,
    }


def persist_drift_report(report: dict[str, Any], db_connection) -> bool:
    """Insère le rapport dans gold.model_drift_reports.

    Args:
        report: dict retourné par ``run_drift_report()``.
        db_connection: connexion psycopg2 ouverte.

    Returns:
        True si insertion OK, False sinon.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ref_from = now - timedelta(days=7)
    ref_to = now - timedelta(days=1)
    cur_from = now - timedelta(hours=24)
    cur_to = now

    try:
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gold.model_drift_reports (
                    computed_at, dataset_drift, drift_share,
                    n_ref, n_current, ref_from, ref_to,
                    current_from, current_to, report
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    now,
                    report["dataset_drift"],
                    report["share_drifted_features"],
                    report["n_ref"],
                    report["n_current"],
                    ref_from, ref_to, cur_from, cur_to,
                    json.dumps(report["details"], default=str),
                ),
            )
        db_connection.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("persist_drift_report failed: %s", e)
        db_connection.rollback()
        return False
