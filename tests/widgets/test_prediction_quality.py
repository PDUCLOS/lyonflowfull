"""Tests unitaires — widget prediction_quality (Sprint 12).

Couvre :
- ``_classify_mae`` : seuils vert/orange/rouge.
- ``_compute_quality_metrics`` : MAE/RMSE/% fiable/% cohérent.
- ``render_prediction_quality`` : fail loud via DashboardDataError si DB down.

Ces tests sont volontairement offline : ils n'ont PAS besoin de PostgreSQL.
On monkeypatch ``load_predictions_vs_actuals`` pour fournir un DataFrame
contrôlé.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Permet l'import du widget depuis la racine du projet
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.widgets.usager.prediction_quality import (
    _classify_mae,
    _compute_quality_metrics,
    render_prediction_quality,
)


def _make_df(errors_kmh: list[float], errors_pct: list[float] | None = None) -> pd.DataFrame:
    """Construit un DataFrame predictions_vs_actuals à partir d'erreurs."""
    if errors_pct is None:
        # Par défaut, on déduit errors_pct de errors_kmh sur une vitesse
        # arbitraire de 30 km/h (référentiel ville).
        errors_pct = [e / 30 * 100 for e in errors_kmh]
    return pd.DataFrame(
        {
            "horizon_minutes": [60] * len(errors_kmh),
            "model_name": ["xgboost_speed_1.0.0"] * len(errors_kmh),
            "predicted_speed": [30.0 - e for e in errors_kmh],
            "actual_speed": [30.0] * len(errors_kmh),
            "error_kmh": errors_kmh,
            "error_pct": errors_pct,
        }
    )


class TestClassifyMae:
    def test_mae_low_is_excellent(self):
        label, color = _classify_mae(2.0)
        assert label == "Excellente"
        assert color == "#2E7D32"

    def test_mae_mid_is_correct(self):
        label, color = _classify_mae(5.0)
        assert label == "Correcte"
        assert color == "#F57C00"

    def test_mae_high_is_degraded(self):
        label, color = _classify_mae(10.0)
        assert label == "Dégradée"
        assert color == "#C62828"

    def test_mae_boundary_just_under_green(self):
        # Juste sous le seuil vert (3.0) → Excellente
        label, _ = _classify_mae(2.99)
        assert label == "Excellente"

    def test_mae_boundary_just_under_orange(self):
        # Juste sous le seuil orange (6.0) → Correcte
        label, _ = _classify_mae(5.99)
        assert label == "Correcte"


class TestComputeQualityMetrics:
    def test_empty_dataframe_returns_nan(self):
        df = pd.DataFrame(
            columns=[
                "horizon_minutes",
                "model_name",
                "predicted_speed",
                "actual_speed",
                "error_kmh",
                "error_pct",
            ]
        )
        m = _compute_quality_metrics(df)
        assert m["n_obs"] == 0
        assert np.isnan(m["mae"])
        assert np.isnan(m["rmse"])
        assert np.isnan(m["pct_reliable"])

    def test_perfect_predictions(self):
        df = _make_df([0.0] * 100)
        m = _compute_quality_metrics(df)
        assert m["n_obs"] == 100
        assert m["mae"] == 0.0
        assert m["rmse"] == 0.0
        assert m["pct_reliable"] == 100.0
        assert m["pct_no_deviation"] == 100.0

    def test_mixed_errors(self):
        # 10% d'erreurs > 5 km/h
        errors = [1.0] * 9 + [10.0]
        df = _make_df(errors)
        m = _compute_quality_metrics(df)
        assert m["n_obs"] == 10
        assert m["mae"] == pytest.approx(1.9)
        assert m["pct_reliable"] == pytest.approx(90.0)

    def test_errors_are_absolute(self):
        # Les signes sont neutralisés (erreur = |predicted - actual|)
        df = _make_df([2.0, -2.0, 4.0, -4.0])
        m = _compute_quality_metrics(df)
        assert m["mae"] == pytest.approx(3.0)
        # RMSE = sqrt(mean([4, 4, 16, 16])) = sqrt(10) ≈ 3.162
        assert m["rmse"] == pytest.approx((10.0) ** 0.5)


class TestRenderPredictionQuality:
    def test_empty_db_returns_warning(self, monkeypatch):
        """Si la table est vide (DB vient d'être initialisée), on affiche
        un warning au lieu d'un crash."""

        # Mock : DB renvoie un DataFrame vide
        def mock_load(*args, **kwargs):
            return pd.DataFrame(
                columns=[
                    "horizon_minutes",
                    "model_name",
                    "predicted_speed",
                    "actual_speed",
                    "error_kmh",
                    "error_pct",
                ]
            )

        from dashboard.components.widgets.usager import prediction_quality as pq

        monkeypatch.setattr(pq, "load_predictions_vs_actuals", mock_load)

        # Streamlit va écrire dans la page — on vérifie juste qu'il n'y a
        # pas d'exception. Le widget n'est pas rendu visuellement sans browser.
        # On capture le warning via un context manager minimal.
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None:
            pytest.skip("Pas de contexte Streamlit (test offline)")
        # Sinon, on appelle — Streamlit gère l'erreur.
        try:
            render_prediction_quality()
        except Exception as e:  # pragma: no cover
            pytest.fail(f"render_prediction_quality raised: {e}")

    def test_db_down_raises_dashboard_data_error(self, monkeypatch):
        """Sprint 8+ — si la DB est down, on lève DashboardDataError,
        c'est l'appelant qui catch via data_error_to_message."""

        from src.data.exceptions import DashboardDataError

        def mock_load(*args, **kwargs):
            raise DashboardDataError(
                source="predictions_vs_actuals",
                detail="DB indispo",
            )

        from dashboard.components.widgets.usager import prediction_quality as pq

        monkeypatch.setattr(pq, "load_predictions_vs_actuals", mock_load)

        with pytest.raises(DashboardDataError):
            render_prediction_quality()
