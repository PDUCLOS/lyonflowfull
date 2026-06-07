"""MLflow Integration — centralisation du tracking MLflow.

Sprint 8 — Toute l'interaction MLflow passe par ce module. Avantages :

* **Single source of truth** pour l'URI tracking, l'experiment name, la
  gestion des runs
* **Graceful degradation** : si MLflow n'est pas installé ou si le
  serveur est down, les fonctions retournent des no-ops (fallback
  stdout logging) au lieu de planter
* **Pattern unifié** pour les 2 modèles (XGBoost + GNN) : start_run,
  log_metrics, log_params, log_artifact, end_run
* **Helpers d'introspection** : list_registered_models(), get_latest_run(),
  compare_models() — consommés par le dashboard Model Monitoring

## Usage côté trainer (XGBoost Speed)

```python
from src.ml.mlflow_integration import MLflowTracker

tracker = MLflowTracker(experiment_name="xgboost_speed")
with tracker.start_run(run_name=f"h{horizon}_{timestamp}") as run:
    tracker.log_params({"horizon_min": horizon, "n_estimators": 200})
    metrics = model.fit(...)
    tracker.log_metrics(metrics)
    tracker.log_artifact(model_path)
```

## Usage côté dashboard (Model Monitoring)

```python
from src.ml.mlflow_integration import list_registered_models, get_latest_run

models = list_registered_models(experiment="xgboost_speed")
for m in models:
    latest = get_latest_run(m["name"])
    st.metric(f"{m['name']} v{latest['version']}", f"MAE={latest['metrics']['mae']:.2f}")
```

## Configuration

Variables d'env :
* ``MLFLOW_TRACKING_URI`` : URL du serveur (défaut ``http://localhost:5000``)
* ``MLFLOW_EXPERIMENT_NAME`` : nom par défaut (utilisé si non spécifié)
* ``MLFLOW_S3_ENDPOINT_URL`` : pour le backend artifacts S3
* ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` : credentials S3

Note : tous les modèles du projet sont loggés dans le même experiment
``lyonflow-traffic`` par défaut, avec un ``run_name`` qui identifie
le modèle + horizon (ex: ``xgboost_speed_h60_20260607_073000``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Détection d'environnement
# -----------------------------------------------------------------------------


def is_mlflow_available() -> bool:
    """True si la lib mlflow est installée ET le serveur joignable."""
    try:
        import mlflow  # noqa: F401

        return True
    except ImportError:
        return False


def is_tracking_server_reachable() -> bool:
    """True si le serveur MLflow (MLFLOW_TRACKING_URI) répond."""
    if not is_mlflow_available():
        return False
    try:
        from mlflow.tracking import MlflowClient  # type: ignore[import-untyped]

        client = MlflowClient()
        client.list_experiments()  # throws si serveur down
        return True
    except Exception:  # pragma: no cover
        return False


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------


DEFAULT_TRACKING_URI = "http://localhost:5000"
DEFAULT_EXPERIMENT = "lyonflow-traffic"
DEFAULT_ARTIFACT_ROOT = "./mlruns"


def get_tracking_uri() -> str:
    """Lit MLFLOW_TRACKING_URI ou fallback défaut."""
    return os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def get_artifact_root() -> str:
    """Lit MLFLOW_DEFAULT_ARTIFACT_ROOT ou fallback défaut."""
    return os.getenv("MLFLOW_DEFAULT_ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT)


# -----------------------------------------------------------------------------
# Tracker principal
# -----------------------------------------------------------------------------


class MLflowTracker:
    """Wrapper centralisé pour tracker des entraînements sur MLflow.

    Utilise le pattern context manager pour garantir que chaque run est
    fermé proprement (même en cas d'exception).

    Si MLflow n'est pas disponible ou si le serveur est down, le tracker
    fonctionne en mode "no-op" : il log les events dans stdout mais
    n'envoie rien à MLflow.
    """

    def __init__(
        self,
        experiment_name: str = DEFAULT_EXPERIMENT,
        tracking_uri: str | None = None,
    ):
        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri or get_tracking_uri()
        self._mlflow = None
        self._run = None
        self._noop = False
        self._initialize()

    def _initialize(self) -> None:
        """Configure MLflow tracking. Bascule en no-op si indispo.

        Note : on ne tente ``set_experiment`` que si le serveur est
        joignable (sinon la lib MLflow peut hang plusieurs secondes sur
        un timeout réseau).
        """
        if not is_mlflow_available():
            logger.info("MLflow non installé — tracker en mode no-op")
            self._noop = True
            return
        # Quick reachability check avant d'appeler set_experiment (qui hang)
        if not is_tracking_server_reachable():
            logger.info("MLflow tracking server indispo (%s) — no-op", self.tracking_uri)
            self._noop = True
            return
        try:
            import mlflow

            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            self._mlflow = mlflow
            logger.info("MLflow tracker initialisé: %s / %s", self.tracking_uri, self.experiment_name)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow init failed (%s) — tracker en mode no-op", e)
            self._noop = True

    @contextmanager
    def start_run(
        self,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Generator[Any, None, None]:
        """Démarre un run MLflow (ou no-op si indispo).

        Yields l'objet run (ou un mock). Garantit end_run() même en cas
        d'exception.
        """
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] start_run: %s", run_name or "unnamed")
            yield _NoopRun()
            return

        run = self._mlflow.start_run(run_name=run_name, tags=tags or {})
        self._run = run
        try:
            yield run
        except Exception:
            self._mlflow.end_run(status="FAILED")
            raise
        finally:
            if self._run is not None:
                self._mlflow.end_run(status="FINISHED")
                self._run = None

    def log_params(self, params: dict[str, Any]) -> None:
        """Log des hyperparamètres du run courant."""
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_params: %s", params)
            return
        try:
            self._mlflow.log_params(params)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow log_params failed: %s", e)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        """Log des métriques du run courant (MAE, RMSE, etc.)."""
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] step=%s log_metrics: %s", step, metrics)
            return
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow log_metrics failed: %s", e)

    def log_artifact(self, local_path: str) -> None:
        """Upload un fichier local comme artifact du run."""
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_artifact: %s", local_path)
            return
        try:
            self._mlflow.log_artifact(local_path)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow log_artifact failed: %s", e)

    def set_tag(self, key: str, value: str) -> None:
        """Pose un tag sur le run (ex: ``"model": "xgboost_speed"``)."""
        if self._noop or self._mlflow is None:
            return
        try:
            self._mlflow.set_tag(key, value)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow set_tag failed: %s", e)

    def log_dict(self, data: dict, artifact_file: str) -> None:
        """Log un dict Python comme JSON artifact."""
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_dict: %s", artifact_file)
            return
        try:
            self._mlflow.log_dict(data, artifact_file)
        except Exception as e:  # pragma: no cover
            logger.warning("MLflow log_dict failed: %s", e)

    @property
    def run_id(self) -> str | None:
        """ID du run courant, ou None si no-op ou pas de run."""
        if self._run is None:
            return None
        return getattr(self._run.info, "run_id", None)


# -----------------------------------------------------------------------------
# Helpers d'introspection (consommés par le dashboard)
# -----------------------------------------------------------------------------


def list_registered_models(experiment: str | None = None, max_results: int = 50) -> list[dict]:
    """Liste les modèles trackés dans un experiment MLflow.

    Args:
        experiment: nom de l'experiment (None = tous).
        max_results: nombre max de runs à retourner.

    Returns:
        Liste de dicts avec ``name``, ``version``, ``stage``, ``metrics``,
        ``params``, ``trained_at``, ``run_id``.

    Note:
        Si MLflow indispo ou serveur non joignable, retourne une liste
        vide (le dashboard affichera un message "MLflow non accessible").
    """
    if not is_mlflow_available():
        return []
    # Quick reachability check avant d'appeler le client (sinon hang)
    if not is_tracking_server_reachable():
        return []
    try:
        from mlflow.tracking import MlflowClient  # type: ignore[import-untyped]

        client = MlflowClient()
        # mlflow>=2.0 utilise experiment_ids (int), pas experiment_names (str)
        experiment_ids = None
        if experiment:
            exp = client.get_experiment_by_name(experiment)
            if exp is not None:
                experiment_ids = [exp.experiment_id]
            else:
                return []
        runs = client.search_runs(
            experiment_ids=experiment_ids,
            max_results=max_results,
            order_by=["start_time DESC"],
        )
        out = []
        for r in runs:
            data = r.data
            run_name = data.tags.get("mlflow.runName", r.info.run_id[:8])
            model_name = data.tags.get("model", run_name.split("_h")[0])
            horizon_tag = data.tags.get("horizon_min", "")
            model_version = data.params.get("model_version", "1.0.0")
            out.append(
                {
                    "name": run_name,
                    "model_name": model_name,
                    "horizon_min": int(horizon_tag) if horizon_tag.isdigit() else None,
                    "version": model_version,
                    "stage": "Production",  # on simplifier pour le moment
                    "metrics": dict(data.metrics),
                    "params": dict(data.params),
                    "tags": dict(data.tags),
                    "trained_at": r.info.start_time,
                    "run_id": r.info.run_id,
                }
            )
        return out
    except Exception as e:  # pragma: no cover
        logger.warning("list_registered_models failed: %s", e)
        return []


def get_latest_run(model_name: str, experiment: str | None = None) -> dict | None:
    """Récupère le dernier run d'un modèle donné.

    Args:
        model_name: nom logique du modèle (ex: "xgboost_speed_h60").
        experiment: nom de l'experiment (None = tous).

    Returns:
        Dict avec metrics, params, tags, trained_at, run_id. None si
        pas trouvé.
    """
    runs = list_registered_models(experiment=experiment, max_results=200)
    for r in runs:
        if r["name"].startswith(model_name):
            return r
    return None


def compare_models(
    model_a: str, model_b: str, metric: str = "mae", experiment: str | None = None
) -> dict:
    """Compare 2 modèles sur une métrique donnée (dernier run de chaque).

    Returns:
        Dict avec ``a`` (run dict), ``b`` (run dict), ``delta`` (b - a),
        ``winner`` (le modèle avec la plus petite metric si lower_is_better).
    """
    run_a = get_latest_run(model_a, experiment=experiment)
    run_b = get_latest_run(model_b, experiment=experiment)
    if not run_a or not run_b:
        return {"a": run_a, "b": run_b, "delta": None, "winner": None}

    val_a = run_a.get("metrics", {}).get(metric, 0.0)
    val_b = run_b.get("metrics", {}).get(metric, 0.0)
    delta = val_b - val_a
    # Lower is better pour mae/rmse/mape
    winner = model_a if val_a <= val_b else model_b
    return {
        "a": run_a,
        "b": run_b,
        "delta": delta,
        "winner": winner,
        "metric": metric,
        "value_a": val_a,
        "value_b": val_b,
    }


def get_experiment_summary(experiment: str = DEFAULT_EXPERIMENT) -> dict:
    """Résumé d'un experiment : nb runs, dates, modèles présents.

    Returns:
        Dict avec ``name``, ``run_count``, ``latest_run_at``, ``model_names``.
    """
    runs = list_registered_models(experiment=experiment, max_results=200)
    if not runs:
        return {
            "name": experiment,
            "run_count": 0,
            "latest_run_at": None,
            "model_names": [],
            "available": is_tracking_server_reachable(),
        }
    model_names = sorted({r["model_name"] for r in runs if r.get("model_name")})
    latest_ts = max(
        (r.get("trained_at") for r in runs if r.get("trained_at")),
        default=None,
    )
    return {
        "name": experiment,
        "run_count": len(runs),
        "latest_run_at": latest_ts,
        "model_names": model_names,
        "available": True,
    }


# -----------------------------------------------------------------------------
# No-op run
# -----------------------------------------------------------------------------


class _NoopRun:
    """Stub quand MLflow n'est pas dispo."""

    info = type("Info", (), {"run_id": "noop_run"})()


# -----------------------------------------------------------------------------
# Convenience pour usage one-liner
# -----------------------------------------------------------------------------


def quick_log(
    experiment: str,
    run_name: str,
    params: dict,
    metrics: dict,
    artifact_path: str | None = None,
) -> str | None:
    """Log rapide d'un run complet (1 ligne). Retourne le run_id ou None.

    Pattern ultra-simple pour les trainers :
    ```python
    run_id = quick_log(
        "xgboost_speed",
        f"h{horizon}_{int(time.time())}",
        params={"n_estimators": 200, ...},
        metrics={"mae": 2.5, "rmse": 3.1, "r2": 0.92},
        artifact_path=model_path,
    )
    ```
    """
    tracker = MLflowTracker(experiment_name=experiment)
    with tracker.start_run(run_name=run_name):
        tracker.log_params(params)
        tracker.log_metrics(metrics)
        if artifact_path:
            tracker.log_artifact(artifact_path)
    return tracker.run_id or "noop"
