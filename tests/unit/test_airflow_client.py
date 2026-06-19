"""Tests unitaires — src/data/airflow_client.

Couvre les helpers REST API Airflow. Les appels HTTP sont mockés
(unittest.mock) pour ne pas dépendre d'un Airflow réel.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def _mock_response(status_code: int, json_payload: dict | None = None) -> MagicMock:
    """Construit un mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload or {}
    resp.text = ""
    return resp


def _patch_airflow_available():
    """Helper : patch is_airflow_available() à True pour court-circuiter le health check."""
    return patch("src.data.airflow_client.is_airflow_available", return_value=True)


def test_clear_stuck_dag_run_success():
    """Sprint 15+ (OPERATIONS_FINALES.md étape 0) — clear d'un DAG run
    bloqué doit faire un POST /clearTaskInstances et retourner True
    si HTTP 200/201.
    """
    from src.data import airflow_client

    resp = _mock_response(200, {"task_instances": [{"task_id": "t1"}, {"task_id": "t2"}]})
    with _patch_airflow_available(), patch("src.data.airflow_client.requests.post", return_value=resp) as mock_post:
        ok = airflow_client.clear_stuck_dag_run("maintenance_dag", "run_abc123")

    assert ok is True
    # Vérifier le payload envoyé
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["dag_run_id"] == "run_abc123"
    assert call_kwargs["json"]["reset_dag_runs"] is True
    assert call_kwargs["json"]["dry_run"] is False
    # URL doit finir par /clearTaskInstances
    called_url = mock_post.call_args.args[0]
    assert called_url.endswith("/api/v1/dags/maintenance_dag/clearTaskInstances")


def test_clear_stuck_dag_run_http_error():
    """HTTP 404 / 500 → retourne False (l'opérateur retente depuis Pro_6)."""
    from src.data import airflow_client

    resp = _mock_response(404)
    with _patch_airflow_available(), patch("src.data.airflow_client.requests.post", return_value=resp):
        ok = airflow_client.clear_stuck_dag_run("dag", "run_x")

    assert ok is False


def test_clear_stuck_dag_run_airflow_down():
    """Si Airflow indispo → False immédiat (pas d'appel HTTP)."""
    from src.data import airflow_client

    with (
        patch("src.data.airflow_client.is_airflow_available", return_value=False),
        patch("src.data.airflow_client.requests.post") as mock_post,
    ):
        ok = airflow_client.clear_stuck_dag_run("dag", "run_x")

    assert ok is False
    mock_post.assert_not_called()


def test_mark_dag_run_failed_success():
    """Sprint 15+ — mark failed doit faire un PATCH /dagRuns/{run_id}."""
    from src.data import airflow_client

    resp = _mock_response(200)
    with _patch_airflow_available(), patch("src.data.airflow_client.requests.patch", return_value=resp) as mock_patch:
        ok = airflow_client.mark_dag_run_failed("maintenance_dag", "run_abc123")

    assert ok is True
    call_kwargs = mock_patch.call_args.kwargs
    assert call_kwargs["json"] == {"state": "failed"}
    called_url = mock_patch.call_args.args[0]
    assert called_url.endswith("/api/v1/dags/maintenance_dag/dagRuns/run_abc123")


def test_mark_dag_run_failed_http_error():
    """HTTP != 200 → False."""
    from src.data import airflow_client

    resp = _mock_response(500)
    with _patch_airflow_available(), patch("src.data.airflow_client.requests.patch", return_value=resp):
        ok = airflow_client.mark_dag_run_failed("dag", "run_x")

    assert ok is False


def test_mark_dag_run_failed_airflow_down():
    """Si Airflow indispo → False immédiat (pas d'appel HTTP)."""
    from src.data import airflow_client

    with (
        patch("src.data.airflow_client.is_airflow_available", return_value=False),
        patch("src.data.airflow_client.requests.patch") as mock_patch,
    ):
        ok = airflow_client.mark_dag_run_failed("dag", "run_x")

    assert ok is False
    mock_patch.assert_not_called()


def test_get_dags_status_includes_last_dag_run_id():
    """Le dict enrichi doit contenir ``last_dag_run_id`` pour que les
    boutons Clear/Fail dans pipeline_management.py aient l'info.
    """
    from src.data import airflow_client

    # Mock la liste de DAGs + leur dernier run
    dags_payload = {
        "dags": [
            {
                "dag_id": "test_dag",
                "schedule_interval": {"value": "@daily"},
                "next_dagrun": "2026-06-20T03:00:00Z",
                "description": "Test",
                "is_paused": False,
            }
        ]
    }
    runs_payload = {
        "dag_runs": [
            {
                "dag_run_id": "scheduled__2026-06-19_03-00-00",
                "state": "running",
                "execution_date": "2026-06-19T03:00:00Z",
                "start_date": "2026-06-19T03:00:01Z",
                "end_date": None,
            }
        ]
    }

    def fake_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/dags?limit=" in url:
            resp.json.return_value = dags_payload
        elif "/dagRuns" in url:
            resp.json.return_value = runs_payload
        else:
            resp.json.return_value = {}
        return resp

    with _patch_airflow_available(), patch("src.data.airflow_client.requests.get", side_effect=fake_get):
        dags = airflow_client.get_dags_status()

    assert len(dags) == 1
    assert dags[0]["dag_id"] == "test_dag"
    # LE FIX : cette clé doit exister (sinon les boutons Clear/Fail ne
    # peuvent pas être affichés)
    assert "last_dag_run_id" in dags[0]
    assert dags[0]["last_dag_run_id"] == "scheduled__2026-06-19_03-00-00"
    assert dags[0]["last_status"] == "running"
