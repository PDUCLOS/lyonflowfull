"""Tests pour SpatioTemporalGCN — skip proprement si torch indispo.

Couvre :
* Imports et détection d'environnement
* Architecture du modèle (forward pass shape)
* Dataset synthetic (sliding windows, edge_index)
* Trainer (boucle, métriques, quality gate)
* STGCNWrapper (load, predict, fallback)
* Persistance (save/load)

Les tests qui n'ont pas besoin de torch tournent toujours.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Permet l'import depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.stgcn import model as stgcn_model
from training.stgcn import train as stgcn_train
from training.stgcn.dataset import (
    DatasetConfig,
    STGCNDataset,
    _generate_synthetic_adjacency,
    _generate_synthetic_traffic,
    build_tensors_from_df,
)

requires_torch = pytest.mark.skipif(
    not stgcn_model.is_available(),
    reason="torch + torch_geometric non installés",
)


# =============================================================================
# Tests environment + model
# =============================================================================


@requires_torch
def test_is_available_returns_true():
    """Si on est ici, c'est que torch est dispo (skipif au-dessus)."""
    assert stgcn_model.is_available() is True


@requires_torch
def test_spatiotemporal_gcn_forward_shape():
    """Vérifie que le forward pass produit la bonne shape."""
    import torch

    from training.stgcn.model import SpatioTemporalGCN

    cfg = stgcn_model.STGCNConfig(
        num_nodes=20,
        hidden_channels=32,
        seq_len=6,
        in_channels=5,
        gcn_layers=2,
    )
    model = SpatioTemporalGCN(cfg)
    batch = 4
    x = torch.randn(batch, cfg.seq_len, cfg.num_nodes, cfg.in_channels)
    # Edge index : graphe complet (chaque nœud connecté à 2 voisins)
    edges = []
    for u in range(cfg.num_nodes):
        for v in range(max(0, u - 1), min(cfg.num_nodes, u + 2)):
            if u != v:
                edges.append((u, v))
    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    out = model.forward(x, edge_index)
    assert out.shape == (batch, cfg.num_nodes, cfg.out_channels)


@requires_torch
def test_spatiotemporal_gcn_num_params_positive():
    from training.stgcn.model import SpatioTemporalGCN

    cfg = stgcn_model.STGCNConfig(num_nodes=10, hidden_channels=16, seq_len=4, in_channels=3)
    model = SpatioTemporalGCN(cfg)
    assert model.num_parameters > 0


@requires_torch
def test_spatiotemporal_gcn_save_load(tmp_path):
    """Save puis load → doit donner les mêmes prédictions."""
    import torch

    from training.stgcn.model import SpatioTemporalGCN

    cfg = stgcn_model.STGCNConfig(num_nodes=10, hidden_channels=16, seq_len=4, in_channels=3)
    model = SpatioTemporalGCN(cfg)
    model.eval()
    save_path = tmp_path / "test_stgcn.pt"
    model.save(str(save_path))

    # Reload
    model2 = SpatioTemporalGCN(cfg)
    model2.load(str(save_path))
    model2.eval()

    x = torch.randn(2, cfg.seq_len, cfg.num_nodes, cfg.in_channels)
    edge_index = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]], dtype=torch.long)
    with torch.no_grad():
        out1 = model.forward(x, edge_index)
        out2 = model2.forward(x, edge_index)
    # Outputs doivent être identiques après save/load
    assert torch.allclose(out1, out2, atol=1e-5)


# =============================================================================
# Tests dataset
# =============================================================================


def test_synthetic_traffic_shape():
    df = _generate_synthetic_traffic(num_nodes=10, num_timesteps=50)
    assert len(df) == 10 * 50
    assert "speed_norm" in df.columns
    assert "hour_sin" in df.columns
    assert df["speed_norm"].between(0, 1).all()


def test_synthetic_adjacency_shape():
    ei = _generate_synthetic_adjacency(num_nodes=20, k=2)
    assert ei.shape[0] == 2  # 2 lignes (u, v)
    assert ei.shape[1] > 0  # au moins une arête
    assert ei.dtype == np.int64


def test_build_tensors_shape():
    df = _generate_synthetic_traffic(num_nodes=5, num_timesteps=100)
    ei = _generate_synthetic_adjacency(num_nodes=5)
    cfg = DatasetConfig(seq_len=10, horizon=5, in_channels=5)
    X, edge_index, Y = build_tensors_from_df(df, ei, config=cfg)
    assert X.ndim == 4
    assert X.shape[1] == 10  # seq_len
    assert X.shape[2] == 5   # num_nodes
    assert X.shape[3] == 5   # in_channels
    assert Y.shape == (X.shape[0], 5)  # (num_samples, num_nodes)
    assert edge_index.shape == ei.shape


def test_stgcn_dataset_synthetic():
    ds = STGCNDataset.synthetic(num_nodes=10, seq_len=6, horizon=3)
    assert len(ds) > 0
    X, _ei, Y = ds.tensors()
    assert X.shape[0] == len(ds)
    assert Y.shape[0] == len(ds)


def test_stgcn_dataset_repr():
    ds = STGCNDataset.synthetic(num_nodes=10, seq_len=6, horizon=3)
    r = repr(ds)
    assert "STGCNDataset" in r
    assert "num_nodes=10" in r


# =============================================================================
# Tests train (métrique, quality gate)
# =============================================================================


def test_compute_metrics_perfect_prediction():
    y = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    m = stgcn_train.compute_metrics(y, y)
    assert m["mae"] == 0.0
    assert m["rmse"] == 0.0
    assert m["mape_pct"] == 0.0
    assert m["r2"] == 1.0


def test_compute_metrics_noisy_prediction():
    y_true = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    y_pred = y_true + 0.01
    m = stgcn_train.compute_metrics(y_pred, y_true)
    assert 0 < m["mae"] < 0.05
    assert 0 < m["rmse"] < 0.05
    assert 0 < m["r2"] < 1.0


def test_quality_gate_no_previous():
    """Pas de modèle précédent → on accepte."""
    assert stgcn_train.check_quality_gate(0.05, None) is True


def test_quality_gate_pass():
    """new_mae ≤ prev × 1.15 → passe."""
    # prev=0.10, threshold=0.115, new=0.10 → passe
    assert stgcn_train.check_quality_gate(0.10, 0.10, tolerance=0.15) is True
    # prev=0.10, threshold=0.115, new=0.11 → passe (juste)
    assert stgcn_train.check_quality_gate(0.11, 0.10, tolerance=0.15) is True


def test_quality_gate_fail():
    """new_mae > prev × 1.15 → échoue (raise)."""
    with pytest.raises(stgcn_train.QualityGateError):
        stgcn_train.check_quality_gate(0.20, 0.10, tolerance=0.15)


# =============================================================================
# Tests trainer (1 epoch seulement pour vitesse)
# =============================================================================


@requires_torch
def test_trainer_one_epoch_smoke():
    """Smoke test : 1 epoch sur petit dataset synthetic."""
    from training.stgcn.train import STGCNTrainer

    ds = STGCNDataset.synthetic(num_nodes=10, seq_len=6, horizon=3)
    cfg = stgcn_model.STGCNConfig(num_nodes=10, hidden_channels=16, seq_len=6, in_channels=5)
    trainer = STGCNTrainer(
        dataset=ds,
        config=cfg,
        horizons=(15,),  # 1 horizon seulement
        epochs=1,
        batch_size=4,
        early_stopping_patience=1,
    )
    results = trainer.train_one(horizon_min=15)
    assert "mae" in results
    assert "rmse" in results
    assert results["mae"] >= 0


# =============================================================================
# Tests STGCNWrapper
# =============================================================================


def test_stgcn_wrapper_get_singleton():
    from src.models.stgcn_wrapper import STGCNWrapper

    w1 = STGCNWrapper.get(60)
    w2 = STGCNWrapper.get(60)
    assert w1 is w2  # singleton


@requires_torch
def test_stgcn_wrapper_load_if_exists(tmp_path, monkeypatch):
    """Si modèle existe → load OK. Sinon → load returns False."""
    from src.models.stgcn_wrapper import STGCNWrapper

    # Pas de modèle dans tmp_path → load doit retourner False
    w = STGCNWrapper(horizon_min=60, model_dir=str(tmp_path))
    assert w.load() is False
    assert w.is_available is False


def test_stgcn_wrapper_no_torch(monkeypatch):
    """Si torch indispo → predict retourne None."""
    from src.models.stgcn_wrapper import STGCNWrapper

    w = STGCNWrapper(horizon_min=60, model_dir="/nonexistent")
    # Force _is_loaded=False (load va skip)
    w._is_loaded = False
    # Mock is_available
    monkeypatch.setattr(stgcn_model, "is_available", lambda: False)
    result = w.predict(np.zeros((1, 6, 10, 5)), np.zeros((2, 0), dtype=np.int64))
    assert result is None
