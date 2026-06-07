"""DB module — connection pool, helpers, ORM.

Exposed API:
- get_engine / get_session_factory : SQLAlchemy singleton
- session_scope : context manager transaction
- raw_connection : context manager psycopg2 brut
- execute_query / execute_scalar : helpers requêtes paramétrées
- test_connection : health check
"""

from src.db.connection import (
    get_engine,
    get_session_factory,
    session_scope,
    raw_connection,
    execute_query,
    execute_scalar,
    test_connection,
)

__all__ = [
    "get_engine",
    "get_session_factory",
    "session_scope",
    "raw_connection",
    "execute_query",
    "execute_scalar",
    "test_connection",
]
