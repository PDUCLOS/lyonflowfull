"""STGCNWrapper — wrapper production pour inférence SpatioTemporalGCN.

Fait le pont entre :

* Le modèle entraîné (sauvegardé via ``STGCNTrainer``)
* L'API ``/predict/traffic`` (qui attend du JSON)
* Le DAG ``retrain_gnn`` (qui charge + prédit)

API publique :

* ``STGCNWrapper.load(horizon_min)`` — charge le modèle depuis le disque
* ``STGCNWrapper.predict(features, edge_index)`` — inférence batch
* ``STGCNWrapper.predict_for_node(node_idx, recent_speeds)`` — inférence
  pour un nœud seul (utilisé par l'API routing/recommend)

Stratégie de fallback :

* Si torch / modèle manquant : retourne None → l'API fallback sur XGBoost
* Si erreur d'inférence : log + None (pas de crash API)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from training.stgcn.model import is_available

logger = logging.getLogger(__name__)


# Cache par horizon
_MODEL_CACHE: dict[int, STGCNWrapper] = {}


class STGCNWrapper:
    """Wrapper d'inférence pour le modèle SpatioTemporalGCN."""

    def __init__(
        self,
        horizon_min: int,
        model_dir: str | None = None,
    ):
        self.horizon_min = horizon_min
        # Double `or` pour que mypy comprenne que le résultat est toujours str.
        resolved_dir = model_dir or os.getenv("LYONFLOW_MODELS_DIR") or "/app/models"
        self.model_dir = Path(resolved_dir)
        self._model = None
        self._config: dict | None = None
        self._is_loaded = False

    @classmethod
    def get(cls, horizon_min: int) -> STGCNWrapper:
        """Retourne une instance cachée par horizon (singleton-like)."""
        if horizon_min not in _MODEL_CACHE:
            _MODEL_CACHE[horizon_min] = cls(horizon_min=horizon_min)
        return _MODEL_CACHE[horizon_min]

    def load(self) -> bool:
        """Charge le modèle depuis le disque. Retourne True si succès."""
        if not is_available():
            logger.warning("torch non disponible — STGCNWrapper.load() no-op")
            return False

        model_path = self.model_dir / f"stgcn_h{self.horizon_min}.pt"
        if not model_path.exists():
            logger.info("STGCN H+%dmin non trouvé à %s — fallback XGBoost", self.horizon_min, model_path)
            return False

        try:
            import torch

            from training.stgcn.model import build_module

            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            self._config = ckpt["config"]
            self._model = build_module(_config_to_stgcn_config(self._config))
            assert self._model is not None  # narrow pour mypy
            self._model.load_state_dict(ckpt["state_dict"])
            self._model.eval()
            self._is_loaded = True
            logger.info(
                "STGCN H+%dmin loaded (%d params)", self.horizon_min, sum(p.numel() for p in self._model.parameters())
            )
            return True
        except Exception as e:  # pragma: no cover
            logger.exception("Failed to load STGCN H+%dmin: %s", self.horizon_min, e)
            self._is_loaded = False
            return False

    def predict(
        self,
        features: np.ndarray,
        edge_index: np.ndarray,
    ) -> np.ndarray | None:
        """Prédit la vitesse future pour tous les nœuds.

        Args:
            features: np.ndarray ``(batch, seq_len, num_nodes, in_channels)``.
            edge_index: np.ndarray ``(2, num_edges)``.

        Returns:
            np.ndarray ``(batch, num_nodes)`` ou None si modèle pas chargé.
        """
        if not self._is_loaded and not self.load():
            return None

        try:
            import torch

            assert self._model is not None  # narrow pour mypy (load() OK ci-dessus)
            with torch.no_grad():
                x = torch.from_numpy(features).float()
                ei = torch.from_numpy(edge_index).long()
                pred = self._model(x, ei)  # (B, N, 1)
                return pred.squeeze(-1).numpy()
        except Exception as e:  # pragma: no cover
            logger.exception("STGCN inference failed: %s", e)
            return None

    def predict_for_node(
        self,
        node_idx: int,
        recent_features: np.ndarray,
        edge_index: np.ndarray,
    ) -> float | None:
        """Prédit la vitesse future pour UN nœud.

        Args:
            node_idx: Index du nœud.
            recent_features: ``(seq_len, num_nodes, in_channels)`` ou
                ``(num_nodes, in_channels)``.
            edge_index: np.ndarray ``(2, num_edges)``.

        Returns:
            Vitesse prédite (km/h non normalisée) ou None.
        """
        if recent_features.ndim == 3:
            recent_features = recent_features[np.newaxis, ...]  # ajouter batch
        pred = self.predict(recent_features, edge_index)
        if pred is None:
            return None
        speed_norm = float(pred[0, node_idx])
        return speed_norm * 130.0  # dénormalisation

    @property
    def is_available(self) -> bool:
        return self._is_loaded


def _config_to_stgcn_config(d: dict):
    """Convertit un dict de config en STGCNConfig."""
    from training.stgcn.model import STGCNConfig

    return STGCNConfig(
        in_channels=d.get("in_channels", 5),
        hidden_channels=d.get("hidden_channels", 128),
        out_channels=d.get("out_channels", 1),
        num_nodes=d.get("num_nodes", 1520),
        seq_len=d.get("seq_len", 12),
        dropout=d.get("dropout", 0.1),
        gcn_layers=d.get("gcn_layers", 2),
        leaky_relu_slope=d.get("leaky_relu_slope", 0.2),
    )
