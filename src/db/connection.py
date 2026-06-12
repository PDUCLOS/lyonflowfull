"""DB connection module — SQLAlchemy + psycopg2."""

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
    """Singleton SQLAlchemy engine."""
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
    """Singleton session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager pour transaction SQLAlchemy."""
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
    """Context manager pour connexion psycopg2 brute (COPY, etc.)."""
    s = get_settings()
    conn = psycopg2.connect(
        host=s.db.host,
        port=s.db.port,
        dbname=s.db.db,
        user=s.db.user,
        password=s.db.password,
        # Sprint 8 hotfix 4 (2026-06-12) — Force le search_path au
        # niveau DSN. Le user `lyonflow` du container n'a pas gold
        # dans son search_path par défaut, ce qui faisait planter
        # toutes les queries type `gold.dim_spatial_grid_mapping`.
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
    """Exécute une requête paramétrée, retourne les résultats en list[dict]."""
    with raw_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Sprint 8 hotfix 3 (2026-06-12) — Force search_path explicite.
        # Le user `lyonflow` du container Streamlit a un search_path par
        # défaut qui n'inclut pas `gold` (et autres schémas applicatifs),
        # ce qui faisait planter les queries type
        # `SELECT * FROM gold.dim_spatial_grid_mapping`.
        cur.execute("SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow")
        cur.execute(query, params)
        if cur.description:
            return [dict(row) for row in cur.fetchall()]
        return []


def execute_scalar(query: str, params: tuple = ()) -> object | None:
    """Retourne le premier scalar (première row, première col) ou None."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow")
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else None


def test_connection() -> bool:
    """Health check DB — True si la connexion répond."""
    try:
        return execute_scalar("SELECT 1") == 1
    except Exception:
        return False
