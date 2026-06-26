"""Couche Base de données (DB) — Gestion du pool de connexions, ORM et requêtes.

Ce module expose les utilitaires essentiels pour interagir avec la base PostgreSQL.
Il fournit à la fois des sessions ORM SQLAlchemy pour les interactions complexes
et des connexions brutes `psycopg2` pour les requêtes de haute performance.

Interface publique exposée :
- `get_engine` / `get_session_factory` : Modèle Singleton pour SQLAlchemy.
- `session_scope` : Gestionnaire de contexte (context manager) pour les transactions ORM.
- `raw_connection` : Gestionnaire de contexte pour les connexions brutes `psycopg2`.
- `execute_query` / `execute_scalar` : Fonctions utilitaires pour l'exécution sécurisée 
  de requêtes SQL paramétrées.
- `test_connection` : Fonction de vérification de l'état de la base de données (Health check).
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
