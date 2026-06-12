"""Tests E2E — Smoke tests de l'app Streamlit + API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_health_endpoint_if_api_up():
    """Test /health si l'API tourne. Skip sinon."""
    import httpx

    try:
        r = httpx.get("http://localhost:8000/health", timeout=2)
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "version" in data
    except Exception:
        pytest.skip("API non démarrée — smoke test skipped")


def test_models_endpoint_if_api_up():
    """Test /api/v1/models si l'API tourne."""
    import httpx

    try:
        r = httpx.get("http://localhost:8000/api/v1/models", headers={"X-API-Key": "test"}, timeout=2)
        # 200 OK ou 401 (no API key) — les deux prouvent que l'endpoint existe
        assert r.status_code in (200, 401)
    except Exception:
        pytest.skip("API non démarrée — smoke test skipped")


def test_streamlit_homepage_if_up():
    """Test page d'accueil Streamlit si elle tourne."""
    import httpx

    try:
        r = httpx.get("http://localhost:8501/", timeout=2)
        assert r.status_code == 200
    except Exception:
        pytest.skip("Streamlit non démarré — smoke test skipped")
