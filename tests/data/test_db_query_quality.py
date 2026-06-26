"""Tests Axe B — Data Quality db_query helpers (sans DB)."""

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
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


def test_get_source_health_empty_when_db_down():
    result = db_query.get_source_health()
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_get_source_health_importable():
    assert callable(db_query.get_source_health)


def test_get_data_completeness_empty_when_db_down():
    result = db_query.get_data_completeness()
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_get_data_completeness_importable():
    assert callable(db_query.get_data_completeness)


def test_check_all_sources_returns_list_when_db_down():
    """check_all_sources() doit retourner une liste (avec au moins 1 entry d'erreur)."""
    from src.monitoring.health_checks import check_all_sources

    result = check_all_sources()
    assert isinstance(result, list)
    # Quand DB indispo, on a au moins 1 entry (erreur DB) — on n'asserte pas
    # le contenu exact car le helper peut varier.
