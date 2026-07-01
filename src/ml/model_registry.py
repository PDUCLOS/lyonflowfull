"""Registre des modèles (Model Registry) — XGBoost speed/velov uniquement.

Le projet a archivé le tandem GNN+XGBoost (Sprint 24+, 2026-06-30). Seul
XGBoost reste en production :

* ``XGBoostSpeedModel`` — prédiction vitesse trafic H+1h (focus principal)
* ``XGBoostVelovModel`` — prédiction disponibilité Vélov H+1h

Pour la traçabilité (RNCP 38777), l'ancien code GNN/STGCN est conservé
dans ``archive/legacy/gnn/`` (training/stgcn/, src/models/stgcn_wrapper.py,
dags/ml/retrain_gnn.py, tests/ml/test_stgcn.py).

## Variables d'environnement supportées

* ``LYONFLOW_XGBOOST_TRAINING`` : ``True`` (défaut) | ``False`` (skip retrain)
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ModelKind(StrEnum):
    """Type de modèle ML."""

    XGBOOST = "xgboost"


def is_xgboost_enabled() -> bool:
    """True si XGBoost est activé (toujours True — seul modèle en prod)."""
    return True


def is_xgboost_training_enabled() -> bool:
    """True si le DAG XGBoost peut s'exécuter (toggle séparé).

    Lit directement l'env var (pas le cache pydantic-settings) pour
    permettre le toggle runtime sans redémarrer.
    """
    return os.getenv("LYONFLOW_XGBOOST_TRAINING", "true").lower() not in ("false", "0", "no", "")


def is_model_monitoring_visible() -> bool:
    """True si le dashboard Model Monitoring MLflow est visible.

    Lit l'env var directement. Par défaut True.
    Set ``LYONFLOW_DASHBOARD_MODEL_MONITORING=false`` pour masquer.
    """
    return os.getenv("LYONFLOW_DASHBOARD_MODEL_MONITORING", "true").lower() not in (
        "false",
        "0",
        "no",
    )


def is_traffic_map_visible() -> bool:
    """True si la carte trafic est visible dans le dashboard.

    Lit l'env var directement. Par défaut True.
    Set ``LYONFLOW_DASHBOARD_TRAFFIC_MAP=false`` pour masquer.
    """
    return os.getenv("LYONFLOW_DASHBOARD_TRAFFIC_MAP", "true").lower() not in (
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
    display_name = "XGBoost (Production)"
    _model: Any

    def __init__(self, horizon_min: int, model_dir: str | None = None):
        from pathlib import Path

        self.horizon_min = horizon_min
        resolved_dir = model_dir or os.getenv("LYONFLOW_MODELS_DIR") or "/app/models"
        self.model_dir = Path(resolved_dir)
        self._model: Any = None

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
            assert self._model is not None
            return self._model.predict(features)
        except Exception as e:  # pragma: no cover
            logger.exception("XGBoost prediction failed: %s", e)
            return None


ModelHandle = XGBoostModelHandle


# -----------------------------------------------------------------------------
# Registry principal
# -----------------------------------------------------------------------------


class ModelRegistry:
    """Singleton qui orchestre l'accès au modèle XGBoost (seul modèle en prod)."""

    _instances: dict[str, ModelRegistry] = {}

    def __init__(self, horizon_min: int):
        self.horizon_min = horizon_min
        self._xgb: XGBoostModelHandle | None = None

    @classmethod
    def get(cls, horizon_min: int) -> ModelRegistry:
        """Singleton par horizon (évite de recharger les modèles)."""
        key = f"h{horizon_min}"
        if key not in cls._instances:
            cls._instances[key] = cls(horizon_min=horizon_min)
        return cls._instances[key]

    @property
    def xgboost(self) -> XGBoostModelHandle | None:
        """Handle XGBoost (toujours disponible — seul modèle en prod)."""
        if self._xgb is None:
            self._xgb = XGBoostModelHandle(horizon_min=self.horizon_min)
        return self._xgb

    def get_active_model(self) -> ModelHandle | None:
        """Retourne le modèle actif (XGBoost, seul modèle en prod)."""
        return self.xgboost

    def status(self) -> dict:
        """État détaillé du modèle — pour le monitoring dashboard."""
        return {
            "horizon_min": self.horizon_min,
            "active": ModelKind.XGBOOST.value,
            "xgboost_available": self.xgboost.is_available() if self.xgboost else False,
            "xgboost_training": is_xgboost_training_enabled(),
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
