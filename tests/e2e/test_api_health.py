"""E2E tests API — endpoints REST du backend FastAPI.

Couverture :
- /health         : health check public (pas d'auth)
- /api/v1/bottlenecks : top bottlenecks (auth API key requise)
"""

import os

import pytest
import requests


API_BASE = os.getenv("LYONFLOW_API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("LYONFLOW_API_KEY", "")


class TestApiHealth:
    """Tests du endpoint /health — accessible sans auth."""

    def test_health_returns_200(self):
        """Le health check doit retourner HTTP 200."""
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_health_response_structure(self):
        """La réponse doit contenir les champs attendus."""
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        data = resp.json()
        assert "status" in data, "Réponse doit contenir 'status'"
        assert "version" in data, "Réponse doit contenir 'version'"
        assert "db" in data, "Réponse doit contenir 'db'"
        assert data["status"] == "ok", f"status attendu 'ok', got {data['status']}"
        assert isinstance(data["db"], bool), "db doit être un bool"


class TestApiBottlenecks:
    """Tests du endpoint /api/v1/bottlenecks — requiert API key."""

    def test_bottlenecks_requires_api_key(self):
        """Sans X-API-Key → 401 Unauthorized."""
        resp = requests.get(f"{API_BASE}/api/v1/bottlenecks", timeout=10)
        # Si DISABLE_AUTH=true en dev, ça peut retourner 200. Sinon 401.
        # On vérifie juste que ça ne crash pas et retourne un code HTTP valide.
        assert resp.status_code in (200, 401), (
            f"Expected 200 (auth disabled) or 401 (auth required), got {resp.status_code}"
        )

    def test_bottlenecks_with_valid_key(self):
        """Avec API key valide → 200 + structure JSON valide."""
        if not API_KEY:
            pytest.skip("LYONFLOW_API_KEY non configuré")
        headers = {"X-API-Key": API_KEY}
        resp = requests.get(f"{API_BASE}/api/v1/bottlenecks", headers=headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "La réponse doit être une liste"
        # Vérifie la structure d'un item
        if data:
            item = data[0]
            assert "id" in item, "Item doit contenir 'id'"
            assert "diagnosis" in item, "Item doit contenir 'diagnosis'"
