"""Tests Wrapper DataCollector TomTomTrafficFlow.

Vérifie que la nouvelle classe ``TomTomTrafficFlow`` (qui wrappe le
module ``src.ingestion.tomtom_traffic``) suit le pattern unifié des
7 autres collecteurs (DataCollector ABC) :
1. Sans TOMTOM_API_KEY → fetch_raw() retourne n_records=0 (no-op gracieux)
2. Avec clé + collect_lyon_tiles() mocked → save_lyon_tiles_to_bronze()
   est appelé avec les bonnes données
3. _save_raw() avec 0 records → skip INSERT Bronze (idempotence )
4. run() expose n_requests/n_failures et last_success_at
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.tomtom_traffic import TomTomTrafficFlow


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Reset cache + clé API entre chaque test."""
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    yield


class TestTomTomTrafficFlowNoKey:
    """Sans clé API : no-op gracieux, 0 records."""

    def test_init_creates_collector(self):
        c = TomTomTrafficFlow()
        assert c.source == "tomtom_traffic_flow"
        assert c.bronze_table == "tomtom_traffic"
        assert c.n_requests == 0
        assert c.n_failures == 0
        assert c.last_success_at is None

    def test_fetch_raw_without_key_returns_empty(self):
        c = TomTomTrafficFlow()
        result = c.fetch_raw()
        assert result.source == "tomtom_traffic_flow"
        assert result.n_records == 0
        assert result.raw_data == []
        assert result.error is None

    def test_run_without_key_marks_failure(self):
        c = TomTomTrafficFlow()
        # run() ne lève pas (warning log), mais n_requests reste 0
        result = c.run()
        # Avec n_records=0, run() return FetchResult avec n_requests=0
        # (car le base.py skip le compteur si validate failed... non, il
        # incrémente même à 0. Voir base.py.run().)
        assert result.n_records == 0
        assert c.n_failures == 0  # pas une erreur, juste no-op


class TestTomTomTrafficFlowWithKey:
    """Avec clé API : fetch → save en bronze."""

    def test_fetch_raw_with_key_calls_collect(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-test-key")
        # Mock collect_lyon_tiles pour éviter l'appel HTTP réel
        fake_results = [
            {
                "lat": 45.76,
                "lon": 4.85,
                "current_speed_kmh": 35.0,
                "free_flow_speed_kmh": 50.0,
                "ratio": 0.7,
                "confidence": 0.95,
                "current_travel_time_s": 120,
                "free_flow_travel_time_s": 80,
                "tile_key": "45.7600_4.8500",
                "fetched_at": "2026-06-18T15:00:00+00:00",
            },
        ]
        with patch("src.ingestion.tomtom_traffic.collect_lyon_tiles", return_value=fake_results):
            c = TomTomTrafficFlow()
            result = c.fetch_raw()
            assert result.n_records == 1
            assert result.raw_data == fake_results

    def test_run_with_key_saves_to_bronze(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-test-key")
        fake_results = [
            {
                "lat": 45.76,
                "lon": 4.85,
                "current_speed_kmh": 35.0,
                "free_flow_speed_kmh": 50.0,
                "ratio": 0.7,
                "confidence": 0.95,
                "current_travel_time_s": 120,
                "free_flow_travel_time_s": 80,
                "tile_key": "45.7600_4.8500",
                "fetched_at": "2026-06-18T15:00:00+00:00",
            },
        ]
        with (
            patch("src.ingestion.tomtom_traffic.collect_lyon_tiles", return_value=fake_results),
            patch("src.ingestion.tomtom_traffic.save_lyon_tiles_to_bronze", return_value=1) as mock_save,
        ):
            c = TomTomTrafficFlow()
            result = c.run()

            # Validate result
            assert result.n_records == 1
            assert result.error is None
            assert c.n_requests == 1
            assert c.n_failures == 0
            assert c.last_success_at is not None

            # Validate save was called
            assert mock_save.called
            assert mock_save.call_args[0][0] == fake_results

    def test_save_raw_with_zero_records_skips(self, monkeypatch):
        """— 0 records → skip INSERT (idempotence)."""
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-test-key")
        with patch("src.ingestion.tomtom_traffic.save_lyon_tiles_to_bronze") as mock_save:
            c = TomTomTrafficFlow()
            # Fetch avec 0 résultats (API indispo ou quota)
            with patch("src.ingestion.tomtom_traffic.collect_lyon_tiles", return_value=[]):
                result = c.run()
                assert result.n_records == 0
                # save_lyon_tiles_to_bronze ne doit PAS être appelé
                assert not mock_save.called

    def test_run_handles_collect_exception(self, monkeypatch):
        """Si collect_lyon_tiles raise, run() attrape et retourne FetchResult avec error."""
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-test-key")
        c = TomTomTrafficFlow()
        with patch("src.ingestion.tomtom_traffic.collect_lyon_tiles", side_effect=RuntimeError("boom")):
            result = c.run()
            assert result.error is not None
            assert "boom" in result.error
            assert c.n_failures == 1
            assert c.last_error is not None


class TestTomTomTrafficFlowImports:
    """Vérifie l'intégration dans src.ingestion.__init__."""

    def test_collector_exported_from_package(self):
        from src.ingestion import TomTomTrafficFlow
        from src.ingestion.tomtom_traffic import TomTomTrafficFlow as DirectClass

        assert TomTomTrafficFlow is DirectClass

    def test_collector_in_realtime_list(self):
        from src.ingestion import REALTIME_COLLECTORS, TomTomTrafficFlow

        assert TomTomTrafficFlow in REALTIME_COLLECTORS

    def test_collector_in_all_classes_list(self):
        from src.ingestion import ALL_COLLECTOR_CLASSES, TomTomTrafficFlow

        assert TomTomTrafficFlow in ALL_COLLECTOR_CLASSES
