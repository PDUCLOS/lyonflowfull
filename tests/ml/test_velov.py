"""Tests pour velov.py (VelovCollector) — Sprint 9 refacto.

Couvre :
* Import du module sans erreur
* Classe instanciable
* logger defini au niveau module (pas dans except)
* Les URLs sont overridables via env vars
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.velov import VelovCollector


class TestVelovCollectorImports:
    def test_module_imports_without_error(self):
        assert True

    def test_velov_collector_class_exists(self):
        assert VelovCollector is not None


class TestVelovCollectorInstantiation:
    def test_instantiation_default(self):
        collector = VelovCollector()
        assert collector.source == "velov_gbfs"
        assert collector.bronze_table == "velov"
        assert collector.timeout == 30

    def test_default_urls_set(self):
        collector = VelovCollector()
        assert "station_status.json" in collector.station_status_url
        assert "station_information.json" in collector.station_information_url


class TestVelovCollectorLogger:
    def test_logger_defined_at_module_level(self):
        """logger est defini au niveau module, pas dans un bloc except."""
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "ingestion" / "velov.py"
        tree = ast.parse(src.read_text())
        # Cherche logging.getLogger(__name__) au niveau module
        found_logger_assign = False
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "logger":
                        found_logger_assign = True
        assert found_logger_assign, (
            "velov.py: 'logger' doit être defini au niveau module "
            "(import logging + logger = logging.getLogger(__name__))"
        )

    def test_no_import_inside_except_block(self):
        """Il n'y a pas d'import statement dans un bloc except."""
        import ast

        src = Path(__file__).resolve().parents[2] / "src" / "ingestion" / "velov.py"
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    for child in ast.walk(handler):
                        if isinstance(child, ast.Import):
                            pytest.fail(
                                f"Import inside except block at line {child.lineno}: "
                                f"'{ast.unparse(child)}' — move to top-level imports"
                            )
                        if isinstance(child, ast.ImportFrom):
                            pytest.fail(
                                f"ImportFrom inside except block at line {child.lineno}: "
                                f"'{ast.unparse(child)}' — move to top-level imports"
                            )


class TestVelovCollectorEnvVars:
    def test_urls_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("VELOV_STATION_STATUS_URL", "http://custom/status.json")
        monkeypatch.setenv("VELOV_STATION_INFORMATION_URL", "http://custom/info.json")
        collector = VelovCollector()
        assert collector.station_status_url == "http://custom/status.json"
        assert collector.station_information_url == "http://custom/info.json"


class TestVelovCollectorFetchRaw:
    def test_fetch_raw_returns_fetch_result(self):
        """fetch_raw() retourne un FetchResult bien forme."""
        collector = VelovCollector()
        with patch.object(collector, "_http_get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"{}"
            mock_response.json.return_value = {"data": {"stations": []}}
            mock_get.return_value = mock_response

            result = collector.fetch_raw()
            assert result.source == "velov_gbfs"
            assert "status" in result.raw_data
            assert "information" in result.raw_data
            assert isinstance(result.fetched_at.year, int)
            assert result.status_code == 200

    def test_fetch_raw_graceful_when_information_fails(self):
        """Si station_information echoue, le fetch continue avec information=[]."""
        collector = VelovCollector()
        call_count = [0]

        def http_get_side_effect(url, **kwargs):
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"{}"
            if "information" in url:
                raise Exception("API unavailable")
            mock_resp.json.return_value = {"data": {"stations": [{"station_id": "s1"}]}}
            return mock_resp

        with patch.object(collector, "_http_get", side_effect=http_get_side_effect):
            result = collector.fetch_raw()
            assert result.raw_data["information"] == []
            assert result.raw_data["status"][0]["station_id"] == "s1"
