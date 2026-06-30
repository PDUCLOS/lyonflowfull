"""MLflow Integration — centralisation du tracking MLflow.

 Toute l'interaction MLflow passe par ce module. Avantages :

* **Single source of truth** pour l'URI tracking, l'experiment name, la
  gestion des runs.
* **Graceful degradation** : si MLflow n'est pas installé ou si le
  serveur est down, les fonctions retournent des no-ops (fallback
  stdout logging) au lieu de planter.
* **Pattern unifié** pour les 2 modèles (XGBoost + GNN) : start_run,
  log_metrics, log_params, log_artifact, end_run.
* **Helpers d'introspection** : list_registered_models(), get_latest_run(),
  compare_models() — consommés par le dashboard Model Monitoring.

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
* ``MLFLOW_TRACKING_URI`` : URL du serveur (défaut ``http://localhost:5000``).
* ``MLFLOW_S3_ENDPOINT_URL`` : pour le backend artifacts S3.

Note il n'y a **pas** de variable d'env globale pour
l'experiment name. Chaque modèle spécifie le sien explicitement :
* ``xgboost_speed`` — XGBoost Speed H+1h
* ``xgboost_velov`` — XGBoost Vélov H+30min + H+1h

L'ancien default global ``DEFAULT_EXPERIMENT = "lyonflow-traffic"`` a
été supprimé (cf. note au-dessus de ``DEFAULT_TRACKING_URI``).
* ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` : credentials S3.

Note : tous les modèles du projet sont loggés dans le même experiment
``lyonflow-traffic`` par défaut, avec un ``run_name`` qui identifie
le modèle + horizon (ex: ``xgboost_speed_h60_20260607_073000``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Détection d'environnement
# -----------------------------------------------------------------------------


def is_mlflow_available() -> bool:
    """Vérifie si la librairie MLflow est installée sur le système.

    Returns:
        bool: True si `mlflow` peut être importé, False sinon.
    """
    try:
        import mlflow  # noqa: F401

        return True
    except ImportError:
        return False


def is_tracking_server_reachable() -> bool:
    """Vérifie si le serveur MLflow (défini par MLFLOW_TRACKING_URI) répond.

    Returns:
        bool: True si le serveur répond aux requêtes de base, False en cas
        d'erreur ou si `mlflow` n'est pas installé.
    """
    if not is_mlflow_available():
        return False
    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
        # Effectue une recherche d'expériences basique pour tester la connexion.
        # Si le serveur est hors-ligne, ceci lèvera une exception.
        client.search_experiments()
        return True
    except Exception:  # pragma: no cover
        return False


# -----------------------------------------------------------------------------
# Configuration Globale
# -----------------------------------------------------------------------------

DEFAULT_TRACKING_URI = "http://localhost:5000"
# NOTE ) — DEFAULT_EXPERIMENT retiré. Chaque modèle log dans
# sa propre expérience dédiée (séparation = bonne pratique MLflow) :
# * xgboost_speed (cf. src/models/xgboost_speed.py)
# * xgboost_velov (cf. src/models/xgboost_velov.py)
DEFAULT_ARTIFACT_ROOT = "./mlruns"


def get_tracking_uri() -> str:
    """Lit l'URI du tracking MLflow depuis l'environnement ou retourne la valeur par défaut.

    Returns:
        str: L'URL du serveur MLflow.
    """
    return os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def get_artifact_root() -> str:
    """Lit le répertoire des artefacts MLflow depuis l'environnement ou retourne la valeur par défaut.

    Returns:
        str: Le chemin de base pour le stockage des artefacts.
    """
    return os.getenv("MLFLOW_DEFAULT_ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT)


# -----------------------------------------------------------------------------
# Tracker principal (Wrapper MLflow)
# -----------------------------------------------------------------------------


class MLflowTracker:
    """Wrapper centralisé pour tracker des entraînements sur MLflow.

    Utilise le pattern context manager (`with ...`) pour garantir que chaque
    run est fermé proprement (même en cas d'exception).

    Si MLflow n'est pas disponible ou si le serveur est down, le tracker
    fonctionne en mode "no-op" : il log les events dans la sortie standard
    mais n'envoie rien à MLflow.
    """

    def __init__(
        self,
        experiment_name: str | None = None,
        tracking_uri: str | None = None,
    ):
        """Initialise le tracker MLflow pour un modèle spécifique.

        Args:
            experiment_name (str | None): Nom de l'expérience MLflow. Il est
                fortement recommandé de le définir explicitement (ex: "xgboost_speed").
            tracking_uri (str | None): URI personnalisé du serveur MLflow. S'il n'est
                pas fourni, utilise les variables d'environnement.
        """
        # Avertissement si experiment_name est omis pour éviter les logs orphelins.
        if experiment_name is None:
            logger.warning(
                "MLflowTracker instancié sans experiment_name — fallback "
                "MLFLOW_EXPERIMENT_NAME env ou 'lyonflow-default'. À éviter "
                "en prod (séparation par modèle = bonne pratique MLflow)."
            )
            experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "lyonflow-default")

        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri or get_tracking_uri()
        self._mlflow: Any = None
        self._run = None
        self._noop = False

        # Tentative de configuration initiale de MLflow
        self._initialize()

    def _initialize(self) -> None:
        """Configure la connexion au serveur de tracking MLflow.

        Bascule le tracker en mode `no-op` silencieusement si MLflow est
        indisponible ou injoignable, afin de ne pas bloquer l'exécution.
        """
        if not is_mlflow_available():
            logger.info("MLflow non installé — tracker en mode no-op")
            self._noop = True
            return

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
            logger.warning("L'initialisation MLflow a échoué (%s) — tracker en mode no-op", e)
            self._noop = True

    @contextmanager
    def start_run(
        self,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Generator[Any, None, None]:
        """Démarre une session d'entraînement MLflow (ou mode no-op).

        Args:
            run_name (str | None): Le nom de la session (run).
            tags (dict[str, str] | None): Dictionnaire de tags à associer au run.

        Yields:
            L'objet `run` actif (ou un mock `_NoopRun` en cas d'indisponibilité).
            Garantit que la session `end_run()` est appelée même en cas d'exception.
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
            # En cas d'exception Python (erreur de code, data, etc.), on marque
            # explicitement le run MLflow comme FAILED avant de relancer l'erreur.
            self._mlflow.end_run(status="FAILED")
            raise
        finally:
            # Succès ou fin naturelle de la clause `with`
            if self._run is not None:
                self._mlflow.end_run(status="FINISHED")
                self._run = None

    def log_params(self, params: dict[str, Any]) -> None:
        """Enregistre un dictionnaire de paramètres pour le run courant.

        Args:
            params (dict): Dictionnaire clé-valeur des paramètres (ex: {"lr": 0.01}).
        """
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_params: %s", params)
            return
        try:
            self._mlflow.log_params(params)
        except Exception as e:  # pragma: no cover
            logger.warning("Échec de MLflow log_params: %s", e)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        """Enregistre les métriques de performance du run courant.

        Args:
            metrics (dict): Dictionnaire clé-valeur des métriques (ex: {"mae": 1.2}).
            step (int | None): Étape ou époque de l'entraînement associée (optionnel).
        """
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] step=%s log_metrics: %s", step, metrics)
            return
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception as e:  # pragma: no cover
            logger.warning("Échec de MLflow log_metrics: %s", e)

    def log_artifact(self, local_path: str) -> None:
        """Upload un fichier local comme artefact dans MLflow.

        Args:
            local_path (str): Chemin d'accès local du fichier à sauvegarder.
        """
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_artifact: %s", local_path)
            return
        try:
            self._mlflow.log_artifact(local_path)
        except Exception as e:  # pragma: no cover
            logger.warning("Échec de MLflow log_artifact: %s", e)

    def set_tag(self, key: str, value: str) -> None:
        """Ajoute ou modifie un tag pour le run courant.

        Args:
            key (str): Nom du tag.
            value (str): Valeur du tag.
        """
        if self._noop or self._mlflow is None:
            return
        try:
            self._mlflow.set_tag(key, value)
        except Exception as e:  # pragma: no cover
            logger.warning("Échec de MLflow set_tag: %s", e)

    def log_dict(self, data: dict, artifact_file: str) -> None:
        """Sauvegarde un dictionnaire Python en tant qu'artefact JSON.

        Args:
            data (dict): Données à sauvegarder.
            artifact_file (str): Nom de l'artefact (ex: "config.json").
        """
        if self._noop or self._mlflow is None:
            logger.info("[MLflow no-op] log_dict: %s", artifact_file)
            return
        try:
            self._mlflow.log_dict(data, artifact_file)
        except Exception as e:  # pragma: no cover
            logger.warning("Échec de MLflow log_dict: %s", e)

    def register_model(self, model_name: str) -> None:
        """Enregistre le modèle du run courant dans le Model Registry.

        Si le modèle existe déjà, une nouvelle version sera créée.

        Args:
            model_name (str): Le nom sous lequel enregistrer le modèle.
        """
        if not self._run:
            return
        try:
            run_id = self._run.info.run_id
            uri = f"runs:/{run_id}/{model_name}.pkl"

            from mlflow.tracking import MlflowClient
            import contextlib

            client = MlflowClient()
            # On ignore l'erreur si le "Registered Model" parent existe déjà
            with contextlib.suppress(Exception):
                client.create_registered_model(model_name)

            client.create_model_version(name=model_name, source=uri, run_id=run_id)
            logger.info("Modèle enregistré: %s (run %s)", model_name, run_id)
        except Exception as e:
            logger.warning("Échec de l'enregistrement du modèle: %s", e)

    def transition_to_production(self, model_name: str) -> None:
        """Promeut la dernière version existante de ce modèle à l'état 'Production'.

        Archive automatiquement toutes les versions précédentes actuellement en Production.

        Args:
            model_name (str): Nom du modèle enregistré.
        """
        try:
            from mlflow.tracking import MlflowClient

            client = MlflowClient()
            versions = client.get_latest_versions(name=model_name)
            if not versions:
                return
            latest = versions[0]

            # Transition vers la phase "Production" et archivage de l'existant
            client.transition_model_version_stage(
                name=model_name, version=latest.version, stage="Production", archive_existing_versions=True
            )
            logger.info("Transition réussie: %s (version %s) vers Production", model_name, latest.version)
        except Exception as e:
            logger.warning("Échec de la transition du modèle vers Production: %s", e)

    @property
    def run_id(self) -> str | None:
        """ID unique du run courant.

        Returns:
            str | None: L'ID si le run est actif, None en cas de mode no-op
            ou si aucun run n'est lancé.
        """
        if self._run is None:
            return None
        return getattr(self._run.info, "run_id", None)


# -----------------------------------------------------------------------------
# Helpers d'introspection (Consommés par le dashboard)
# -----------------------------------------------------------------------------


def list_registered_models(experiment: str | None = None, max_results: int = 50) -> list[dict]:
    """Liste tous les modèles enregistrés dans une expérience MLflow donnée.

    Args:
        experiment (str | None): Nom de l'expérience (None = toutes).
        max_results (int): Nombre maximum de runs à retourner (défaut 50).

    Returns:
        list[dict]: Liste de dictionnaires contenant le statut et les métriques des modèles.
            (clés: ``name``, ``version``, ``stage``, ``metrics``, ``params``, ``trained_at``, ``run_id``)

    Raises:
    DashboardDataError: fail loud) si MLflow est indisponible ou non joignable.
    """
    from src.data.exceptions import DashboardDataError

    if not is_mlflow_available():
        raise DashboardDataError(
            source="mlflow",
            detail="Module mlflow non installé. Exécutez `pip install mlflow`.",
        )

    # Vérification rapide de connectivité avant l'appel API client
    if not is_tracking_server_reachable():
        raise DashboardDataError(
            source="mlflow",
            detail=(
                f"MLflow tracking server non joignable ({get_tracking_uri()}). "
                "Vérifier que le service mlflow est actif (ex: docker compose ps mlflow)."
            ),
        )

    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
        models = client.search_registered_models(max_results=max_results)
        out = []
        for rm in models:
            # Filtrage par nom d'expérience si demandé (On suppose ici que le nom
            # du modèle commence par le nom de l'expérience).
            if experiment and not rm.name.startswith(experiment):
                continue

            latest_versions = rm.latest_versions
            if not latest_versions:
                continue

            # Priorise la version taggée 'Production', sinon prend la version la plus récente
            prod_version = next((v for v in latest_versions if v.current_stage == "Production"), latest_versions[0])
            run_id = prod_version.run_id

            try:
                # Récupère les détails du run associé
                run = client.get_run(run_id)
                data = run.data
                metrics = dict(data.metrics)
                params = dict(data.params)
                tags = dict(data.tags)
                trained_at = run.info.start_time
            except Exception:
                metrics, params, tags, trained_at = {}, {}, {}, None

            out.append(
                {
                    "name": rm.name,
                    "model_name": rm.name,
                    "horizon_min": int(tags.get("horizon_min", 0)) if tags.get("horizon_min", "").isdigit() else None,
                    "version": prod_version.version,
                    "stage": prod_version.current_stage,
                    "metrics": metrics,
                    "params": params,
                    "tags": tags,
                    "trained_at": trained_at,
                    "run_id": run_id,
                }
            )
        return out
    except DashboardDataError:
        raise
    except Exception as e:  # pragma: no cover
        raise DashboardDataError(
            source="mlflow",
            detail=f"L'opération search_registered_models de MLflow a échoué : {e}",
        ) from e


def get_latest_run(model_name: str, experiment: str | None = None) -> dict | None:
    """Récupère les informations du dernier run pour un modèle précis.

    Args:
        model_name (str): Nom logique du modèle (ex: "xgboost_speed_h60").
        experiment (str | None): Nom de l'expérience (None = toutes).

    Returns:
        dict | None: Dictionnaire contenant les `metrics`, `params`, `tags`,
        `trained_at` et `run_id`. Renvoie None si introuvable.
    """
    runs = list_registered_models(experiment=experiment, max_results=200)
    for r in runs:
        if r["name"].startswith(model_name):
            return r
    return None


def compare_models(model_a: str, model_b: str, metric: str = "mae", experiment: str | None = None) -> dict:
    """Compare deux modèles sur la base d'une métrique spécifique.

    Se base sur le dernier run de chaque modèle.

    Args:
        model_a (str): Nom du premier modèle.
        model_b (str): Nom du second modèle.
        metric (str): La métrique à comparer (ex: "mae", "rmse"). Défaut "mae".
        experiment (str | None): Expérience concernée.

    Returns:
        dict: Contient le détail du run `a`, du run `b`, le différentiel (`delta`),
        la `metric` comparée, et le gagnant (`winner`).
    """
    run_a = get_latest_run(model_a, experiment=experiment)
    run_b = get_latest_run(model_b, experiment=experiment)

    if not run_a or not run_b:
        return {"a": run_a, "b": run_b, "delta": None, "winner": None}

    val_a = run_a.get("metrics", {}).get(metric, 0.0)
    val_b = run_b.get("metrics", {}).get(metric, 0.0)
    delta = val_b - val_a

    # "Lower is better" est utilisé ici en présumant des métriques d'erreur (mae, rmse, mape)
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


def get_experiment_summary(experiment: str) -> dict:
    """Retourne un résumé synthétique de l'expérience demandée.

    Note `experiment` est désormais obligatoire.

      Args:
          experiment (str): Nom de l'expérience MLflow.

      Returns:
          dict: Résumé avec `name`, `run_count`, `latest_run_at`,
          `model_names`, et disponibilité (`available`).
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
    # Cast et gestion du max sur la date
    latest_ts = max(
        (cast(datetime, r["trained_at"]) for r in runs if r.get("trained_at") is not None),
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
# Stub pour mode No-op
# -----------------------------------------------------------------------------


class _NoopRun:
    """Mock/Stub utilisé lorsque MLflow n'est pas disponible.

    Permet au code client d'interagir avec l'objet Run sans erreurs
    quand le serveur est hors-ligne.
    """

    info = type("Info", (), {"run_id": "noop_run"})()


# -----------------------------------------------------------------------------
# Méthode utilitaire One-Liner
# -----------------------------------------------------------------------------


def quick_log(
    experiment: str,
    run_name: str,
    params: dict,
    metrics: dict,
    artifact_path: str | None = None,
) -> str | None:
    """Logue rapidement un run MLflow complet en une seule instruction.

    Args:
        experiment (str): Nom de l'expérience cible.
        run_name (str): Nom du run.
        params (dict): Dictionnaire de paramètres.
        metrics (dict): Dictionnaire de métriques de performance.
        artifact_path (str | None): Chemin local vers un artefact à uploader (optionnel).

    Returns:
        str | None: Le run_id généré par MLflow (ou "noop" si inactif).

    Example:
        ```python
        run_id = quick_log(
            experiment="xgboost_speed",
            run_name=f"h{horizon}_{int(time.time())}",
            params={"n_estimators": 200},
            metrics={"mae": 2.5, "rmse": 3.1},
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
