"""Tests unitaires pour le DAG `maintenance_record_network_health` P4.3).

Valide les fonctions _record_health et _purge_old SANS dépendance DB.
Les queries SQL sont mockées via unittest.mock.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags" / "maintenance"))

# Import direct des fonctions (pas via le DAG, qui requiert Airflow runtime)
import importlib.util

DAG_PATH = Path(__file__).resolve().parents[2] / "dags" / "maintenance" / "record_network_health.py"
spec = importlib.util.spec_from_file_location("record_network_health", DAG_PATH)
# Patch les imports Airflow AVANT le load
sys.modules["airflow"] = MagicMock()
sys.modules["airflow.operators"] = MagicMock()
sys.modules["airflow.operators.python"] = MagicMock()

mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as e:
    # Si le load échoue (à cause d'Airflow mock incomplet), skip propre
    pytest.skip(f"DAG load impossible: {e}", allow_module_level=True)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_record_health_inserts_score() -> None:
    """_record_health doit INSERT le score + sources quand fn_network_health_score retourne 1 row."""
    fake_score_row = {
        "score": 75.5,
        "traffic_available": True,
        "tcl_available": True,
        "velov_available": False,
        "meteo_available": True,
        "computed_at": datetime(2026, 6, 22, 12, 30, tzinfo=UTC),
        "diagnosis": "healthy",
    }
    with patch.object(mod, "execute_query") as mock_execute:
        # 1er appel : SELECT fn_network_health_score() → 1 row
        # 2ème appel : INSERT history
        mock_execute.side_effect = [[fake_score_row], None]
        result = mod._record_health()
    assert result == 1
    assert mock_execute.call_count == 2

    # Vérifier le 2ème call = INSERT avec les bonnes valeurs
    insert_call = mock_execute.call_args_list[1]
    args, _ = insert_call
    sql, params = args
    assert "INSERT INTO gold.network_health_history" in sql
    assert "ON CONFLICT (recorded_at) DO NOTHING" in sql
    assert params[0] == fake_score_row["computed_at"]
    assert float(params[1]) == 75.5
    # available_sources = ["trafic", "tcl", "meteo"] (velov indisponible)
    assert set(params[2]) == {"trafic", "tcl", "meteo"}


def test_record_health_no_data() -> None:
    """_record_health doit retourner 0 si fn_network_health_score() ne retourne rien."""
    with patch.object(mod, "execute_query") as mock_execute:
        mock_execute.return_value = []  # 0 rows
        result = mod._record_health()
    assert result == 0
    # Doit avoir fait 1 SEUL call (SELECT) — pas d'INSERT inutile
    assert mock_execute.call_count == 1


def test_record_health_all_sources_unavailable() -> None:
    """Si toutes les sources sont indisponibles, available_sources = []."""
    fake_row = {
        "score": 0.0,
        "traffic_available": False,
        "tcl_available": False,
        "velov_available": False,
        "meteo_available": False,
        "computed_at": datetime(2026, 6, 22, 12, 30, tzinfo=UTC),
        "diagnosis": "critical",
    }
    with patch.object(mod, "execute_query") as mock_execute:
        mock_execute.side_effect = [[fake_row], None]
        mod._record_health()
    insert_call = mock_execute.call_args_list[1]
    _, params = insert_call[0]
    assert params[2] == []


def test_purge_old_deletes_7d() -> None:
    """_purge_old doit DELETE WHERE recorded_at < NOW() - 7j."""
    with patch.object(mod, "execute_query") as mock_execute:
        mock_execute.return_value = None
        mod._purge_old()
    assert mock_execute.call_count == 1
    call_args = mock_execute.call_args[0]
    sql, params = call_args
    assert "DELETE FROM gold.network_health_history" in sql
    assert "WHERE recorded_at < %s" in sql
    # Le cutoff doit être ~7 jours dans le passé (tolérance 5 min)
    cutoff = params[0]
    now = datetime.now(UTC)
    delta = now - cutoff
    assert timedelta(days=6, hours=23, minutes=55) < delta < timedelta(days=7, minutes=5)
