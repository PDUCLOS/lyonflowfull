"""Tests d'intégration — Infrastructure (DB, config)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_config_loads_defaults():
    """Le module config doit s'importer même sans .env."""
    from src.config import get_settings

    s = get_settings()
    # Sprint 9+ (2026-06-17) — assertion non-versionnée pour ne plus casser
    # à chaque bump. On vérifie juste que la version est non vide + format semver.
    assert s.app_version
    parts = s.app_version.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"app_version doit être semver (X.Y.Z), got: {s.app_version}"
    )
    assert s.db.host is not None
    assert s.mlflow.tracking_uri is not None


def test_db_module_importable():
    from src.db import execute_query, get_engine, test_connection

    assert callable(get_engine)
    assert callable(execute_query)
    assert callable(test_connection)


def test_db_connection_if_available():
    """Si la DB tourne, on doit pouvoir se connecter. Skip sinon."""
    from src.db import test_connection

    if not test_connection():
        pytest.skip("PostgreSQL non disponible — test skipped")


def test_ingestion_base_importable():
    from src.ingestion import DataCollector, FetchResult

    assert DataCollector is not None
    assert FetchResult is not None


def test_all_8_collectors_importable():
    """Les 8 collecteurs doivent tous s'importer."""
    from src.ingestion import (
        AirQualityOpenMeteo,
        CalendrierScolaire,
        ChantiersGrandLyon,
        JoursFeries,
        MeteoOpenMeteo,
        TclSiriLite,
        TraficGrandLyon,
        VelovCollector,
    )

    classes = [
        TraficGrandLyon,
        VelovCollector,
        MeteoOpenMeteo,
        AirQualityOpenMeteo,
        ChantiersGrandLyon,
        TclSiriLite,
        CalendrierScolaire,
        JoursFeries,
    ]
    for cls in classes:
        assert cls is not None
        # Vérifie que ça s'instancie
        instance = cls()
        assert instance.source is not None
        assert instance.bronze_table is not None


def test_transformation_module_importable():
    from src.transformation import transform_silver_to_gold, transform_to_silver

    assert callable(transform_to_silver)
    assert callable(transform_silver_to_gold)


def test_rgpd_module_importable():
    from src.rgpd import log_audit, log_data_subject_request, set_user_consent

    assert callable(log_audit)
    assert callable(log_data_subject_request)
    assert callable(set_user_consent)


def test_rgpd_hashing_is_anonymous():
    """Le hash SHA256 doit être anonymisé et non réversible trivialement."""
    from src.rgpd.service import _hash

    h1 = _hash("192.168.1.1")
    h2 = _hash("192.168.1.1")
    h3 = _hash("192.168.1.2")
    assert h1 == h2, "Même input doit donner même hash"
    assert h1 != h3, "Inputs différents doivent donner hashes différents"
    assert len(h1) == 32, "Hash doit faire 32 caractères (truncated SHA256)"


def test_governance_module_importable():
    from src.governance import (
        auto_register_schema,
        get_pii_columns,
        register_data_dictionary_entry,
        register_lineage,
    )

    assert callable(register_data_dictionary_entry)
    assert callable(auto_register_schema)


@pytest.mark.integration
def test_api_module_importable():
    """Le module FastAPI doit s'importer (sans démarrer l'app)."""
    from src.api.main import app

    assert app is not None
    assert app.title == "LyonFlowFull API"


def test_models_importable():
    from src.models import XGBoostSpeedModel, XGBoostVelovModel

    assert XGBoostSpeedModel is not None
    assert XGBoostVelovModel is not None


def test_dag_files_exist():
    """Les DAGs Airflow doivent exister."""
    dags_dir = WORKSPACE / "dags"
    expected = [
        "bronze/collect_bronze.py",
        "transforms/transform_bronze_to_silver.py",
        "transforms/transform_silver_to_gold.py",
        "maintenance/maintenance.py",
        "ml/retrain_xgboost.py",
    ]
    for d in expected:
        path = dags_dir / d
        assert path.exists(), f"DAG manquant: {path}"


@pytest.mark.integration
def test_init_db_sql_exists():
    """Le SQL d'init doit exister et contenir les schémas Medallion.

    Note: init-db.sql est genere via pg_dump (sans IF NOT EXISTS). On
    accepte les 2 formes pour rester robuste a une re-generation depuis
    la prod. Les schemas rgpd/governance sont crees par alembic migration,
    pas par init-db.sql.
    """
    import re

    sql_path = WORKSPACE / "deploy" / "init-db.sql"
    assert sql_path.exists()
    content = sql_path.read_text()
    # Match "CREATE SCHEMA bronze" ou "CREATE SCHEMA IF NOT EXISTS bronze"
    for schema in ("bronze", "silver", "gold"):
        pattern = rf"CREATE SCHEMA(\s+IF NOT EXISTS)?\s+{schema}\b"
        assert re.search(pattern, content), f"Schema {schema} non trouve dans init-db.sql"


@pytest.mark.integration
def test_dockerfile_exists():
    """Le Dockerfile doit exister."""
    dockerfile = WORKSPACE / "Dockerfile"
    assert dockerfile.exists()
    content = dockerfile.read_text()
    assert "FROM python" in content
    assert "USER appuser" in content, "Doit utiliser un user non-root"


@pytest.mark.integration
def test_docker_compose_exists():
    """Le docker-compose doit exister avec tous les services."""
    compose = WORKSPACE / "docker-compose.yml"
    assert compose.exists()
    content = compose.read_text()
    services = ["postgres", "minio", "redis", "mlflow", "airflow-webserver", "api", "streamlit", "nginx"]
    for svc in services:
        assert svc in content, f"Service manquant dans docker-compose: {svc}"


@pytest.mark.integration
def test_nginx_config_exists():
    """Nginx doit être configuré."""
    nginx = WORKSPACE / "nginx" / "nginx.conf"
    assert nginx.exists()
    content = nginx.read_text()
    assert "upstream streamlit_backend" in content
    assert "upstream api_backend" in content
    assert "limit_req_zone" in content, "Rate limiting doit être configuré"
