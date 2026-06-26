"""Client Airflow REST API — Récupère l'état des DAGs, des exécutions et permet les déclenchements manuels.

La philosophie de ce client est d'échouer de manière explicite ("fail loud") en production :

* Si Airflow est indisponible, le client lève une exception ``DashboardDataError``. 
  Le widget appelant intercepte cette exception et affiche une alerte via ``st.error``.
* Aucun mécanisme de repli (fallback mock) n'est autorisé.

Exemple d'utilisation :
    ```python
    from src.data.airflow_client import get_dags_status
    dags = get_dags_status()  # Liste de dictionnaires compatible avec les widgets Streamlit
    ```

Variables d'environnement requises :
- AIRFLOW_HOST (défaut : localhost)
- AIRFLOW_PORT (défaut : 8080)
- AIRFLOW_ADMIN_USERNAME (défaut : admin)
- AIRFLOW_ADMIN_PASSWORD (défaut : vide -> déclenche une erreur en production)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.data.exceptions import DashboardDataError

logger = logging.getLogger(__name__)

_HEALTH_CACHE: bool | None = None


def _airflow_base_url() -> str:
    host = os.getenv("AIRFLOW_HOST", "localhost")
    port = os.getenv("AIRFLOW_PORT", "8080")

    # En production, Airflow est exposé derrière Nginx avec le préfixe /airflow
    # (cf. AIRFLOW__WEBSERVER__BASE_URL + nginx.conf).
    # Sans ce préfixe, les endpoints /health et /api/v1/* retournent une erreur 404.
    # Pour un développement local direct, il faut surcharger AIRFLOW_BASE_PATH="" dans le .env.
    base_path = os.getenv("AIRFLOW_BASE_PATH", "/airflow")
    return f"http://{host}:{port}{base_path}"


def _airflow_auth() -> tuple[str, str] | None:
    user = os.getenv("AIRFLOW_ADMIN_USERNAME", "admin")
    pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
    if not pwd:
        return None
    return (user, pwd)


def is_airflow_available() -> bool:
    """Vérifie la disponibilité de l'API Airflow via l'endpoint /health avec mise en cache par processus."""
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
        logger.debug("Échec de la vérification de santé d'Airflow : %s", exc)
        _HEALTH_CACHE = False
    return _HEALTH_CACHE


def reset_health_cache() -> None:
    """Réinitialise le cache de disponibilité (utile pour les tests ou les rafraîchissements manuels)."""
    global _HEALTH_CACHE
    _HEALTH_CACHE = None


def get_dags_status() -> list[dict[str, Any]]:
    """Récupère la liste des DAGs ainsi que l'état de leur dernière exécution.

    Cette fonction est optimisée pour alimenter le composant de gestion des pipelines.

    Returns:
        Une liste de dictionnaires contenant :
        `dag_id`, `schedule`, `last_run`, `last_status`, `last_duration_s`, 
        `next_run`, `description`, `paused`, `last_dag_run_id`.

    Raises:
        DashboardDataError: Si l'API Airflow est injoignable ou si la requête échoue.
    """
    if not is_airflow_available():
        raise DashboardDataError(
            source="airflow",
            detail=(
                f"L'API REST d'Airflow est injoignable ({_airflow_base_url()}/health). "
                "Vérifiez que le service est actif et que les identifiants dans le .env sont corrects."
            ),
        )

    try:
        return _fetch_dags_from_airflow()
    except Exception as exc:
        raise DashboardDataError(
            source="airflow",
            detail=f"La requête vers l'API REST d'Airflow a échoué : {exc}",
        ) from exc


def _fetch_dags_from_airflow() -> list[dict[str, Any]]:
    """Logique interne effectuant l'appel HTTP réel vers l'API Airflow."""
    base = _airflow_base_url()
    auth = _airflow_auth()
    timeout = float(os.getenv("AIRFLOW_API_TIMEOUT", "3"))

    r = requests.get(f"{base}/api/v1/dags?limit=100", auth=auth, timeout=timeout)
    r.raise_for_status()
    dags = r.json().get("dags", [])

    enriched: list[dict[str, Any]] = []
    for d in dags:
        dag_id = d["dag_id"]
        # Récupération de la dernière exécution pour chaque DAG
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
                "last_dag_run_id": last.get("dag_run_id") or "",
            }
        )
    return enriched


def trigger_dag(dag_id: str) -> bool:
    """Déclenche manuellement une nouvelle exécution d'un DAG.
    
    Args:
        dag_id: L'identifiant du DAG à lancer.
        
    Returns:
        True si la requête POST a réussi (statut 200/201), False sinon.
    """
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
        logger.warning("Échec du déclenchement du DAG (%s) : %s", dag_id, exc)
        return False


def clear_stuck_dag_run(dag_id: str, dag_run_id: str) -> bool:
    """Nettoie les instances de tâches bloquées d'une exécution de DAG.

    Marque toutes les instances de tâches (Task Instances) de l'exécution comme "cleared".
    Airflow les reprogrammera automatiquement. Particulièrement utile pour débloquer
    une exécution coincée dans l'état "running".
    """
    if not is_airflow_available():
        return False
    base = _airflow_base_url()
    auth = _airflow_auth()
    try:
        r = requests.post(
            f"{base}/api/v1/dags/{dag_id}/clearTaskInstances",
            json={
                "dry_run": False,
                "dag_run_id": dag_run_id,
                "reset_dag_runs": True,
                "only_failed": False,
            },
            auth=auth,
            timeout=10,
        )
        ok = r.status_code in (200, 201)
        if ok:
            logger.info(
                "clear_stuck_dag_run(%s, %s): %d tâches nettoyées",
                dag_id,
                dag_run_id,
                len(r.json().get("task_instances", [])),
            )
        else:
            logger.warning("clear_stuck_dag_run(%s, %s): Code HTTP %d — %s", dag_id, dag_run_id, r.status_code, r.text[:200])
        return ok
    except Exception as exc:
        logger.warning("Échec du nettoyage des tâches pour le DAG (%s, %s) : %s", dag_id, dag_run_id, exc)
        return False


def mark_dag_run_failed(dag_id: str, dag_run_id: str) -> bool:
    """Force l'état d'une exécution de DAG bloquée à "failed"."""
    if not is_airflow_available():
        return False
    base = _airflow_base_url()
    auth = _airflow_auth()
    try:
        r = requests.patch(
            f"{base}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}",
            json={"state": "failed"},
            auth=auth,
            timeout=5,
        )
        ok = r.status_code == 200
        if ok:
            logger.info("mark_dag_run_failed(%s, %s) : Succès", dag_id, dag_run_id)
        else:
            logger.warning("mark_dag_run_failed(%s, %s) : Code HTTP %d", dag_id, dag_run_id, r.status_code)
        return ok
    except Exception as exc:
        logger.warning("Échec de la mise en échec forcée pour le DAG (%s, %s) : %s", dag_id, dag_run_id, exc)
        return False
