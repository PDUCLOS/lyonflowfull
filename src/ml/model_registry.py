"""Model Registry — coexistence XGBoost + GNN avec feature flags.

Sprint 8 — Permet de faire tourner les 2 solutions en parallèle et de
basculer de l'une à l'autre via une simple variable d'environnement.

## Usage

```python
from src.ml.model_registry import ModelRegistry, ModelKind

# Récupérer le modèle actif (selon LYONFLOW_MODELS_ACTIVE)
model = ModelRegistry.get_active_model(horizon_min=60)
prediction = model.predict(features)

# Comparer les 2 modèles
comparison = ModelRegistry.compare_predictions(
    features, edge_index, horizon_min=60
)
# → {"xgboost": [...], "stgcn": [...], "delta": [...]}
```

## Variables d'environnement

* ``LYONFLOW_MODELS_ACTIVE`` : ``"xgboost"`` | ``"stgcn"`` | ``"both"`` (défaut)
* ``LYONFLOW_STGCN_TRAINING`` : ``True`` (défaut) | ``False`` (skip retrain)
* ``LYONFLOW_XGBOOST_TRAINING`` : ``True`` (défaut) | ``False`` (skip retrain)

## Workflow validation

Phase 1 (les 2 en //) :
    ``LYONFLOW_MODELS_ACTIVE=both``

Phase 2 (GNN challengé, on accumule des data) :
    ``LYONFLOW_MODELS_ACTIVE=both`` + dashboard compare

Phase 3 (Patrice valide le GNN) :
    ``LYONFLOW_MODELS_ACTIVE=stgcn`` → XGBoost désactivé
    ``LYONFLOW_XGBOOST_TRAINING=False`` → DAG XGBoost pause

Phase 4 (rollback éventuel) :
    ``LYONFLOW_MODELS_ACTIVE=xgboost`` → retour XGBoost seul
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

logger = logging.getLogger(__name__)


class ModelKind(StrEnum):
    """Type de modèle ML."""

    XGBOOST = "xgboost"
    STGCN = "stgcn"
    BOTH = "both"


# -----------------------------------------------------------------------------
# Constantes d'activation (miroir de la config, pour usage rapide)
# -----------------------------------------------------------------------------


def get_active_models() -> ModelKind:
    """Lit LYONFLOW_MODELS_ACTIVE et retourne le ModelKind correspondant.

    Returns:
        ModelKind.XGBOOST / STGCN / BOTH

    Raises:
        ValueError: si la valeur d'env est inconnue.
    """
    raw = os.getenv("LYONFLOW_MODELS_ACTIVE", "both").lower().strip()
    if raw == "xgboost":
        return ModelKind.XGBOOST
    if raw == "stgcn":
        return ModelKind.STGCN
    if raw == "both":
        return ModelKind.BOTH
    raise ValueError(f"LYONFLOW_MODELS_ACTIVE='{raw}' invalide. Valeurs acceptées : xgboost, stgcn, both.")


def is_xgboost_enabled() -> bool:
    """True si XGBoost est dans les modèles actifs."""
    return get_active_models() in (ModelKind.XGBOOST, ModelKind.BOTH)


def is_stgcn_enabled() -> bool:
    """True si le GNN est dans les modèles actifs."""
    return get_active_models() in (ModelKind.STGCN, ModelKind.BOTH)


def is_xgboost_training_enabled() -> bool:
    """True si le DAG XGBoost peut s'exécuter (toggle séparé).

    Lit directement l'env var (pas le cache pydantic-settings) pour
    permettre le toggle runtime sans redémarrer.
    """
    return os.getenv("LYONFLOW_XGBOOST_TRAINING", "true").lower() not in ("false", "0", "no", "")


def is_stgcn_training_enabled() -> bool:
    """True si le DAG GNN peut s'exécuter (toggle séparé).

    Lit directement l'env var (pas le cache pydantic-settings) pour
    permettre le toggle runtime sans redémarrer.

    Note Sprint 9 : par défaut False (le DAG est créé en pause pour
    préparation). Pour activer : set ``LYONFLOW_STGCN_TRAINING=true``.
    """
    return os.getenv("LYONFLOW_STGCN_TRAINING", "false").lower() not in ("false", "0", "no", "")


# -----------------------------------------------------------------------------
# Sprint 9 — Feature flags dashboard (cartes préparées mais masquées)
# -----------------------------------------------------------------------------


def is_gnn_map_visible() -> bool:
    """True si la carte trafic GNN est visible dans le dashboard.

    Lit l'env var directement (pas le cache pydantic) pour permettre
    le toggle runtime. Par défaut True (carte intégrée Pro/Usager/Elu).
    Set ``LYONFLOW_DASHBOARD_GNN_MAP=false`` pour masquer.
    """
    return os.getenv("LYONFLOW_DASHBOARD_GNN_MAP", "true").lower() not in ("false", "0", "no")


def is_model_monitoring_visible() -> bool:
    """True si le dashboard Model Monitoring MLflow est visible.

    Lit l'env var directement. Par défaut True (intégré Sprint 10).
    Set ``LYONFLOW_DASHBOARD_MODEL_MONITORING=false`` pour masquer.
    """
    return os.getenv("LYONFLOW_DASHBOARD_MODEL_MONITORING", "true").lower() not in (
        "false",
        "0",
        "no",
    )


# -----------------------------------------------------------------------------
# Wrappers unifiés
# -----------------------------------------------------------------------------


class XGBoostModelHandle:
    """Handle unifié pour le modèle XGBoost (XGBoostSpeedModel / XGBoostVelovModel)."""

    model_kind = ModelKind.XGBOOST
    display_name = "XGBoost (Champion)"

    def __init__(self, horizon_min: int, model_dir: str | None = None):
        from pathlib import Path

        self.horizon_min = horizon_min
        self.model_dir = Path(model_dir or os.getenv("LYONFLOW_MODELS_DIR", "/app/models"))
        self._model = None

    def is_available(self) -> bool:
        """Vérifie que le modèle existe sur disque + xgboost installé."""
        try:
            import xgboost  # noqa: F401
        except ImportError:
            return False
        return (self.model_dir / f"xgb_speed_h{self.horizon_min}.json").exists()

    def load(self) -> bool:
        """Charge le modèle. Retourne True si succès."""
        if not self.is_available():
            return False
        try:
            from src.models.xgboost_speed import XGBoostSpeedModel

            self._model = XGBoostSpeedModel(model_dir=str(self.model_dir))
            self._model.load(horizons=[self.horizon_min])
            return True
        except Exception as e:  # pragma: no cover
            logger.exception("Failed to load XGBoost H+%dmin: %s", self.horizon_min, e)
            return False

    def predict(self, features) -> list[float] | None:
        """Prédit. Retourne None si pas chargé."""
        if self._model is None and not self.load():
            return None
        try:
            return self._model.predict(features)
        except Exception as e:  # pragma: no cover
            logger.exception("XGBoost prediction failed: %s", e)
            return None


class STGCNModelHandle:
    """Handle unifié pour le modèle STGCN (SpatioTemporalGCN)."""

    model_kind = ModelKind.STGCN
    display_name = "SpatioTemporalGCN (Challenger)"

    def __init__(self, horizon_min: int, model_dir: str | None = None):
        self.horizon_min = horizon_min
        from src.models.stgcn_wrapper import STGCNWrapper

        self._wrapper: STGCNWrapper | None = None
        # Force model_dir via le singleton cache
        if model_dir:
            os.environ["LYONFLOW_MODELS_DIR"] = model_dir

    def is_available(self) -> bool:
        """Vérifie que torch + modèle dispo."""
        from src.models.stgcn_wrapper import STGCNWrapper
        from training.stgcn.model import is_available

        if not is_available():
            return False
        # Force singleton to use this horizon's model
        w = STGCNWrapper(horizon_min=self.horizon_min)
        return w.load()  # charge ou retourne False

    def load(self) -> bool:
        """Charge via STGCNWrapper."""
        from src.models.stgcn_wrapper import STGCNWrapper

        self._wrapper = STGCNWrapper.get(self.horizon_min)
        return self._wrapper.load()

    def predict(self, features, edge_index=None) -> list[float] | None:
        """Prédit. Retourne None si pas chargé."""
        if self._wrapper is None or (not self._wrapper.is_available and not self.load()):
            return None
        try:
            arr = self._wrapper.predict(features, edge_index) if edge_index is not None else None
            if arr is None:
                return None
            return arr.flatten().tolist()
        except Exception as e:  # pragma: no cover
            logger.exception("STGCN prediction failed: %s", e)
            return None


# Type union pour les handles
ModelHandle = XGBoostModelHandle | STGCNModelHandle


# -----------------------------------------------------------------------------
# Registry principal
# -----------------------------------------------------------------------------


class ModelRegistry:
    """Singleton qui orchestre l'activation des modèles selon les env vars."""

    _instances: dict[str, ModelRegistry] = {}

    def __init__(self, horizon_min: int):
        self.horizon_min = horizon_min
        self._xgb: XGBoostModelHandle | None = None
        self._stgcn: STGCNModelHandle | None = None

    @classmethod
    def get(cls, horizon_min: int) -> ModelRegistry:
        """Singleton par horizon (évite de recharger les modèles)."""
        key = f"h{horizon_min}"
        if key not in cls._instances:
            cls._instances[key] = cls(horizon_min=horizon_min)
        return cls._instances[key]

    # ------------------------------------------------------------------
    # Accès aux modèles
    # ------------------------------------------------------------------

    @property
    def xgboost(self) -> XGBoostModelHandle | None:
        """Handle XGBoost, ou None si désactivé."""
        if not is_xgboost_enabled():
            return None
        if self._xgb is None:
            self._xgb = XGBoostModelHandle(horizon_min=self.horizon_min)
        return self._xgb

    @property
    def stgcn(self) -> STGCNModelHandle | None:
        """Handle STGCN, ou None si désactivé."""
        if not is_stgcn_enabled():
            return None
        if self._stgcn is None:
            self._stgcn = STGCNModelHandle(horizon_min=self.horizon_min)
        return self._stgcn

    def get_active_model(self) -> ModelHandle | None:
        """Retourne le modèle actif (selon LYONFLOW_MODELS_ACTIVE).

        Returns:
            * ModelKind.XGBOOST → XGBoostModelHandle
            * ModelKind.STGCN   → STGCNModelHandle
            * ModelKind.BOTH     → XGBoostModelHandle (champion par défaut,
              GNN challenger pour comparaison)
        """
        active = get_active_models()
        if active == ModelKind.XGBOOST:
            return self.xgboost
        if active == ModelKind.STGCN:
            return self.stgcn
        # BOTH : champion = XGBoost (prouvé), challenger = STGCN
        return self.xgboost

    def get_challenger_model(self) -> ModelHandle | None:
        """Retourne le modèle challenger (None si BOTH pas activé)."""
        if get_active_models() != ModelKind.BOTH:
            return None
        # Si champion = XGBoost, challenger = STGCN
        if is_xgboost_enabled() and is_stgcn_enabled():
            return self.stgcn
        return None

    # ------------------------------------------------------------------
    # Comparaison pour le monitoring
    # ------------------------------------------------------------------

    def compare_predictions(
        self,
        features,
        edge_index=None,
    ) -> dict:
        """Fait tourner les 2 modèles en // et compare les sorties.

        Returns:
            Dict avec :
            * ``xgboost`` : list[float] | None
            * ``stgcn``   : list[float] | None
            * ``delta``   : list[float] | None (stgcn - xgboost, élément-wise)
            * ``active``  : ModelKind actif pour servir la requête prod
            * ``mode``    : "champion" | "challenger" | "single"
        """
        result: dict = {
            "horizon_min": self.horizon_min,
            "xgboost": None,
            "stgcn": None,
            "delta": None,
            "active": get_active_models().value,
            "mode": "single",
        }

        xgb_pred = self.xgboost.predict(features) if self.xgboost else None
        stgcn_pred = self.stgcn.predict(features, edge_index) if self.stgcn else None

        result["xgboost"] = xgb_pred
        result["stgcn"] = stgcn_pred

        if xgb_pred is not None and stgcn_pred is not None and len(xgb_pred) == len(stgcn_pred):
            result["delta"] = [s - x for s, x in zip(stgcn_pred, xgb_pred, strict=False)]
            result["mode"] = "champion_vs_challenger"

        return result

    # ------------------------------------------------------------------
    # Status pour le dashboard
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """État détaillé des modèles — pour le monitoring dashboard.

        Returns:
            Dict avec :
            * ``active`` : "xgboost" | "stgcn" | "both"
            * ``xgboost_available`` : bool
            * ``stgcn_available`` : bool
            * ``xgboost_training`` : bool (toggle DAG)
            * ``stgcn_training`` : bool (toggle DAG)
        """
        return {
            "horizon_min": self.horizon_min,
            "active": get_active_models().value,
            "xgboost_available": self.xgboost.is_available() if self.xgboost else False,
            "stgcn_available": self.stgcn.is_available() if self.stgcn else False,
            "xgboost_training": is_xgboost_training_enabled(),
            "stgcn_training": is_stgcn_training_enabled(),
            "champion": "xgboost" if is_xgboost_enabled() else ("stgcn" if is_stgcn_enabled() else None),
            "challenger": "stgcn" if get_active_models() == ModelKind.BOTH else None,
        }

    @classmethod
    def reset(cls) -> None:
        """Reset le cache (utile pour les tests)."""
        cls._instances.clear()


# -----------------------------------------------------------------------------
# Helper pour les DAGs Airflow
# -----------------------------------------------------------------------------


def should_run_xgboost_dag() -> bool:
    """Le DAG retrain_xgboost_* doit-il s'exécuter ?

    Returns:
        True si XGBoost est activé ET le toggle training est ON.
    """
    return is_xgboost_enabled() and is_xgboost_training_enabled()


def should_run_stgcn_dag() -> bool:
    """Le DAG retrain_gnn doit-il s'exécuter ?

    Returns:
        True si STGCN est activé ET le toggle training est ON.

    Note: l'entraînement se fait sur EC2 typiquement (pas VPS).
    Le DAG peut être scheduleé sur le cluster Airflow EC2 ou appelé
    via SSH depuis le VPS — voir docs/EC2_TRAINING_GUIDE.md.
    """
    return is_stgcn_enabled() and is_stgcn_training_enabled()
