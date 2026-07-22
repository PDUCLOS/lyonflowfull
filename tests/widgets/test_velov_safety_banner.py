"""Tests unitaires — dashboard/components/velov_safety_banner.py (migration_045).

Couvre :
* get_velov_safety_severity() : mapping status -> severity (0/1/2).
* Ne lève jamais, même si la source retourne "unknown".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components import velov_safety_banner


class TestGetVelovSafetySeverity:
    def test_status_ok_returns_severity_0(self, monkeypatch):
        monkeypatch.setattr(
            velov_safety_banner,
            "cached_velov_safety_advisory",
            lambda: {"status": "ok", "reason": None},
        )
        severity, advisory = velov_safety_banner.get_velov_safety_severity()
        assert severity == 0
        assert advisory["status"] == "ok"

    def test_status_unknown_returns_severity_0(self, monkeypatch):
        """'unknown' est neutre (pas de donnée) — jamais traité comme un risque."""
        monkeypatch.setattr(
            velov_safety_banner,
            "cached_velov_safety_advisory",
            lambda: {"status": "unknown", "reason": None},
        )
        severity, _ = velov_safety_banner.get_velov_safety_severity()
        assert severity == 0

    def test_status_warning_returns_severity_1(self, monkeypatch):
        monkeypatch.setattr(
            velov_safety_banner,
            "cached_velov_safety_advisory",
            lambda: {"status": "warning", "reason": "Pollution dégradée (indice européen 4/6)"},
        )
        severity, advisory = velov_safety_banner.get_velov_safety_severity()
        assert severity == 1
        assert "Pollution" in advisory["reason"]

    def test_status_severe_returns_severity_2(self, monkeypatch):
        monkeypatch.setattr(
            velov_safety_banner,
            "cached_velov_safety_advisory",
            lambda: {"status": "severe", "reason": "Vigilance canicule rouge (Rhône)"},
        )
        severity, _ = velov_safety_banner.get_velov_safety_severity()
        assert severity == 2

    def test_unrecognized_status_defaults_to_0(self, monkeypatch):
        monkeypatch.setattr(
            velov_safety_banner,
            "cached_velov_safety_advisory",
            lambda: {"status": "something_new", "reason": None},
        )
        severity, _ = velov_safety_banner.get_velov_safety_severity()
        assert severity == 0
