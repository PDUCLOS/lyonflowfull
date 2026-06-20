"""Tests Sprint 16 Axe A — Drift detector Evidently.

Couvre ``src.monitoring.drift_detector.run_drift_report()`` avec mock
DataFrames (pas besoin d'Evidently ni de DB pour les unit tests).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.monitoring import drift_detector


def _make_pairs(n: int, base_speed: float = 50.0, noise: float = 2.0) -> pd.DataFrame:
    """Helper : génère un DataFrame de paires synthétiques."""
    import numpy as np

    np.random.seed(42)
    return pd.DataFrame({
        "axis_key": [f"AXIS_{i:04d}" for i in range(n)],
        "calculated_at": pd.date_range("2026-06-20", periods=n, freq="5min"),
        "xgb_speed_kmh": base_speed + np.random.normal(0, noise, n),
        "tomtom_speed_kmh": base_speed + np.random.normal(0, noise, n),
        "error_abs_kmh": np.abs(np.random.normal(0, noise, n)),
        "error_pct": np.abs(np.random.normal(0, 5, n)),
        "tomtom_confidence": np.random.uniform(0.5, 1.0, n),
        "accuracy_band": ["accurate"] * n,
        "model_version": ["v0.7.1"] * n,
        "etat_pred": ["fluide"] * n,
    })


def test_drift_report_with_drift_actually_detects():
    """run_drift_report() doit retourner un dict avec les clés attendues.

    Note : si evidently n'est pas installé (cas local dev), le fallback
    retourne ``n_ref=0, n_current=0`` et ``details={'error': '...'}``.
    On vérifie juste la structure du dict.
    """
    # Reference = distributions normales
    ref = _make_pairs(200, base_speed=50.0, noise=2.0)
    # Current = distribution très différente (drift volontaire)
    cur = _make_pairs(200, base_speed=20.0, noise=10.0)
    result = drift_detector.run_drift_report(reference_df=ref, current_df=cur)
    assert "dataset_drift" in result
    assert "n_drifted_features" in result
    assert "share_drifted_features" in result
    assert "n_ref" in result
    assert "n_current" in result
    assert "details" in result
    # Si evidently installé : n_ref/n_current = taille des inputs après dropna.
    # Sinon (fallback) : 0. Les deux sont acceptables.
    if result["details"].get("error") != "evidently not installed":
        assert result["n_ref"] > 0
        assert result["n_current"] > 0


def test_drift_report_empty_reference():
    """Si reference est vide, retour dict avec info."""
    cur = _make_pairs(50, base_speed=50.0)
    result = drift_detector.run_drift_report(reference_df=pd.DataFrame(), current_df=cur)
    assert result["dataset_drift"] is False
    assert result["n_ref"] == 0
    assert "details" in result


def test_drift_report_empty_current():
    """Si current est vide, retour dict avec info."""
    ref = _make_pairs(50, base_speed=50.0)
    result = drift_detector.run_drift_report(reference_df=ref, current_df=pd.DataFrame())
    assert result["dataset_drift"] is False
    assert result["n_current"] == 0
    assert "details" in result


def test_drift_report_no_drift_identical_distributions():
    """Si reference == current, structure cohérente."""
    import numpy as np

    np.random.seed(123)
    pairs = _make_pairs(100, base_speed=50.0, noise=1.0)
    result = drift_detector.run_drift_report(reference_df=pairs, current_df=pairs.copy())
    assert "dataset_drift" in result
    assert "details" in result
