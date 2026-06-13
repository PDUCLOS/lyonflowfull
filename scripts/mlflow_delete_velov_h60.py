"""Script de suppression du modèle Vélov H+1h dans le MLflow Registry.

Sprint 12+ — Patrice : "tout en H+30min pour Vélov".
Le modèle xgb_velov_h60 n'est plus entraîné (DAG `retrain_xgboost_velov`
boucle uniquement sur `[30]`) mais reste dans MLflow Registry en stage
"Production". Ce script le marque en "Archived" (transition officielle)
et tente le delete des artifacts si l'API le permet.

Usage (sur le VPS, dans un container ou avec le réseau Docker) :

    docker compose exec airflow-worker python scripts/mlflow_delete_velov_h60.py

Pré-requis :
- Variables d'env MLFLOW_TRACKING_URI=http://mlflow:5000
- Compte de service MLflow (ou Basic auth Nginx en amont)

Politique Sprint 8+ — pas d'opération silencieuse. Si MLflow ne répond
pas, on lève une RuntimeError avec contexte (pas un fallback silencieux).
"""

from __future__ import annotations

import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MODEL_NAME = "xgb_velov_h60"
STAGE_OLD = "Production"
STAGE_NEW = "Archived"

# Si l'utilisateur a un mot de passe Basic Auth pour Nginx → MLflow,
# les passer via env. Sinon, accès anonyme (suffit si l'API MLflow est ouverte).
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
BASIC_AUTH_USER = os.getenv("MLFLOW_BASIC_AUTH_USER", "")
BASIC_AUTH_PASSWORD = os.getenv("MLFLOW_BASIC_AUTH_PASSWORD", "")

auth = (BASIC_AUTH_USER, BASIC_AUTH_PASSWORD) if BASIC_AUTH_USER else None


def _check_reachable() -> None:
    """Vérifie que le serveur MLflow répond. Lève RuntimeError sinon."""
    health_url = f"{MLFLOW_TRACKING_URI}/health"
    try:
        r = requests.get(health_url, auth=auth, timeout=5)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"MLflow tracking server injoignable à {MLFLOW_TRACKING_URI} — "
            f"vérifier MLFLOW_TRACKING_URI, ports Docker, Nginx Basic auth. "
            f"Erreur: {e}"
        ) from e


def _list_versions(model_name: str) -> list[dict]:
    """Liste les versions d'un modèle dans le Registry."""
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/registered-models/get-latest-versions"
    r = requests.get(
        url,
        params={"name": model_name},
        auth=auth,
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("registered_models", [])


def _transition_stage(model_name: str, version: int, stage_new: str) -> None:
    """Transitionne un modèle vers un stage (Production, Staging, Archived, None)."""
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/registered-models/transition-versions-stage"
    r = requests.post(
        url,
        json={
            "name": model_name,
            "version": str(version),
            "stage": stage_new,
        },
        auth=auth,
        timeout=10,
    )
    r.raise_for_status()
    logger.info("Transition OK : %s v%s → %s", model_name, version, stage_new)


def _delete_model_version(model_name: str, version: int) -> None:
    """Supprime une version spécifique du Registry (irréversible)."""
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/registered-models/delete-version"
    r = requests.delete(
        url,
        params={"name": model_name, "version": str(version)},
        auth=auth,
        timeout=10,
    )
    r.raise_for_status()
    logger.info("Delete OK : %s v%s (irréversible)", model_name, version)


def main() -> int:
    logger.info("Suppression modèle Vélov H+1h du MLflow Registry")
    logger.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
    logger.info("Modèle cible: %s", MODEL_NAME)

    _check_reachable()

    try:
        versions = _list_versions(MODEL_NAME)
    except requests.HTTPError as e:
        # 404 = modèle pas dans le registry → rien à faire, c'est même mieux
        if e.response is not None and e.response.status_code == 404:
            logger.info("Modèle %s absent du Registry — rien à faire.", MODEL_NAME)
            return 0
        raise

    if not versions:
        logger.info("Aucune version trouvée pour %s — Registry déjà clean.", MODEL_NAME)
        return 0

    # Sprint 12+ — on archive d'abord (transition douce), puis on delete
    # pour respecter les best practices MLflow (transition > delete).
    for v_info in versions:
        version = int(v_info["version"])
        current_stage = v_info.get("current_stage", "None")
        logger.info("Version %s (stage=%s) → archivage", version, current_stage)
        try:
            _transition_stage(MODEL_NAME, version, STAGE_NEW)
        except Exception as e:
            logger.warning("Transition v%s échouée (peut-être déjà Archived) : %s", version, e)
        try:
            _delete_model_version(MODEL_NAME, version)
        except Exception as e:
            logger.warning("Delete v%s échouée : %s", version, e)

    logger.info("Terminé. Vérifier dans MLflow UI : %s", MLFLOW_TRACKING_URI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
