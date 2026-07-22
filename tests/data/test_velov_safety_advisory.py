"""Tests — db_query.get_velov_safety_advisory (migration_045, 2026-07-05).

Vérifie que la lecture de gold.v_velov_safety_advisory ne lève jamais et
dégrade proprement vers un statut "unknown" en cas de panne/vide.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import db_query


class TestGetVelovSafetyAdvisory:
    def test_returns_row_when_query_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            db_query,
            "execute_query",
            lambda q, p=(): [
                {
                    "european_aqi": 5,
                    "couleur_canicule": "orange",
                    "status": "severe",
                    "reason": "Pollution très mauvaise (indice européen 5/6)",
                    "aqi_measured_at": None,
                    "vigilance_bulletin_at": None,
                }
            ],
        )
        result = db_query.get_velov_safety_advisory()
        assert result["status"] == "severe"
        assert result["european_aqi"] == 5

    def test_returns_unknown_when_no_rows(self, monkeypatch):
        monkeypatch.setattr(db_query, "execute_query", lambda q, p=(): [])
        result = db_query.get_velov_safety_advisory()
        assert result["status"] == "unknown"
        assert result["european_aqi"] is None

    def test_returns_unknown_when_query_raises(self, monkeypatch):
        def _raise(q, p=()):
            raise RuntimeError("relation gold.v_velov_safety_advisory does not exist")

        monkeypatch.setattr(db_query, "execute_query", _raise)
        result = db_query.get_velov_safety_advisory()
        assert result["status"] == "unknown"
        assert result["reason"] is None
