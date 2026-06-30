"""Module de connexion à la base de données — Intégration SQLAlchemy et psycopg2.

Ce module gère le cycle de vie des connexions à la base de données PostgreSQL
de l'application. Il instancie un pool de connexions SQLAlchemy optimisé
(pool_size=10, max_overflow=20) avec un mécanisme de "pre-ping" pour
éviter les erreurs de connexions mortes ("server closed the connection unexpectedly").

Il propose également des wrappers pour les requêtes brutes via `psycopg2`,
qui forcent automatiquement le `search_path` sur tous les schémas analytiques
(public, gold, bronze, silver, referentiel, airflow_db, mlflow).
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """Fournit le moteur SQLAlchemy (Engine) sous forme de Singleton.

    Configure le pool de connexions avec un "pre-ping" pour assurer la robustesse
    des connexions longues.

    Returns:
        Engine: L'instance unique du moteur de base de données SQLAlchemy.
    """
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            s.db.url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Fournit la fabrique de sessions SQLAlchemy (sessionmaker) en mode Singleton.

    Returns:
        sessionmaker: La fabrique de sessions liée au moteur principal.
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Gestionnaire de contexte pour les transactions SQLAlchemy.

    Garantit la validation (commit) de la transaction en cas de succès,
    son annulation (rollback) en cas d'erreur, et la fermeture propre
    de la session dans tous les cas.

    Yields:
        Session: Une session active SQLAlchemy.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def raw_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Gestionnaire de contexte pour une connexion brute psycopg2.

    Utile pour les requêtes natives très performantes (ex. commandes COPY)
    ou pour contourner l'overhead de l'ORM. Configure explicitement le
    `search_path` de la base de données.

    Yields:
        psycopg2.extensions.connection: Connexion active à PostgreSQL.
    """
    s = get_settings()
    conn = psycopg2.connect(
        host=s.db.host,
        port=s.db.port,
        dbname=s.db.db,
        user=s.db.user,
        password=s.db.password,
        options="-c search_path=public,gold,bronze,silver,referentiel,airflow_db,mlflow",
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """Exécute une requête SQL paramétrée et retourne une liste de dictionnaires.

    Le format `list[dict]` est idéal pour la conversion directe en DataFrame Pandas
    dans la couche d'accès aux données.

    Args:
        query (str): La requête SQL paramétrée (avec des `%s`).
        params (tuple): Les variables à injecter de manière sécurisée.

    Returns:
        list[dict]: Les résultats sous forme de dictionnaire par ligne.
    """
    with raw_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow")
        cur.execute(query, params)
        if cur.description:
            return [dict(row) for row in cur.fetchall()]
        return []


def execute_scalar(query: str, params: tuple = ()) -> object | None:
    """Exécute une requête SQL et retourne uniquement la première valeur de la première colonne.

    Idéal pour les requêtes d'agrégation (ex. COUNT, SUM) ou les vérifications (ex. SELECT 1).

    Args:
        query (str): La requête SQL paramétrée.
        params (tuple): Les variables de la requête.

    Returns:
        object | None: La valeur scalaire trouvée, ou None si aucun résultat.
    """
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow")
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else None


def test_connection() -> bool:
    """Vérifie l'état de la connexion à la base de données (Health check).

    Returns:
        bool: True si la base répond correctement à `SELECT 1`, False sinon.
    """
    try:
        return execute_scalar("SELECT 1") == 1
    except Exception:
        return False
