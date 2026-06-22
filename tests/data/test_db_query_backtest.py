"""Tests Sprint 16 Axe A — Backtest Engine (XGBoost vs TomTom).

Couvre ``src.data.db_query.get_xgb_vs_tomtom()`` et
``get_xgb_accuracy_summary()``. Pas de DB live (skip pattern cf.
``test_db_query_and_data_loader.py``) — on vérifie juste que les helpers
sont importables et retournent des DataFrames vides quand la DB est
indispo (fail loud via DashboardDataError).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests."""
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


def test_get_xgb_vs_tomtom_empty_when_db_down():
    """get_xgb_vs_tomtom() doit retourner un DataFrame vide si DB indispo.

    Politique Sprint 8 : ``_df_from_query`` retourne DataFrame vide + warning
    (pas de DashboardDataError) — le caller gère l'absence de données.
    """
    result = db_query.get_xgb_vs_tomtom(hours=24, limit=500)
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_get_xgb_vs_tomtom_importable():
    """get_xgb_vs_tomtom() doit être importable et avoir la bonne signature."""
    assert callable(db_query.get_xgb_vs_tomtom)
    # Vérif signature via inspect
    import inspect
    sig = inspect.signature(db_query.get_xgb_vs_tomtom)
    assert "hours" in sig.parameters
    assert "limit" in sig.parameters


def test_get_xgb_accuracy_summary_empty_when_db_down():
    """get_xgb_accuracy_summary() doit retourner un DataFrame vide si DB indispo."""
    result = db_query.get_xgb_accuracy_summary(hours=168)
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_get_xgb_accuracy_summary_importable():
    """get_xgb_accuracy_summary() doit être importable avec signature correcte."""
    assert callable(db_query.get_xgb_accuracy_summary)
    import inspect
    sig = inspect.signature(db_query.get_xgb_accuracy_summary)
    assert "hours" in sig.parameters
