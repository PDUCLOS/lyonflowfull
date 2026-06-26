"""Population Stability Index (PSI) — Détection de dérive (Drift) légère en pur Python.

Ce détecteur de dérive est notamment utilisé par le DAG de préparation des données 
d'entraînement (`build_xgb_training_set`) pour comparer les distributions 
(features et target) entre deux fenêtres temporelles (ex: semaine de référence vs semaine courante).
Les résultats sont persistés dans la table `gold.model_drift_reports`.

**Avantages du PSI par rapport à des outils lourds (ex: Evidently)** :
- Zéro dépendance tierce (évite les conflits de version sur litestar/pydantic).
- Standard reconnu de l'industrie (largement utilisé en credit scoring et marketing).
- Rapide, déterministe (complexité temporelle minimale après calcul des histogrammes).
- Interprétation claire : < 0.1 (Stable), entre 0.1 et 0.2 (Modéré), > 0.2 (Dérive significative).

**Méthode de regroupement (Bucketing)** : 
Approche basée sur les quantiles via `pd.qcut` (10 buckets par défaut) afin 
de gérer efficacement les distributions asymétriques ou non-uniformes (ex: vitesse du trafic).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _safe_psi_term(pct_ref: float, pct_curr: float, eps: float = 1e-6) -> float:
    """Un terme de la somme PSI, protégé contre log(0) et division par 0.

    Convention : si pct_curr == 0 et pct_ref == 0, on ignore le terme
    (les deux bins sont vides). Si pct_curr == 0 et pct_ref > 0, on
    utilise pct_curr = eps pour pouvoir calculer le log.
    """
    if pct_ref < eps and pct_curr < eps:
        return 0.0
    if pct_curr < eps:
        pct_curr = eps
    if pct_ref < eps:
        pct_ref = eps
    return (pct_curr - pct_ref) * np.log(pct_curr / pct_ref)


def compute_psi(
    reference: pd.Series,
    current: pd.Series,
    n_buckets: int = 10,
) -> dict:
    """Calcule le PSI entre deux distributions 1D.

    Args:
        reference: distribution de référence (semaine J-14 → J-7).
        current: distribution courante (semaine J-7 → J).
        n_buckets: nombre de buckets quantile-based (défaut 10).

    Returns:
        Dict avec :
            - psi: float, le score PSI total
            - n_ref: int, nb d'observations de référence
            - n_curr: int, nb d'observations courantes
            - bucket_edges: list[float], les bornes des buckets
            - ref_pcts: list[float], % par bucket côté ref
            - curr_pcts: list[float], % par bucket côté curr
            - status: str, "stable" | "moderate" | "significant"
    """
    ref = reference.dropna()
    curr = current.dropna()
    n_ref, n_curr = len(ref), len(curr)
    if n_ref == 0 or n_curr == 0:
        return {
            "psi": float("nan"),
            "n_ref": n_ref,
            "n_curr": n_curr,
            "status": "insufficient_data",
            "bucket_edges": [],
            "ref_pcts": [],
            "curr_pcts": [],
        }

    # Découpe en quantiles sur la référence (le bucket boundaries doit
    # être dérivé de la ref pour éviter de biaiser le test si la curr
    # a une distribution très différente).
    try:
        # pd.qcut peut échouer si trop de valeurs dupliquées (ex. speed_kmh
        # constant sur un channel). On fallback sur cut avec edges manuels.
        _, edges = pd.qcut(ref, q=n_buckets, retbins=True, duplicates="drop")
    except ValueError:
        # Fallback : linspace entre min et max
        edges = np.linspace(ref.min(), ref.max(), n_buckets + 1)

    # Pad edges pour inclure les bornes extrêmes
    edges[0] = -np.inf
    edges[-1] = np.inf

    # Histogrammes
    ref_counts = np.histogram(ref, bins=edges)[0]
    curr_counts = np.histogram(curr, bins=edges)[0]

    ref_pcts = ref_counts / ref_counts.sum()
    curr_pcts = curr_counts / curr_counts.sum()

    # PSI
    psi = sum(_safe_psi_term(float(r), float(c)) for r, c in zip(ref_pcts, curr_pcts, strict=True))

    if psi < 0.1:
        status = "stable"
    elif psi < 0.2:
        status = "moderate"
    else:
        status = "significant"

    return {
        "psi": float(psi),
        "n_ref": int(n_ref),
        "n_curr": int(n_curr),
        "status": status,
        "bucket_edges": [float(e) for e in edges],
        "ref_pcts": [float(p) for p in ref_pcts],
        "curr_pcts": [float(p) for p in curr_pcts],
    }


def compute_dataset_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    columns: Iterable[str],
    n_buckets: int = 10,
) -> dict:
    """Calcule le drift sur un dataset entier (multi-features).

    Returns:
        Dict ``{column: {psi, status, ...}, _summary: {drift_share, dataset_drift}}``.
        Le ``drift_share`` est la proportion de colonnes avec drift
        modéré ou significatif. Si > 0.5 → ``dataset_drift = True``.
    """
    results = {}
    n_drifted = 0
    n_total = 0
    for col in columns:
        if col not in reference.columns or col not in current.columns:
            logger.warning("Column '%s' missing from one side — skip", col)
            continue
        psi_result = compute_psi(reference[col], current[col], n_buckets=n_buckets)
        results[col] = psi_result
        n_total += 1
        if psi_result["status"] in ("moderate", "significant"):
            n_drifted += 1

    drift_share = n_drifted / n_total if n_total > 0 else 0.0
    return {
        **results,
        "_summary": {
            "drift_share": drift_share,
            "dataset_drift": drift_share > 0.5,
            "n_columns_analyzed": n_total,
            "n_columns_drifted": n_drifted,
        },
    }
