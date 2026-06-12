"""Client Airflow REST API — recupere DAGs + dagRuns + trigger.

Sprint VPS-6 (2026-06-11) — fail loud en prod :

* Mode prod (``LYONFLOW_DEMO_MODE!=1``) : Airflow indispo →
  ``DashboardDataError``. Le widget appelant catch et affiche ``st.error``.
* Mode démo (``LYONFLOW_DEMO_MODE=1``) : fallback ``MOCK_DAGS`` préservé
  (dev local sans Airflow).

Usage::

    from src.data.airflow_client import get_dags_status
    dags = get_dags_status()  # liste dicts compatible widgets
    # En prod : lève DashboardDataError si Airflow indispo

Variables env requises:
- AIRFLOW_HOST (default: localhost)
- AIRFLOW_PORT (default: 8080)
- AIRFLOW_ADMIN_USERNAME (default: admin)
- AIRFLOW_ADMIN_PASSWORD (default: vide -> bascule mock en démo, erreur en prod)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError

logger = logging.getLogger(__name__)

_HEALTH_CACHE: bool | None = None


def _airflow_base_url() -> str:
    host = os.getenv("AIRFLOW_HOST", "localhost")
    port = os.getenv("AIRFLOW_PORT", "8080")
    return f"http://{host}:{port}"


def _airflow_auth() -> tuple[str, str] | None:
    user = os.getenv("AIRFLOW_ADMIN_USERNAME", "admin")
    pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
    if not pwd:
        return None
    return (user, pwd)


def is_airflow_available() -> bool:
    """Ping Airflow /health avec cache process."""
    global _HEALTH_CACHE
    if _HEALTH_CACHE is not None:
        return _HEALTH_CACHE
    auth = _airflow_auth()
    if auth is None:
        _HEALTH_CACHE = False
        return False
    try:
        r = requests.get(f"{_airflow_base_url()}/health", timeout=2)
        _HEALTH_CACHE = r.status_code == 200
    except Exception as exc:
        logger.debug("Airflow health check failed: %s", exc)
        _HEALTH_CACHE = False
    return _HEALTH_CACHE


def reset_health_cache() -> None:
    """Reset cache (utile pour tests + bouton refresh)."""
    global _HEALTH_CACHE
    _HEALTH_CACHE = None


def get_dags_status() -> list[dict[str, Any]]:
    """Liste des DAGs + dernier run (compatible widget pipeline_management).

    Returns:
        Liste de dicts avec les clefs:
        dag_id, schedule, last_run, last_status, last_duration_s, next_run,
        description, paused.

    Raises:
        DashboardDataError: en mode prod, si Airflow indispo (health=False)
            ou si la requête REST échoue.
    """
    if not is_airflow_available():
        # Sprint 8 — viré le fallback mock. Toujours DashboardDataError.
        raise DashboardDataError(
            source="airflow",
            detail=(
                f"Airflow REST API non joignable ({_airflow_base_url()}/health). "
                "Vérifier que le service tourne et que AIRFLOW_HOST/AIRFLOW_ADMIN_PASSWORD "
                "sont corrects dans .env"
            ),
        )

    try:
        return _fetch_dags_from_airflow()
    except Exception as exc:
        # Sprint 8 — viré le fallback mock. Toujours DashboardDataError.
        raise DashboardDataError(
            source="airflow",
            detail=f"Airflow REST API a échoué : {exc}",
        ) from exc


def _fetch_dags_from_airflow() -> list[dict[str, Any]]:
    """Appel reel Airflow REST API."""
    base = _airflow_base_url()
    auth = _airflow_auth()
    timeout = float(os.getenv("AIRFLOW_API_TIMEOUT", "3"))

    r = requests.get(f"{base}/api/v1/dags?limit=100", auth=auth, timeout=timeout)
    r.raise_for_status()
    dags = r.json().get("dags", [])

    enriched: list[dict[str, Any]] = []
    for d in dags:
        dag_id = d["dag_id"]
        # Recupere le dernier run pour ce DAG
        try:
            rr = requests.get(
                f"{base}/api/v1/dags/{dag_id}/dagRuns?limit=1&order_by=-execution_date",
                auth=auth,
                timeout=timeout,
            )
            rr.raise_for_status()
            runs = rr.json().get("dag_runs", [])
            last = runs[0] if runs else {}
        except Exception:
            last = {}

        last_status = last.get("state", "unknown")
        if last_status == "queued":
            last_status = "running"

        last_start = last.get("start_date")
        last_end = last.get("end_date")
        last_duration_s: int | None = None
        if last_start and last_end:
            try:
                from datetime import datetime

                dt_start = datetime.fromisoformat(last_start.replace("Z", "+00:00"))
                dt_end = datetime.fromisoformat(last_end.replace("Z", "+00:00"))
                last_duration_s = int((dt_end - dt_start).total_seconds())
            except Exception:
                last_duration_s = None

        enriched.append(
            {
                "dag_id": dag_id,
                "schedule": d.get("schedule_interval", {}).get("value", "—")
                if isinstance(d.get("schedule_interval"), dict)
                else str(d.get("schedule_interval") or "—"),
                "last_run": last.get("execution_date") or "—",
                "last_status": last_status,
                "last_duration_s": last_duration_s or 0,
                "next_run": d.get("next_dagrun") or "—",
                "description": d.get("description") or "",
                "paused": d.get("is_paused", False),
            }
        )
    return enriched


def trigger_dag(dag_id: str) -> bool:
    """Declenche un run manuel pour le DAG (POST /api/v1/dags/{dag_id}/dagRuns)."""
    if not is_airflow_available():
        return False
    base = _airflow_base_url()
    auth = _airflow_auth()
    try:
        r = requests.post(
            f"{base}/api/v1/dags/{dag_id}/dagRuns",
            json={"conf": {}},
            auth=auth,
            timeout=5,
        )
        return r.status_code in (200, 201)
    except Exception as exc:
        logger.warning("trigger_dag(%s) failed: %s", dag_id, exc)
        return False
