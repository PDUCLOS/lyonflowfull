"""Tests — Collecteur VigilanceMeteo (migration_045, 2026-07-05).

Vérifie :
1. fetch_raw() parse correctement la réponse Opendatasoft (records/fields).
2. validate() refuse 0 enregistrement (signal d'un problème API).
3. _save_raw() insère une ligne par période horaire, ON CONFLICT DO NOTHING.
4. Intégration dans src.ingestion (export + REALTIME_COLLECTORS).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.base import FetchResult
from src.ingestion.vigilance_meteo import VigilanceMeteo

FAKE_API_RESPONSE = {
    "nhits": 2,
    "records": [
        {
            "fields": {
                "domain_id": "69",
                "phenomenon": "canicule",
                "color": "vert",
                "echeance": "J",
                "begin_time": "2026-07-05T04:00:00+00:00",
                "end_time": "2026-07-05T10:00:00+00:00",
                "product_datetime": "2026-07-05T04:00:00+00:00",
            }
        },
        {
            "fields": {
                "domain_id": "69",
                "phenomenon": "canicule",
                "color": "orange",
                "echeance": "J",
                "begin_time": "2026-07-05T10:00:00+00:00",
                "end_time": "2026-07-05T22:00:00+00:00",
                "product_datetime": "2026-07-05T04:00:00+00:00",
            }
        },
    ],
}


class TestVigilanceMeteoFetch:
    def test_init_creates_collector(self):
        c = VigilanceMeteo()
        assert c.source == "vigilance_meteo"
        assert c.bronze_table == "vigilance_meteo"
        assert c.departement == "69"

    def test_fetch_raw_parses_records(self):
        c = VigilanceMeteo()
        fake_response = MagicMock()
        fake_response.json.return_value = FAKE_API_RESPONSE
        fake_response.content = b"{}"
        fake_response.status_code = 200

        with patch.object(c, "_http_get", return_value=fake_response) as mock_get:
            result = c.fetch_raw()

        assert result.n_records == 2
        assert result.raw_data == FAKE_API_RESPONSE
        # Vérifie que les bons paramètres de filtre ont été envoyés
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["refine.domain_id"] == "69"
        assert kwargs["params"]["refine.phenomenon"] == "canicule"
        assert kwargs["params"]["refine.echeance"] == "J"

    def test_fetch_raw_empty_response(self):
        c = VigilanceMeteo()
        fake_response = MagicMock()
        fake_response.json.return_value = {"nhits": 0, "records": []}
        fake_response.content = b"{}"
        fake_response.status_code = 200

        with patch.object(c, "_http_get", return_value=fake_response):
            result = c.fetch_raw()

        assert result.n_records == 0

    def test_fetch_raw_http_error_raises_collector_error(self):
        from src.ingestion.base import CollectorError

        c = VigilanceMeteo()
        with patch.object(c, "_http_get", side_effect=RuntimeError("timeout")), pytest.raises(CollectorError):
            c.fetch_raw()


class TestVigilanceMeteoValidate:
    def test_validate_rejects_zero_records(self):
        c = VigilanceMeteo()
        result = FetchResult(source="vigilance_meteo", fetched_at=None, raw_data={}, n_records=0)
        assert c.validate(result) is False

    def test_validate_accepts_nonzero_records(self):
        c = VigilanceMeteo()
        result = FetchResult(source="vigilance_meteo", fetched_at=None, raw_data={}, n_records=2)
        assert c.validate(result) is True


class TestVigilanceMeteoSaveRaw:
    def test_save_raw_inserts_one_row_per_period(self, monkeypatch):
        import datetime as _dt

        c = VigilanceMeteo()
        result = FetchResult(
            source="vigilance_meteo",
            fetched_at=_dt.datetime(2026, 7, 5, 6, 15, tzinfo=_dt.UTC),
            raw_data=FAKE_API_RESPONSE,
            n_records=2,
        )

        with patch("src.ingestion.vigilance_meteo.execute_query") as mock_exec:
            c._save_raw(result)

        assert mock_exec.call_count == 2
        first_call_params = mock_exec.call_args_list[0][0][1]
        assert first_call_params[1] == "69"  # departement
        assert first_call_params[2] == "vert"  # couleur_canicule

    def test_save_raw_skips_on_error(self):
        import datetime as _dt

        c = VigilanceMeteo()
        result = FetchResult(
            source="vigilance_meteo",
            fetched_at=_dt.datetime(2026, 7, 5, 6, 15, tzinfo=_dt.UTC),
            raw_data=None,
            n_records=0,
            error="boom",
        )
        with patch("src.ingestion.vigilance_meteo.execute_query") as mock_exec:
            c._save_raw(result)
        assert not mock_exec.called


class TestVigilanceMeteoImports:
    def test_collector_exported_from_package(self):
        from src.ingestion import VigilanceMeteo as PackageClass
        from src.ingestion.vigilance_meteo import VigilanceMeteo as DirectClass

        assert PackageClass is DirectClass

    def test_collector_in_realtime_list(self):
        from src.ingestion import REALTIME_COLLECTORS, VigilanceMeteo

        assert VigilanceMeteo in REALTIME_COLLECTORS

    def test_collector_in_all_classes_list(self):
        from src.ingestion import ALL_COLLECTOR_CLASSES, VigilanceMeteo

        assert VigilanceMeteo in ALL_COLLECTOR_CLASSES
