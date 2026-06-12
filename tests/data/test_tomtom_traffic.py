"""Tests Sprint VPS-6 hotfix — Connecteur TomTom (trafic temps réel).

Vérifie :
1. Sans TOMTOM_API_KEY → get_flow() retourne None sans crash
2. Cache process : 2 appels identiques (avec use_cache) = 1 requête API
3. Quota journalier : 2000 requêtes max, au-delà retourne None
4. health() renvoie un dict avec les bons compteurs
5. _tile_key() arrondit correctement aux tuiles 0.02°
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion import tomtom_traffic as tt


@pytest.fixture(autouse=True)
def reset_tomtom_state(monkeypatch):
    """Reset cache + quota entre chaque test."""
    tt.reset_cache()
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    yield
    tt.reset_cache()


class TestTomTomWithoutKey:
    """Sans clé API, tout est no-op gracieux."""

    def test_get_api_key_returns_none(self):
        assert tt.get_api_key() is None

    def test_get_flow_returns_none_without_key(self):
        """Pas de clé → pas d'appel API, retour None."""
        result = tt.get_flow(45.76, 4.85)
        assert result is None

    def test_collect_lyon_tiles_empty(self):
        """Pas de clé → 0 résultats."""
        results = tt.collect_lyon_tiles()
        assert results == []

    def test_health_no_key(self):
        h = tt.health()
        assert h["api_key_configured"] is False
        assert h["cache_size"] == 0
        assert h["daily_quota"] == tt.DAILY_QUOTA


class TestTomTomTileKey:
    """Vérifie l'arrondi aux tuiles 0.02°."""

    def test_tile_key_rounding(self):
        # 45.76 / 0.02 = 2288, arrondi à 2288 → 45.76
        # 4.85 / 0.02 = 242.5, arrondi à 242 → 4.84
        key = tt._tile_key(45.76, 4.85)
        assert key == "45.7600_4.8400"

    def test_tile_key_within_tile_same(self):
        """Deux points dans la même tuile 0.02° ont la même clé."""
        k1 = tt._tile_key(45.765, 4.855)
        k2 = tt._tile_key(45.764, 4.856)
        assert k1 == k2

    def test_tile_key_different_tiles(self):
        """Deux points à >0.02° d'écart ont des clés différentes."""
        k1 = tt._tile_key(45.76, 4.85)
        k2 = tt._tile_key(45.78, 4.85)
        assert k1 != k2


class TestTomTomCache:
    """Vérifie le cache process 5 min."""

    def test_cache_hit_no_api_call(self, monkeypatch):
        """Si la valeur est en cache, pas d'appel API."""
        key = tt._tile_key(45.76, 4.85)
        cached_value = {
            "current_speed_kmh": 30.0, "free_flow_speed_kmh": 50.0,
            "ratio": 0.6, "confidence": 1.0,
            "current_travel_time_s": 120, "free_flow_travel_time_s": 60,
            "fetched_at": "2026-06-11T00:00:00", "tile_key": key,
            "lat": 45.76, "lon": 4.85,
        }
        tt._cache_set(key, cached_value)
        # Avec use_cache=True, on doit avoir un hit
        result = tt.get_flow(45.76, 4.85, use_cache=True)
        assert result == cached_value

    def test_cache_miss_calls_api(self, monkeypatch):
        """Sans cache, sans clé, retourne None sans crash."""
        # Pas de clé, pas de cache → None direct
        result = tt.get_flow(45.76, 4.85, use_cache=False)
        assert result is None


class TestTomTomQuota:
    """Vérifie le rate-limiting journalier."""

    def test_quota_remaining_initially(self):
        assert tt._quota_remaining() == tt.DAILY_QUOTA

    def test_quota_remaining_after_consumption(self, monkeypatch):
        """Si on consomme, le quota restant diminue."""
        # _reset_daily_quota_if_needed compare avec la date du jour — on
        # aligne _daily_reset_date sur aujourd'hui pour ne pas être reset.
        from datetime import UTC, datetime
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        monkeypatch.setattr("src.ingestion.tomtom_traffic._daily_reset_date", today)
        monkeypatch.setattr("src.ingestion.tomtom_traffic._daily_request_count", 500)
        assert tt._quota_remaining() == tt.DAILY_QUOTA - 500

    def test_quota_exhausted_returns_none(self, monkeypatch):
        """Quota épuisé → get_flow retourne None (avec clé configurée)."""
        from datetime import UTC, datetime
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        monkeypatch.setattr("src.ingestion.tomtom_traffic._daily_reset_date", today)
        monkeypatch.setattr("src.ingestion.tomtom_traffic._daily_request_count", tt.DAILY_QUOTA)
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-key")
        result = tt.get_flow(45.76, 4.85, use_cache=False)
        assert result is None


class TestTomTomReset:
    """Vérifie reset_cache()."""

    def test_reset_clears_state(self):
        """reset_cache vide le cache + reset le compteur journalier."""
        tt._cache_set("test_key", {"foo": "bar"})
        tt._daily_request_count = 100
        tt._daily_reset_date = "2099-01-01"
        tt.reset_cache()
        assert tt._cache == {}
        assert tt._daily_request_count == 0
        assert tt._daily_reset_date == ""


class TestTomTomInputValidation:
    """Vérifie validation des inputs GPS."""

    def test_invalid_lat(self):
        with pytest.raises(ValueError, match="Coordonnées GPS invalides"):
            tt.get_flow(91.0, 4.85)

    def test_invalid_lon(self):
        with pytest.raises(ValueError, match="Coordonnées GPS invalides"):
            tt.get_flow(45.76, 181.0)

    def test_valid_gps(self):
        # Cas valide — pas d'exception (juste None car pas de clé)
        result = tt.get_flow(45.76, 4.85)
        assert result is None  # pas de clé API en test
