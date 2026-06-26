"""Tests Helpers db_query TomTom coherence + fail loud.

Vérifie que les nouveaux helpers ``get_tomtom_coherence`` et
``get_tomtom_gl_drift`` (et leurs wrappers data_loader) respectent
la politique zéro mock de lèvent ``DashboardDataError``
quand la DB est indisponible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests (pas de DB locale).

    Patch dans DEUX modules (db_query + data_loader) — voir
    tests/data/test_db_query_and_data_loader.py pour l'explication.
    """
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helpers data_loader : fail loud quand DB indispo
# =============================================================================


def test_load_tomtom_coherence_raises_when_no_db() -> None:
    """load_tomtom_coherence doit lever DashboardDataError si DB indispo."""
    with pytest.raises(DashboardDataError):
        data_loader.load_tomtom_coherence()


def test_load_tomtom_gl_drift_raises_when_no_db() -> None:
    """load_tomtom_gl_drift doit lever DashboardDataError si DB indispo."""
    with pytest.raises(DashboardDataError):
        data_loader.load_tomtom_gl_drift()


# =============================================================================
# get_tomtom_coherence (db_query) — doit exister et retourner un DataFrame vide
# quand DB indispo. En prod, ça raise, mais le helper bas-niveau
# get_tomtom_coherence retourne un DataFrame vide (cf. _df_from_query).
# C'est le wrapper data_loader qui raise.
# =============================================================================


def test_get_tomtom_coherence_returns_empty_when_no_db() -> None:
    """get_tomtom_coherence (bas-niveau) : DataFrame vide si DB indispo."""
    import pandas as pd

    df = db_query.get_tomtom_coherence(limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_tomtom_gl_drift_returns_empty_when_no_db() -> None:
    """get_tomtom_gl_drift (bas-niveau) : DataFrame vide si DB indispo."""
    import pandas as pd

    df = db_query.get_tomtom_gl_drift(limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# =============================================================================
# get_tomtom_latest (existant) doit toujours fonctionner
# =============================================================================


def test_get_tomtom_latest_returns_empty_when_no_db() -> None:
    """Régression : le helper Sprint VPS-6 reste compatible."""
    import pandas as pd

    df = db_query.get_tomtom_latest(limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_tomtom_health_no_key() -> None:
    """Sprint VPS-6 — get_tomtom_health() doit renvoyer un dict même sans clé."""
    h = data_loader.get_tomtom_health()
    assert isinstance(h, dict)
    assert h.get("api_key_configured") is False
