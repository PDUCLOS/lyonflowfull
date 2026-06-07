"""DB module — connection pool, helpers, ORM.

Exposed API:
- get_engine / get_session_factory : SQLAlchemy singleton
- session_scope : context manager transaction
- raw_connection : context manager psycopg2 brut
- execute_query / execute_scalar : helpers requêtes paramétrées
- test_connection : health check
"""

from src.db.connection import (
    execute_query,
    execute_scalar,
    get_engine,
    get_session_factory,
    raw_connection,
    session_scope,
    test_connection,
)

__all__ = [
    "execute_query",
    "execute_scalar",
    "get_engine",
    "get_session_factory",
    "raw_connection",
    "session_scope",
    "test_connection",
]
