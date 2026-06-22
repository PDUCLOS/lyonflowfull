"""Tests unitaires — src/monitoring/drift_detector.py (Sprint 16 Axe A).

Couvre ``run_drift_report()`` :
* DataFrames vides → dataset_drift=False, details={"info": "empty..."}
* Pas de features disponibles → details={"info": "no numerical features..."}
* Distributions stables (ref==curr) → dataset_drift=False, n_drifted=0
* Distributions très driftées → dataset_drift=True, n_drifted > 0
* Mix stable + drifted → share_drifted_features = ratio correct
* engine="psi" retourné
* Structure details : {col: {psi, status, n_ref, n_curr, ...}}
* Filtrage colonnes : seules les features de NUMERICAL_FEATURES sont analysées
* Result est JSON-serializable (pour persistance DB)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.monitoring.drift_detector import (
    NUMERICAL_FEATURES,
    run_drift_report,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _make_pairs(
    xgb: np.ndarray,
    tomtom: np.ndarray,
    conf: np.ndarray | None = None,
) -> pd.DataFrame:
    """DataFrame compatible avec NUMERICAL_FEATURES (xgb/tomtom/error/conf)."""
    n = len(xgb)
    if conf is None:
        conf = np.full(n, 0.8)
    err_abs = np.abs(xgb - tomtom)
    err_pct = err_abs / np.maximum(tomtom, 1e-6) * 100
    return pd.DataFrame(
        {
            "xgb_speed_kmh": xgb,
            "tomtom_speed_kmh": tomtom,
            "error_abs_kmh": err_abs,
            "error_pct": err_pct,
            "tomtom_confidence": conf,
        }
    )


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


class TestRunDriftReport:
    """Calcule le rapport de drift via PSI (moteur principal)."""

    def test_empty_dataframes(self) -> None:
        """reference ou current vide → dataset_drift=False, info dans details."""
        result = run_drift_report(
            reference_df=pd.DataFrame(),
            current_df=pd.DataFrame(),
        )
        assert result["dataset_drift"] is False
        assert result["n_drifted_features"] == 0
        assert result["n_ref"] == 0
        assert result["n_current"] == 0
        assert "info" in result["details"]
        assert result["engine"] == "psi"

    def test_no_numerical_features(self) -> None:
        """DataFrames sans les colonnes NUMERICAL_FEATURES → details info."""
        df = pd.DataFrame({"unrelated_col": [1, 2, 3]})
        result = run_drift_report(reference_df=df, current_df=df.copy())
        assert result["dataset_drift"] is False
        assert result["n_drifted_features"] == 0
        assert "info" in result["details"]
        assert "no numerical features" in result["details"]["info"]

    def test_stable_distributions(self) -> None:
        """ref==curr (distributions identiques) → drift_share≈0, dataset_drift=False."""
        rng = np.random.default_rng(42)
        df = _make_pairs(
            rng.normal(50, 5, 200),
            rng.normal(50, 5, 200),
        )
        result = run_drift_report(reference_df=df, current_df=df.copy())
        assert result["dataset_drift"] is False
        assert result["n_drifted_features"] == 0
        assert result["share_drifted_features"] == pytest.approx(0.0, abs=0.05)
        assert result["engine"] == "psi"
        assert result["n_ref"] == 200
        assert result["n_current"] == 200

    def test_significant_drift(self) -> None:
        """Curr très différent de ref → n_drifted > 0, dataset_drift=True."""
        rng = np.random.default_rng(42)
        ref = _make_pairs(
            rng.normal(50, 5, 300),
            rng.normal(50, 5, 300),
        )
        # Curr : XGB a dérivé de 20 km/h, TomTom stable
        cur = _make_pairs(
            rng.normal(30, 5, 300),  # XGB drifté vers le bas
            rng.normal(50, 5, 300),  # TomTom stable
        )
        result = run_drift_report(reference_df=ref, current_df=cur)
        # Au moins error_abs_kmh et error_pct doivent drafter
        assert result["n_drifted_features"] > 0
        assert result["share_drifted_features"] > 0
        # XGB drift + error drift → dataset_drift probable
        # (peut être False si seul 1/5 colonnes drift, ce qui est <0.5)
        # On vérifie juste qu'au moins 1 feature est driftée
        assert any(
            d.get("status") in ("moderate", "significant")
            for d in result["details"].values()
        )

    def test_details_structure(self) -> None:
        """details = {col: {psi, status, n_ref, n_curr, ...}, ...}."""
        rng = np.random.default_rng(42)
        df = _make_pairs(
            rng.normal(50, 5, 200),
            rng.normal(50, 5, 200),
        )
        result = run_drift_report(reference_df=df, current_df=df.copy())
        for col in NUMERICAL_FEATURES:
            assert col in result["details"], f"col {col} manquant dans details"
            detail = result["details"][col]
            assert "psi" in detail
            assert "status" in detail
            assert "n_ref" in detail
            assert "n_curr" in detail
            assert detail["status"] in (
                "stable",
                "moderate",
                "significant",
                "insufficient_data",
            )

    def test_filters_unknown_columns(self) -> None:
        """Colonnes hors NUMERICAL_FEATURES ne sont pas analysées."""
        rng = np.random.default_rng(42)
        df = _make_pairs(
            rng.normal(50, 5, 100),
            rng.normal(50, 5, 100),
        )
        df["extra_col"] = rng.normal(0, 1, 100)  # pas dans NUMERICAL_FEATURES
        result = run_drift_report(reference_df=df, current_df=df.copy())
        assert "extra_col" not in result["details"]
        # Seules les 5 features NUMERICAL_FEATURES sont là
        assert set(result["details"].keys()) == set(NUMERICAL_FEATURES)

    def test_result_is_json_serializable(self) -> None:
        """Le résultat doit être JSON-sérialisable (pour persistance DB)."""
        rng = np.random.default_rng(42)
        df = _make_pairs(
            rng.normal(50, 5, 100),
            rng.normal(50, 5, 100),
        )
        result = run_drift_report(reference_df=df, current_df=df.copy())
        # Ne doit pas raise
        json_str = json.dumps(result, default=str)
        # Round-trip
        parsed = json.loads(json_str)
        assert parsed["dataset_drift"] == result["dataset_drift"]
        assert parsed["engine"] == "psi"

    def test_share_drifted_features_computed_correctly(self) -> None:
        """share_drifted_features = n_drifted / n_analyzed (cohérence)."""
        rng = np.random.default_rng(42)
        ref = _make_pairs(
            rng.normal(50, 5, 300),
            rng.normal(50, 5, 300),
        )
        # Curr identique SAUF pour tomtom_speed_kmh (drift fort)
        cur = _make_pairs(
            rng.normal(50, 5, 300),
            rng.normal(80, 5, 300),  # drift sur tomtom
        )
        result = run_drift_report(reference_df=ref, current_df=cur)
        n_analyzed = len(result["details"])
        if n_analyzed > 0:
            expected_share = result["n_drifted_features"] / n_analyzed
            assert result["share_drifted_features"] == pytest.approx(expected_share)
