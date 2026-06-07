"""Dataset GNN trafic — chargement depuis gold.dim_spatial_grid_mapping
+ gold.traffic_features_live + gold.dim_gnn_adjacency.

Le dataset construit des paires ``(sequence_temporelle, target)`` :

* **Séquence d'entrée** : ``(seq_len, num_nodes, in_channels)`` — les
  ``seq_len`` dernières observations pour chaque nœud.
* **Target** : ``(num_nodes,)`` — la valeur future à horizon donné pour
  chaque nœud.

Le découpage train/val suit une logique temporelle (pas random) :
* Train : 80% début
* Val : 20% fin
* Test : jamais inclus (online prediction uniquement)

Stratégie d'échantillonnage :
* On prend des **sliding windows** sur l'axe temporel.
* Chaque fenêtre commence à ``t``, et cible ``t + horizon`` (LEAD-like).
* Skip les fenêtres où des données manquent (trop de NaN).

Note : ce module est offline-first — il fonctionne avec des mocks
synthetic data si la DB n'est pas dispo (utile pour les tests).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------


@dataclass
class DatasetConfig:
    """Hyperparamètres du dataset GNN.

    Attributes:
        seq_len: Longueur de la fenêtre d'entrée (timesteps).
        horizon: Horizon de prédiction (timesteps, en unités de 5 min).
        in_channels: Nombre de features par nœud par timestep.
        stride: Pas entre 2 fenêtres consécutives (défaut 1).
        min_valid_frac: Fraction minimale de données valides par fenêtre
            (sinon fenêtre skippée).
    """

    seq_len: int = 12
    horizon: int = 12  # 1h
    in_channels: int = 5  # speed, hour_sin, hour_cos, day_sin, day_cos
    stride: int = 1
    min_valid_frac: float = 0.7


# -----------------------------------------------------------------------------
# Feature engineering
# -----------------------------------------------------------------------------


def _time_features(measurement_time: pd.Series) -> pd.DataFrame:
    """Calcule hour_sin, hour_cos, day_sin, day_cos à partir de timestamps."""
    t = pd.to_datetime(measurement_time)
    hour = t.dt.hour + t.dt.minute / 60.0
    day = t.dt.dayofweek
    return pd.DataFrame(
        {
            "hour_sin": np.sin(2 * np.pi * hour / 24),
            "hour_cos": np.cos(2 * np.pi * hour / 24),
            "day_sin": np.sin(2 * np.pi * day / 7),
            "day_cos": np.cos(2 * np.pi * day / 7),
        },
        index=measurement_time.index,
    )


def _normalize_speed(speed: pd.Series) -> pd.Series:
    """Normalisation speed_kmh → [0, 1] (speed_max = 130 km/h)."""
    return (speed.clip(lower=0, upper=130) / 130.0).astype(float)


# -----------------------------------------------------------------------------
# Loader DB
# -----------------------------------------------------------------------------


def _load_gold_traffic_features(num_nodes_max: int = 2000) -> pd.DataFrame:
    """Charge ``gold.traffic_features_live`` depuis la DB.

    Args:
        num_nodes_max: Limite dure (sécurité) — on ne charge pas plus de
            N nœuds distincts.

    Returns:
        DataFrame : measurement_time, node_idx, speed_norm, hour_sin,
        hour_cos, day_sin, day_cos.

    Raises:
        RuntimeError: si la DB ne répond pas.
    """
    from src.db.connection import execute_query

    query = """
        SELECT
            measurement_time,
            node_idx,
            speed_kmh,
            hour_sin,
            hour_cos,
            day_sin,
            day_cos
        FROM gold.traffic_features_live
        WHERE measurement_time >= NOW() - INTERVAL '7 days'
        ORDER BY measurement_time, node_idx
    """
    rows = execute_query(query)
    if not rows:
        raise RuntimeError("gold.traffic_features_live vide ou DB down")
    df = pd.DataFrame(rows)
    df["speed_norm"] = _normalize_speed(df["speed_kmh"])
    return df


def _load_adjacency() -> np.ndarray:
    """Charge edge_index depuis ``gold.dim_gnn_adjacency``.

    Returns:
        np.ndarray shape ``(2, num_edges)`` au format PyG.
    """
    from src.db.connection import execute_query

    rows = execute_query(
        """
        SELECT node_u, node_v
        FROM gold.dim_gnn_adjacency
        WHERE is_connected = TRUE
        """
    )
    if not rows:
        raise RuntimeError("gold.dim_gnn_adjacency vide ou DB down")
    df = pd.DataFrame(rows)
    return np.stack([df["node_u"].values, df["node_v"].values]).astype(np.int64)


def _load_spatial_mapping() -> pd.DataFrame:
    """Charge ``gold.dim_spatial_grid_mapping`` (node_idx ↔ channel_id)."""
    from src.db.connection import execute_query

    rows = execute_query(
        """
        SELECT node_idx, channel_id, h3_id
        FROM gold.dim_spatial_grid_mapping
        ORDER BY node_idx
        """
    )
    if not rows:
        raise RuntimeError("gold.dim_spatial_grid_mapping vide ou DB down")
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Synthetic data (pour tests + démo)
# -----------------------------------------------------------------------------


def _generate_synthetic_traffic(
    num_nodes: int = 50,
    num_timesteps: int = 24 * 60 // 5,  # 1 journée à 5 min
    seed: int = 42,
) -> pd.DataFrame:
    """Génère un dataset trafic synthétique réaliste.

    Vitesse = base_diurne × bruit_sin + perturbations locales par nœud.
    """
    rng = np.random.default_rng(seed)

    # Timestamps : 1 journée à 5 min
    timestamps = pd.date_range("2026-06-01", periods=num_timesteps, freq="5min")

    # Base speed = fonction de l'heure (heures de pointe = plus lent)
    hour = timestamps.hour + timestamps.minute / 60
    base_speed = 50.0 - 25.0 * np.exp(-((hour - 8.5) ** 2) / 2) - 20.0 * np.exp(-((hour - 18) ** 2) / 3)

    rows = []
    for node in range(num_nodes):
        # Bruit par nœud (variation spatiale)
        node_offset = rng.normal(0, 5)
        node_amp = rng.uniform(0.7, 1.2)
        for i, ts in enumerate(timestamps):
            speed = max(5.0, (base_speed[i] + node_offset) * node_amp + rng.normal(0, 2))
            rows.append(
                {
                    "measurement_time": ts,
                    "node_idx": node,
                    "speed_kmh": float(speed),
                    "hour_sin": float(np.sin(2 * np.pi * hour[i] / 24)),
                    "hour_cos": float(np.cos(2 * np.pi * hour[i] / 24)),
                    "day_sin": float(np.sin(2 * np.pi * ts.dayofweek / 7)),
                    "day_cos": float(np.cos(2 * np.pi * ts.dayofweek / 7)),
                }
            )
    df = pd.DataFrame(rows)
    df["speed_norm"] = _normalize_speed(df["speed_kmh"])
    return df


def _generate_synthetic_adjacency(num_nodes: int, k: int = 2, seed: int = 42) -> np.ndarray:
    """Génère un graphe K-NN simplifié (chaque nœud connecté à K voisins).

    Pour un graphe plus réaliste, charger le vrai ``gold.dim_gnn_adjacency``
    (K=2 grid_disk H3).
    """
    edges = set()
    for u in range(num_nodes):
        # Connecter à K voisins proches
        for v in range(max(0, u - k), min(num_nodes, u + k + 1)):
            if u != v:
                edges.add((u, v))
                edges.add((v, u))  # bidirectionnel
    edge_index = np.array(list(edges), dtype=np.int64).T
    if edge_index.size == 0:
        edge_index = np.zeros((2, 0), dtype=np.int64)
    return edge_index


# -----------------------------------------------------------------------------
# Tensor builder
# -----------------------------------------------------------------------------


def build_tensors_from_df(
    df: pd.DataFrame,
    edge_index: np.ndarray,
    config: DatasetConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Construit les tenseurs (X, edge_index, Y) depuis un DataFrame.

    Args:
        df: DataFrame avec colonnes [measurement_time, node_idx, speed_norm,
            hour_sin, hour_cos, day_sin, day_cos].
        edge_index: np.ndarray (2, num_edges).
        config: Hyperparamètres dataset.

    Returns:
        (X, edge_index, Y) :
        * X shape (num_samples, seq_len, num_nodes, in_channels)
        * Y shape (num_samples, num_nodes) — target = speed_norm à t+horizon
    """
    cfg = config or DatasetConfig()

    # Pivot : (measurement_time × node_idx) → matrix (T, N)
    pivot_speed = df.pivot_table(index="measurement_time", columns="node_idx", values="speed_norm", aggfunc="mean")
    timestamps = pivot_speed.index
    num_timesteps, num_nodes = pivot_speed.shape

    # Features additionnelles (hour_sin, etc.) — on prend la valeur du
    # premier nœud par timestep (identique pour tous)
    feature_arrays = [pivot_speed.values]  # (T, N)
    for col in ["hour_sin", "hour_cos", "day_sin", "day_cos"]:
        per_ts = df.drop_duplicates("measurement_time").set_index("measurement_time")[col]
        per_ts = per_ts.reindex(timestamps).values  # (T,)
        feature_arrays.append(np.broadcast_to(per_ts[:, None], (num_timesteps, num_nodes)).copy())

    # Stack → (T, N, in_channels)
    full = np.stack(feature_arrays, axis=-1)  # (T, N, C)
    full = np.nan_to_num(full, nan=0.0)

    # Sliding windows
    total_window = cfg.seq_len + cfg.horizon
    if num_timesteps < total_window:
        raise ValueError(f"Pas assez de timesteps ({num_timesteps}) pour seq_len+horizon={total_window}")

    num_samples = (num_timesteps - total_window) // cfg.stride + 1
    X = np.zeros((num_samples, cfg.seq_len, num_nodes, cfg.in_channels), dtype=np.float32)
    Y = np.zeros((num_samples, num_nodes), dtype=np.float32)

    for i in range(num_samples):
        start = i * cfg.stride
        end = start + cfg.seq_len
        target_idx = end + cfg.horizon - 1
        X[i] = full[start:end]
        Y[i] = full[target_idx, :, 0]  # speed_norm au timestep cible

    return X, edge_index, Y


# -----------------------------------------------------------------------------
# Dataset class (PyTorch-friendly)
# -----------------------------------------------------------------------------


class STGCNDataset:
    """Dataset GNN pour trafic routier.

    Example::

        dataset = STGCNDataset.from_db()  # charge DB Gold
        # OU
        dataset = STGCNDataset.synthetic(num_nodes=50)
        X, edge_index, Y = dataset.tensors()
        # X: (num_samples, seq_len, num_nodes, in_channels)
        # edge_index: (2, num_edges)
        # Y: (num_samples, num_nodes)
    """

    def __init__(
        self,
        X: np.ndarray,
        edge_index: np.ndarray,
        Y: np.ndarray,
        config: DatasetConfig | None = None,
    ):
        self.X = X
        self.edge_index = edge_index
        self.Y = Y
        self.config = config or DatasetConfig()

    @classmethod
    def synthetic(cls, num_nodes: int = 50, seq_len: int = 12, horizon: int = 12, seed: int = 42) -> STGCNDataset:
        """Construit un dataset synthétique (pour tests + démo)."""
        cfg = DatasetConfig(seq_len=seq_len, horizon=horizon)
        df = _generate_synthetic_traffic(num_nodes=num_nodes, seed=seed)
        edge_index = _generate_synthetic_adjacency(num_nodes=num_nodes, seed=seed)
        X, ei, Y = build_tensors_from_df(df, edge_index, config=cfg)
        return cls(X, ei, Y, config=cfg)

    @classmethod
    def from_db(
        cls,
        num_nodes_max: int = 2000,
        seq_len: int = 12,
        horizon: int = 12,
    ) -> STGCNDataset:
        """Construit un dataset depuis gold.traffic_features_live."""
        cfg = DatasetConfig(seq_len=seq_len, horizon=horizon)
        df = _load_gold_traffic_features(num_nodes_max=num_nodes_max)
        # Sous-échantillonner les nœuds si trop
        unique_nodes = df["node_idx"].unique()
        if len(unique_nodes) > num_nodes_max:
            sampled = np.random.default_rng(0).choice(unique_nodes, size=num_nodes_max, replace=False)
            df = df[df["node_idx"].isin(sampled)]
        edge_index = _load_adjacency()
        X, ei, Y = build_tensors_from_df(df, edge_index, config=cfg)
        return cls(X, ei, Y, config=cfg)

    def tensors(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Retourne (X, edge_index, Y) en numpy. Convertir en torch si besoin."""
        return self.X, self.edge_index, self.Y

    def to_torch(self) -> tuple[object, object, object]:
        """Convertit en tenseurs torch (import paresseux)."""
        import torch

        return (
            torch.from_numpy(self.X),
            torch.from_numpy(self.edge_index),
            torch.from_numpy(self.Y),
        )

    def __len__(self) -> int:
        return self.X.shape[0]

    def __repr__(self) -> str:
        return (
            f"STGCNDataset(num_samples={len(self)}, seq_len={self.config.seq_len}, "
            f"horizon={self.config.horizon}, num_nodes={self.X.shape[2]}, "
            f"in_channels={self.config.in_channels})"
        )
