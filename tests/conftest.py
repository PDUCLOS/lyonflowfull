"""Conftest centralisé Sprint 8 (2026-06-12) — fixtures partagées pour pytest.

But : permettre aux tests unitaires de tourner SANS PostgreSQL (donc sur
la machine de dev et en CI) en mockant la couche DB via une fixture
``mock_db``. Pour les tests d'intégration qui ont vraiment besoin de la
DB, on garde la marque ``@pytest.mark.integration`` (déjà skippable).

Philosophie :
- Les modules src/* qui font ``from src.db.connection import ...`` ne
  savent pas qu'ils sont mockés — le patch monkeypatche la fonction au
  niveau du module, pas de psycopg2.
- MockDB retourne des réponses cohérentes avec le schéma v0.3.1
  (lag_h1, sin_hour, channel_id string) — pas le vieux schéma.

Usage::

    def test_x(mock_db):
        mock_db.set_response("SELECT ...", [{"speed_kmh": 30.0}])
        from src.foo import bar
        assert bar() == ...
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

# Sprint 8 — Le projet n'a pas de conftest à la racine tests/.
# Ce conftest doit être importable par tous les sous-dossiers (data, ml, etc.)
# pytest discovery charge automatiquement conftest.py à chaque niveau.

# Permet les imports ``from src.xxx import yyy`` depuis les tests
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class MockDB:
    """Mock intelligent pour psycopg2 — simule execute_query / execute_scalar.

    Permet de définir des réponses en mode "pattern matching" :::

        db = MockDB()
        db.set_response("FROM gold.dim_spatial_grid_mapping", [...rows...])
        # Toute query contenant ce pattern renverra ces rows
    """

    def __init__(self) -> None:
        self.responses: list[tuple[str, list[dict]]] = []
        self.queries_log: list[str] = []
        self._default_response: list[dict] = []

    def set_response(self, pattern: str, rows: list[dict]) -> None:
        """Définit la réponse pour toute query contenant ``pattern``."""
        self.responses.append((pattern, rows))

    def set_default(self, rows: list[dict]) -> None:
        """Réponse par défaut si aucun pattern ne match."""
        self._default_response = rows

    def execute_query(self, query: str, params: tuple = ()) -> list[dict]:
        """Simule src.db.connection.execute_query."""
        self.queries_log.append(query)
        for pattern, rows in self.responses:
            if pattern in query:
                return list(rows)
        return list(self._default_response)

    def execute_scalar(self, query: str, params: tuple = ()) -> Any:
        rows = self.execute_query(query, params)
        if not rows:
            return None
        first = rows[0]
        if isinstance(first, dict):
            return next(iter(first.values()))
        return first[0]

    def raw_connection(self):
        """Simule le context manager raw_connection (utilisé dans le DAG cron)."""
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cur
            yield mock_conn

        return _cm()

    def raw_connection_noop(self):
        """Variante no-op (pour tests où la connexion ne fait rien)."""

        class _NoOpCtx:
            def __enter__(self):
                return MagicMock(), MagicMock()

            def __exit__(self, *args):
                return False

        return _NoOpCtx()


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MockDB:
    """Fixture MockDB : patche ``src.db.connection.execute_query`` etc.

    Usage::

        def test_x(mock_db):
            mock_db.set_response("FROM gold.dim_spatial_grid_mapping", [...])
            # Maintenant n'importe quel code qui fait
            # ``from src.db.connection import execute_query`` recevra
            # le mock.
    """
    db = MockDB()
    # Patche le module src.db.connection (et tous les modules qui en dépendent)
    import src.db.connection as conn_module

    monkeypatch.setattr(conn_module, "execute_query", db.execute_query)
    monkeypatch.setattr(conn_module, "execute_scalar", db.execute_scalar)
    monkeypatch.setattr(conn_module, "raw_connection", db.raw_connection)
    return db


@pytest.fixture
def demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``LYONFLOW_DEMO_MODE=1`` (mode démo local)."""
    monkeypatch.setenv("LYONFLOW_DEMO_MODE", "1")


@pytest.fixture
def prod_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``LYONFLOW_DEMO_MODE=0`` (mode prod, fail loud)."""
    monkeypatch.setenv("LYONFLOW_DEMO_MODE", "0")
    # Reset le cache de _is_demo_mode entre les tests
    from src.data.data_loader import _is_demo_mode

    _is_demo_mode.cache_clear()


@pytest.fixture
def reset_demo_mode_cache() -> None:
    """Reset le cache de _is_demo_mode entre tests (idempotence)."""
    from src.data.data_loader import _is_demo_mode

    _is_demo_mode.cache_clear()
    yield
    _is_demo_mode.cache_clear()
