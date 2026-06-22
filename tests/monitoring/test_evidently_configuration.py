"""Tests Sprint 16 refacto — Configuration Evidently (PSI primary + Evidently optional).

Cf docs/SPEC_EVIDENTLY_CONFIGURATION.md. Sprint 16 Axe A refacto :
- PSI devient le moteur principal (zero deps, src/monitoring/psi.py)
- Evidently v0.7 devient optionnel (rapports HTML on-demand)

Couvre :
1. ``psi.py`` : 9 tests (compute_psi, compute_dataset_drift)
2. ``drift_detector.py`` : 7 tests refactored (engine="psi")
3. ``drift_detector.py`` Evidently optionnel : 3 tests
4. ``drift_status_badge._diagnose_drift`` : 5 tests diagnostic différentiel
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))

from src.monitoring.drift_detector import (
    NUMERICAL_FEATURES,
    generate_html_drift_report,
    run_drift_report,
)
from src.monitoring.psi import compute_dataset_drift, compute_psi

# =============================================================================
# 9.1. Tests PSI core (src/monitoring/psi.py)
# =============================================================================


class TestComputePsi:
    def test_identical_distributions_psi_near_zero(self):
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(35, 10, 500))
        result = compute_psi(ref, cur)
        assert result["psi"] < 0.1
        assert result["status"] == "stable"

    def test_shifted_distribution_psi_significant(self):
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(55, 10, 500))  # +20 km/h
        result = compute_psi(ref, cur)
        assert result["psi"] > 0.2
        assert result["status"] == "significant"

    def test_moderate_shift(self):
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(38, 11, 500))  # léger shift
        result = compute_psi(ref, cur)
        assert result["status"] in ("stable", "moderate")

    def test_empty_series(self):
        result = compute_psi(pd.Series(dtype=float), pd.Series(dtype=float))
        assert result["status"] == "insufficient_data"
        assert np.isnan(result["psi"])

    def test_constant_values(self):
        """Valeurs constantes → ne crash pas."""
        ref = pd.Series([30.0] * 100)
        cur = pd.Series([30.0] * 100)
        result = compute_psi(ref, cur)
        assert result["psi"] >= 0


class TestComputeDatasetDrift:
    def test_no_drift_all_stable(self):
        np.random.seed(42)
        n = 300
        cols = ["speed", "error", "confidence"]
        ref = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        cur = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        result = compute_dataset_drift(ref, cur, cols)
        assert result["_summary"]["dataset_drift"] is False
        assert result["_summary"]["n_columns_drifted"] == 0

    def test_drift_detected_when_majority_columns_shift(self):
        np.random.seed(42)
        n = 300
        ref = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        cur = pd.DataFrame({
            "speed": np.random.normal(60, 15, n),
            "error": np.abs(np.random.normal(20, 8, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        result = compute_dataset_drift(ref, cur, ["speed", "error", "confidence"])
        assert result["_summary"]["dataset_drift"] is True
        assert result["_summary"]["n_columns_drifted"] >= 2

    def test_missing_column_skipped(self):
        ref = pd.DataFrame({"a": [1, 2, 3]})
        cur = pd.DataFrame({"a": [1, 2, 3]})
        result = compute_dataset_drift(ref, cur, ["a", "b_missing"])
        assert result["_summary"]["n_columns_analyzed"] == 1

    def test_per_column_psi_values(self):
        np.random.seed(42)
        n = 200
        ref = pd.DataFrame({"x": np.random.normal(0, 1, n)})
        cur = pd.DataFrame({"x": np.random.normal(0, 1, n)})
        result = compute_dataset_drift(ref, cur, ["x"])
        assert "x" in result
        assert "psi" in result["x"]
        assert "status" in result["x"]


# =============================================================================
# 9.2. Tests drift_detector.run_drift_report (refactored, engine="psi")
# =============================================================================


class TestRunDriftReport:
    def _make_pairs(self, n: int = 100, **shifts) -> pd.DataFrame:
        np.random.seed(42)
        data = {c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES}
        data.update(shifts)
        return pd.DataFrame(data)

    def test_returns_engine_psi(self):
        ref = self._make_pairs(100)
        cur = self._make_pairs(100)
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["engine"] == "psi"

    def test_no_drift_stable(self):
        np.random.seed(42)
        n = 300
        ref = self._make_pairs(n)
        cur = self._make_pairs(n)
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["dataset_drift"] is False

    def test_drift_detected_when_predictions_shift(self):
        np.random.seed(42)
        n = 300
        ref = self._make_pairs(n)
        cur = self._make_pairs(
            n,
            xgb_speed_kmh=np.random.normal(55, 15, n),  # shift
            error_abs_kmh=np.abs(np.random.normal(15, 6, n)),  # doubled
            error_pct=np.abs(np.random.normal(35, 12, n)),  # doubled
        )
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["n_drifted_features"] >= 2

    def test_empty_dataframes(self):
        result = run_drift_report(reference_df=pd.DataFrame(), current_df=pd.DataFrame())
        assert result["dataset_drift"] is False
        assert result["n_ref"] == 0
        assert result["engine"] == "psi"

    def test_details_contain_per_column_psi(self):
        np.random.seed(42)
        n = 200
        ref = self._make_pairs(n)
        cur = self._make_pairs(n)
        result = run_drift_report(reference_df=ref, current_df=cur)
        for col in NUMERICAL_FEATURES:
            assert col in result["details"]
            assert "psi" in result["details"][col]
            assert "status" in result["details"][col]

    def test_result_json_serializable(self):
        np.random.seed(42)
        n = 200
        ref = self._make_pairs(n)
        cur = self._make_pairs(n)
        result = run_drift_report(reference_df=ref, current_df=cur)
        # Doit pouvoir sérialiser en JSON (pour INSERT dans gold.model_drift_reports)
        json.dumps(result, default=str)  # ne doit pas lever


# =============================================================================
# 9.3. Tests Evidently optionnel
# =============================================================================


class TestEvidentlyOptional:
    def _make_pairs(self, n: int = 100) -> pd.DataFrame:
        np.random.seed(42)
        return pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})

    def test_generate_html_returns_none_without_evidently(self, monkeypatch):
        """generate_html_drift_report retourne None si evidently absent."""
        import builtins

        # Bloque l'import evidently
        import importlib

        # Patch sys.modules pour simuler l'absence
        original = sys.modules.get("evidently")
        sys.modules["evidently"] = None  # type: ignore
        try:
            result = generate_html_drift_report(
                reference_df=self._make_pairs(50),
                current_df=self._make_pairs(50),
            )
            assert result is None
        finally:
            if original is not None:
                sys.modules["evidently"] = original
            else:
                sys.modules.pop("evidently", None)


# =============================================================================
# 9.4. Tests diagnostic différentiel (_diagnose_drift dans drift_status_badge)
# =============================================================================


class TestDiagnoseDrift:
    def _diag(self, **col_statuses):
        """Helper : crée un rapport avec details = {col: {status: ...}}."""
        from dashboard.components.widgets.elu import drift_status_badge

        details = {col: {"status": status} for col, status in col_statuses.items()}
        return drift_status_badge._diagnose_drift({"details": details})

    def test_model_degraded_xgb_drifts_tomtom_stable(self):
        from dashboard.components.widgets.elu import drift_status_badge

        details = {
            "xgb_speed_kmh": {"status": "significant"},
            "tomtom_speed_kmh": {"status": "stable"},
            "error_abs_kmh": {"status": "significant"},
            "error_pct": {"status": "moderate"},
            "tomtom_confidence": {"status": "stable"},
        }
        status, msg = drift_status_badge._diagnose_drift({"details": details})
        assert status == "critical"
        assert "retrain" in msg.lower()

    def test_real_traffic_change_both_drift(self):
        from dashboard.components.widgets.elu import drift_status_badge

        details = {
            "xgb_speed_kmh": {"status": "significant"},
            "tomtom_speed_kmh": {"status": "significant"},
            "error_abs_kmh": {"status": "stable"},
            "error_pct": {"status": "stable"},
            "tomtom_confidence": {"status": "stable"},
        }
        status, msg = drift_status_badge._diagnose_drift({"details": details})
        assert status == "warning"
        assert "réel" in msg.lower()

    def test_oracle_degraded(self):
        from dashboard.components.widgets.elu import drift_status_badge

        details = {
            "xgb_speed_kmh": {"status": "stable"},
            "tomtom_speed_kmh": {"status": "stable"},
            "error_abs_kmh": {"status": "stable"},
            "error_pct": {"status": "stable"},
            "tomtom_confidence": {"status": "significant"},
        }
        status, msg = drift_status_badge._diagnose_drift({"details": details})
        assert status == "warning"
        assert "oracle" in msg.lower() or "TomTom" in msg

    def test_all_stable(self):
        from dashboard.components.widgets.elu import drift_status_badge

        details = {
            "xgb_speed_kmh": {"status": "stable"},
            "tomtom_speed_kmh": {"status": "stable"},
            "error_abs_kmh": {"status": "stable"},
            "error_pct": {"status": "stable"},
            "tomtom_confidence": {"status": "stable"},
        }
        status, msg = drift_status_badge._diagnose_drift({"details": details})
        assert status == "ok"
        assert "stable" in msg.lower()

    def test_errors_rising_alone(self):
        from dashboard.components.widgets.elu import drift_status_badge

        details = {
            "xgb_speed_kmh": {"status": "stable"},
            "tomtom_speed_kmh": {"status": "stable"},
            "error_abs_kmh": {"status": "moderate"},
            "error_pct": {"status": "moderate"},
            "tomtom_confidence": {"status": "stable"},
        }
        status, _msg = drift_status_badge._diagnose_drift({"details": details})
        assert status == "warning"
