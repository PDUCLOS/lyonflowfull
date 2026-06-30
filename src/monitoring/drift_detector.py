"""Détecteur de Dérive (Drift Detector) — Comparaison XGBoost vs TomTom (PSI + Evidently).

Architecture :
- **Moteur principal** : PSI (Population Stability Index, via ``src.monitoring.psi``).
  Zéro dépendance, déterministe et léger. Couvre 100% des besoins opérationnels quotidiens.
- **Moteur optionnel** : Evidently (génération de rapports HTML à la demande,
  utile pour le dashboard professionnel ou l'analyse locale). Chargement paresseux (lazy load)
  afin d'éviter de saturer les DAGs réguliers avec des dépendances lourdes (+250 Mo Docker).

Ce module est exécuté quotidiennement (ex: via le DAG ``daily_drift_report``)
juste après l'actualisation de la vue ``gold.mv_xgb_vs_tomtom``. Les résultats
sont persistés dans la table ``gold.model_drift_reports``.

Diagnostic différentiel :
- XGBoost Drift + TomTom stable + Augmentation des erreurs → **Modèle dégradé** (nécessite un ré-entraînement).
- XGBoost Drift + TomTom Drift → **Changement structurel du trafic réel** (ex: vacances, chantier majeur).
- Baisse de confiance TomTom seule → **Oracle dégradé** (vérifier l'état de l'API externe / quotas).
- Stable partout → RAS.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC
from typing import Any

import pandas as pd

from src.data.db_query import get_xgb_vs_tomtom

logger = logging.getLogger(__name__)


# Colonnes numériques à surveiller pour le drift (alignées sur gold.mv_xgb_vs_tomtom)
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
    """Calcule le rapport de drift via PSI (moteur principal).

    Args:
        reference_df: DataFrame de référence (None = fetch auto J-7→J-1).
        current_df: DataFrame current (None = fetch auto dernières 24h).
        hours_current: fenêtre current (défaut 24h).
        hours_reference: fenêtre reference (défaut 168h = 7j).

    Returns:
        Dict avec ``dataset_drift`` (bool), ``n_drifted_features`` (int),
        ``share_drifted_features`` (float), ``n_ref`` (int), ``n_current`` (int),
        ``details`` (dict par colonne : {psi, status, ...}), ``engine`` (str = "psi").
    """
    # Fetch si non fourni
    if reference_df is None or current_df is None:
        reference_df, current_df = _fetch_reference_current(
            hours_current=hours_current,
            hours_reference=hours_reference,
        )

    base_result = {
        "dataset_drift": False,
        "n_drifted_features": 0,
        "share_drifted_features": 0.0,
        "n_ref": len(reference_df),
        "n_current": len(current_df),
        "details": {},
        "engine": "psi",
    }

    if reference_df.empty or current_df.empty:
        base_result["details"] = {"info": "empty reference or current"}
        return base_result

    # Filtre colonnes disponibles
    available = [c for c in NUMERICAL_FEATURES if c in reference_df.columns and c in current_df.columns]
    if not available:
        base_result["details"] = {"info": "no numerical features available"}
        return base_result

    # Calcul PSI (zéro dépendance, voir src/monitoring/psi.py)
    from src.monitoring.psi import compute_dataset_drift

    psi_result = compute_dataset_drift(
        reference=reference_df,
        current=current_df,
        columns=available,
    )
    summary = psi_result.pop("_summary")

    return {
        "dataset_drift": bool(summary["dataset_drift"]),
        "n_drifted_features": int(summary["n_columns_drifted"]),
        "share_drifted_features": float(summary["drift_share"]),
        "n_ref": len(reference_df),
        "n_current": len(current_df),
        "details": psi_result,  # {col: {psi, status, ...}, ...}
        "engine": "psi",
    }


def generate_html_drift_report(
    reference_df: pd.DataFrame | None = None,
    current_df: pd.DataFrame | None = None,
    hours_current: int = 24,
    hours_reference: int = 168,
) -> str | None:
    """Génère un rapport HTML Evidently v0.7 (usage on-demand, pas DAG).

    Args:
        reference_df: DataFrame de référence (None = fetch auto).
        current_df: DataFrame current (None = fetch auto).
        hours_current: fenêtre current (défaut 24h).
        hours_reference: fenêtre reference (défaut 168h).

    Returns:
        HTML en string ou None si Evidently non installé / données vides.
        NE PAS utiliser dans un DAG — usage Pro_7 on-demand uniquement
        (rapport visuel riche pour exploration ponctuelle).
    """
    try:
        from evidently import Report as EvidentlyReport
        from evidently.presets import DataDriftPreset
    except ImportError:
        logger.info("Evidently non installé, generate_html_drift_report retourne None")
        return None

    # Fetch si non fourni
    if reference_df is None or current_df is None:
        reference_df, current_df = _fetch_reference_current(
            hours_current=hours_current,
            hours_reference=hours_reference,
        )

    available = [c for c in NUMERICAL_FEATURES if c in reference_df.columns and c in current_df.columns]
    if not available:
        return None

    ref = reference_df[available].dropna()
    cur = current_df[available].dropna()
    if ref.empty or cur.empty:
        return None

    try:
        report = EvidentlyReport(metrics=[DataDriftPreset()])
        snapshot = report.run(current_data=cur, reference_data=ref)
        return snapshot.get_html_str()
    except Exception as e:
        logger.error("Evidently HTML report failed: %s", e)
        return None


def persist_drift_report(report: dict[str, Any], db_connection) -> bool:
    """Insère le rapport dans gold.model_drift_reports.

    Args:
        report: dict retourné par ``run_drift_report()``.
        db_connection: connexion psycopg2 ouverte.

    Returns:
        True si insertion OK, False sinon.
    """
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
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
                    ref_from,
                    ref_to,
                    cur_from,
                    cur_to,
                    json.dumps(report["details"], default=str),
                ),
            )
        db_connection.commit()
        return True
    except Exception as e:
        logger.error("persist_drift_report failed: %s", e)
        db_connection.rollback()
        return False
