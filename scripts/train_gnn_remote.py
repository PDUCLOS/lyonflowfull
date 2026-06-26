"""GNN training autonome pour OVH AI Training.

Lit les Parquet depuis /data (monté via ovhai), entraîne SpatioTemporalGCN,
sauve le checkpoint dans /output (rapatrié par le script orchestrateur).

Usage dans le container GPU :
    python train_gnn_remote.py [--epochs 100] [--lr 0.001] [--horizon 60]

Le script est self-contained : pas de dépendance à src.db ni MLflow.
Toute la data vient des Parquet, le tracking est local (JSON).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("/data")
OUTPUT_DIR = Path("/output")


def load_data(days_dir: Path | None = None):
    src = days_dir or DATA_DIR
    logger.info("Loading data from %s", src)

    features = pd.read_parquet(src / "features.parquet")
    adjacency = pd.read_parquet(src / "adjacency.parquet")

    edge_index = torch.tensor(
        np.stack([adjacency["node_u"].values, adjacency["node_v"].values]),
        dtype=torch.long,
    )

    ts = pd.to_datetime(features["timestamp"])
    hours = ts.dt.hour + ts.dt.minute / 60.0
    days = ts.dt.dayofweek
    features["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
    features["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)
    features["day_sin"] = np.sin(2 * np.pi * days / 7.0)
    features["day_cos"] = np.cos(2 * np.pi * days / 7.0)
    features["speed_norm"] = (features["speed_kmh"].clip(0, 130) / 130.0).astype(float)

    n_nodes = features["node_idx"].nunique()
    n_edges = edge_index.shape[1]
    logger.info("Loaded %d rows, %d nodes, %d edges", len(features), n_nodes, n_edges)

    return features, edge_index, n_nodes


def build_tensors(df: pd.DataFrame, seq_len: int, horizon_steps: int):
    pivot = df.pivot_table(index="timestamp", columns="node_idx", values="speed_norm", aggfunc="mean")
    timestamps = pivot.index
    n_t, n_nodes = pivot.shape

    feature_arrays = [pivot.values]
    for col in ["hour_sin", "hour_cos", "day_sin", "day_cos"]:
        per_ts = df.drop_duplicates("timestamp").set_index("timestamp")[col]
        per_ts = per_ts.reindex(timestamps).values
        feature_arrays.append(np.broadcast_to(per_ts[:, None], (n_t, n_nodes)).copy())

    full = np.stack(feature_arrays, axis=-1).astype(np.float32)
    full = np.nan_to_num(full, nan=0.0)

    total = seq_len + horizon_steps
    if n_t < total:
        raise ValueError(f"Not enough timesteps ({n_t}) for seq_len+horizon={total}")

    n_samples = n_t - total + 1
    X = np.zeros((n_samples, seq_len, n_nodes, 5), dtype=np.float32)
    Y = np.zeros((n_samples, n_nodes), dtype=np.float32)

    for i in range(n_samples):
        X[i] = full[i : i + seq_len]
        Y[i] = full[i + seq_len + horizon_steps - 1, :, 0]

    return X, Y


def build_model(n_nodes: int, hidden: int = 128, seq_len: int = 12):
    from torch_geometric.nn import GCNConv

    class STGCN(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(input_size=5, hidden_size=hidden, batch_first=True)
            self.gcn1 = GCNConv(hidden, hidden)
            self.gcn2 = GCNConv(hidden, hidden)
            self.norm1 = nn.LayerNorm(hidden)
            self.norm2 = nn.LayerNorm(hidden)
            self.head = nn.Linear(hidden, 1)
            self.act = nn.LeakyReLU(0.2)
            self.drop = nn.Dropout(0.1)

        def forward(self, x, edge_index):
            if x.dim() == 3:
                x = x.unsqueeze(1)
            b, t, n, c = x.shape
            h = x.reshape(b * n, t, c)
            h, _ = self.gru(h)
            h = h[:, -1, :].reshape(b, n, hidden)
            h = h.reshape(b * n, hidden)

            ei = edge_index
            if b > 1:
                ei = torch.cat([edge_index + i * n for i in range(b)], dim=1)

            identity = h
            h = self.gcn1(h, ei)
            h = self.act(h)
            h = self.drop(h)
            h = self.norm1(h)
            h = h + identity

            identity = h
            h = self.gcn2(h, ei)
            h = self.act(h)
            h = self.drop(h)
            h = self.norm2(h)
            h = h + identity

            return self.head(h).reshape(b, n, 1)

    return STGCN()


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)
    if device.type == "cuda":
        logger.info("GPU: %s", torch.cuda.get_device_name(0))

    features, edge_index, n_nodes = load_data(Path(args.data_dir) if args.data_dir else None)
    edge_index = edge_index.to(device)

    horizon_steps = args.horizon_min // 5
    logger.info("Building tensors (seq_len=%d, horizon=%d steps)...", args.seq_len, horizon_steps)
    X, Y = build_tensors(features, args.seq_len, horizon_steps)

    split = int(len(X) * 0.8)
    X_train, Y_train = X[:split], Y[:split]
    X_val, Y_val = X[split:], Y[split:]
    logger.info("Train: %d, Val: %d samples", len(X_train), len(X_val))

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(Y_train)),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(Y_val)),
        batch_size=args.batch_size,
    )

    model = build_model(n_nodes, args.hidden, args.seq_len).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model: %d parameters", n_params)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    loss_fn = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None
    patience = 0
    history = []

    t0 = time.time()
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb, edge_index).squeeze(-1)
            loss = loss_fn(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(xb)
        train_loss /= len(X_train)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb, edge_index).squeeze(-1)
                val_loss += loss_fn(pred, yb).item() * len(xb)
        val_loss /= len(X_val)
        scheduler.step(val_loss)

        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

        if epoch % 10 == 0 or epoch == args.epochs - 1:
            logger.info(
                "Epoch %3d/%d  train=%.5f  val=%.5f  lr=%.1e",
                epoch,
                args.epochs,
                train_loss,
                val_loss,
                optimizer.param_groups[0]["lr"],
            )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= args.patience:
                logger.info("Early stopping at epoch %d", epoch)
                break

    elapsed = time.time() - t0
    logger.info("Training done in %.1fs. Best val_loss=%.5f", elapsed, best_val_loss)

    # Compute MAE on val set (denormalized)
    model.load_state_dict(best_state)
    model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for xb, yb in val_loader:
            xb = xb.to(device)
            pred = model(xb, edge_index).squeeze(-1).cpu().numpy()
            preds.append(pred)
            trues.append(yb.numpy())
    preds = np.concatenate(preds) * 130.0
    trues = np.concatenate(trues) * 130.0
    mae = float(np.mean(np.abs(preds - trues)))
    rmse = float(np.sqrt(np.mean((preds - trues) ** 2)))
    logger.info("Val MAE=%.2f km/h, RMSE=%.2f km/h", mae, rmse)

    # Save
    out = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / f"stgcn_h{args.horizon_min}.pt"
    torch.save(
        {
            "config": {
                "in_channels": 5,
                "hidden_channels": args.hidden,
                "out_channels": 1,
                "num_nodes": n_nodes,
                "seq_len": args.seq_len,
                "dropout": 0.1,
                "gcn_layers": 2,
                "leaky_relu_slope": 0.2,
            },
            "state_dict": best_state,
            "metrics": {"mae": mae, "rmse": rmse, "val_loss": best_val_loss},
        },
        model_path,
    )
    logger.info("Model saved: %s", model_path)

    meta = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "horizon_min": args.horizon_min,
        "n_nodes": n_nodes,
        "n_edges": edge_index.shape[1],
        "n_params": n_params,
        "epochs_run": len(history),
        "best_val_loss": best_val_loss,
        "mae_kmh": mae,
        "rmse_kmh": rmse,
        "elapsed_seconds": round(elapsed, 1),
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else "none",
    }
    (out / "train_meta.json").write_text(json.dumps(meta, indent=2))
    logger.info("Metadata saved: %s", out / "train_meta.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train SpatioTemporalGCN on OVH AI Training")
    parser.add_argument("--data-dir", default=None, help="Override /data mount path")
    parser.add_argument("--output-dir", default=None, help="Override /output mount path")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--seq-len", type=int, default=12)
    parser.add_argument("--horizon-min", type=int, default=60)
    parser.add_argument("--patience", type=int, default=10)
    args = parser.parse_args()
    train(args)
