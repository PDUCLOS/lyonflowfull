"""Training loop pour SpatioTemporalGCN — MLflow tracking + sauvegarde modèle.

Workflow :
1. Charger dataset (DB Gold ou synthetic fallback).
2. Split train/val temporel (80/20).
3. Construire le modèle.
4. Boucle d'entraînement (Adam + MSELoss + LR scheduler).
5. Log métriques dans MLflow (MAE, RMSE, MAPE, params, model artifact).
6. Sauvegarder le modèle final + early stopping.

Conventions Sprint 7 :
* Quality gate : MAE ≤ prev_mae × 1.15 (réutilise le pattern XGBoost).
* MLflow run name : ``stgcn_{horizon}_{YYYYMMDD}``.
* Le run parent s'appelle ``stgcn_traffic`` et les enfants sont les horizons.

Sprint 9 — Refactor : utilise ``src.ml.mlflow_integration.MLflowTracker``
au lieu du stub inline. Tracking unifié XGBoost + GNN.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from training.stgcn.dataset import DatasetConfig, STGCNDataset
from training.stgcn.model import STGCNConfig, is_available

logger = logging.getLogger(__name__)


def _make_tracker():
    """Lazy import pour éviter circularité."""
    from src.ml.mlflow_integration import MLflowTracker

    return MLflowTracker(experiment_name="stgcn_traffic")


# -----------------------------------------------------------------------------
# Quality gate
# -----------------------------------------------------------------------------


class QualityGateError(RuntimeError):
    """Levée quand la qualité du nouveau modèle est insuffisante."""


def check_quality_gate(new_mae: float, prev_mae: float | None, tolerance: float = 0.15) -> bool:
    """Vérifie que new_mae ≤ prev_mae × (1 + tolerance).

    Args:
        new_mae: MAE du modèle fraîchement entraîné.
        prev_mae: MAE du modèle précédent (None = pas de précédent, on accepte).
        tolerance: Pourcentage d'augmentation acceptée (défaut 15%).

    Returns:
        True si le modèle passe le quality gate.

    Raises:
        QualityGateError: si le gate échoue et qu'on doit rejeter le modèle.
    """
    if prev_mae is None:
        logger.info("No previous model — accepting new model (MAE=%.3f)", new_mae)
        return True

    threshold = prev_mae * (1 + tolerance)
    if new_mae <= threshold:
        logger.info("Quality gate passed: new_mae=%.3f ≤ threshold=%.3f", new_mae, threshold)
        return True

    msg = (
        f"Quality gate FAILED: new_mae={new_mae:.3f} > threshold={threshold:.3f} "
        f"(prev_mae={prev_mae:.3f} × {1 + tolerance:.2f})"
    )
    logger.error(msg)
    raise QualityGateError(msg)


# -----------------------------------------------------------------------------
# Métriques
# -----------------------------------------------------------------------------


def compute_metrics(y_pred: np.ndarray, y_true: np.ndarray) -> dict[str, float]:
    """Calcule MAE, RMSE, MAPE, R².

    Args:
        y_pred: Prédictions shape ``(N,)`` ou ``(N, ...)``.
        y_true: Targets shape identique.

    Returns:
        Dict avec mae, rmse, mape_pct, r2.
    """
    y_pred = np.asarray(y_pred).flatten()
    y_true = np.asarray(y_true).flatten()
    err = y_pred - y_true

    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    # MAPE : éviter division par 0
    nonzero = np.abs(y_true) > 1e-6
    mape = float(np.mean(np.abs(err[nonzero] / y_true[nonzero])) * 100) if nonzero.any() else 0.0
    # R²
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {"mae": mae, "rmse": rmse, "mape_pct": mape, "r2": r2}


# -----------------------------------------------------------------------------
# Trainer
# -----------------------------------------------------------------------------


class STGCNTrainer:
    """Trainer GNN avec MLflow tracking.

    Example::

        trainer = STGCNTrainer(
            dataset=STGCNDataset.synthetic(num_nodes=50),
            config=STGCNConfig(num_nodes=50, hidden_channels=32),
            horizons=(60,),
        )
        results = trainer.train_all()
        # results = {"h60": {"mae": 0.05, "rmse": 0.08, ...}}
    """

    DEFAULT_HORIZONS_MIN = (5, 15, 30, 60, 180, 360)
    """6 horizons matching CLAUDE.md spec."""

    def __init__(
        self,
        dataset: STGCNDataset,
        config: STGCNConfig | None = None,
        horizons: tuple[int, ...] = DEFAULT_HORIZONS_MIN,
        mlflow_experiment: str = "stgcn_traffic",
        model_dir: str | None = None,
        learning_rate: float = 1e-3,
        batch_size: int = 16,
        epochs: int = 50,
        early_stopping_patience: int = 5,
    ):
        if not is_available():
            raise RuntimeError("STGCNTrainer requires torch + torch_geometric. pip install torch torch-geometric")

        self.dataset = dataset
        self.config = config or STGCNConfig(num_nodes=dataset.X.shape[2])
        self.horizons = horizons
        self.mlflow_experiment = mlflow_experiment
        default_models_dir = os.getenv("LYONFLOW_MODELS_DIR", "/app/models")
        self.model_dir = Path(model_dir or default_models_dir)
        try:
            self.model_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # Hors VPS/Docker (/app non writable) — fallback tempdir
            import tempfile

            self.model_dir = Path(tempfile.gettempdir()) / "lyonflow_models"
            self.model_dir.mkdir(parents=True, exist_ok=True)
            logger.warning("model_dir %s non writable, fallback %s", default_models_dir, self.model_dir)
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epochs = epochs
        self.early_stopping_patience = early_stopping_patience

        # Split temporel 80/20
        n = len(dataset)
        split = int(n * 0.8)
        self._train_idx = slice(0, split)
        self._val_idx = slice(split, n)

    def _load_prev_mae(self, horizon_min: int) -> float | None:
        """Charge le MAE du modele precedent depuis le checkpoint (None si absent)."""
        import torch

        model_path = self.model_dir / f"stgcn_h{horizon_min}.pt"
        if not model_path.exists():
            return None
        try:
            ckpt = torch.load(str(model_path), map_location="cpu", weights_only=False)
            metrics = ckpt.get("metrics", {})
            return float(metrics.get("mae")) if metrics.get("mae") is not None else None
        except Exception as exc:
            logger.warning("Impossible de charger prev_mae depuis %s: %s", model_path, exc)
            return None

    def train_one(self, horizon_min: int) -> dict:
        """Entraîne un seul horizon.

        Args:
            horizon_min: Horizon cible en minutes (sera converti en
                timesteps selon le sample_step 5 min).

        Returns:
            Dict avec mae, rmse, mape_pct, r2, mlflow_run_id.
        """
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        from training.stgcn.model import build_module

        horizon_steps = horizon_min // 5  # 5 min = sample step
        logger.info("=== Train STGCN H+%dmin (%d steps) ===", horizon_min, horizon_steps)

        # Reconstruire le dataset avec ce horizon
        cfg = DatasetConfig(
            seq_len=self.dataset.config.seq_len,
            horizon=horizon_steps,
            in_channels=self.dataset.config.in_channels,
        )
        # Si horizon différent de celui du dataset, reconstruire
        if horizon_steps != self.dataset.config.horizon:
            from training.stgcn.dataset import build_tensors_from_df

            # Reload synthetic ou DB
            if hasattr(self.dataset, "_df") and self.dataset._df is not None:
                X, edge_index, Y = build_tensors_from_df(self.dataset._df, self.dataset.edge_index, config=cfg)
            else:
                # Re-synthetic avec ce horizon
                ds = STGCNDataset.synthetic(
                    num_nodes=self.dataset.X.shape[2], seq_len=cfg.seq_len, horizon=horizon_steps
                )
                X, edge_index, Y = ds.tensors()
        else:
            X, edge_index, Y = self.dataset.tensors()

        # Split
        n = len(X)
        split = int(n * 0.8)
        X_train, Y_train = X[:split], Y[:split]
        X_val, Y_val = X[split:], Y[split:]

        logger.info("Train: %d samples, Val: %d samples", len(X_train), len(X_val))

        # DataLoaders
        train_ds = TensorDataset(
            torch.from_numpy(X_train).float(),
            torch.from_numpy(Y_train).float(),
        )
        val_ds = TensorDataset(
            torch.from_numpy(X_val).float(),
            torch.from_numpy(Y_val).float(),
        )
        train_loader = DataLoader(train_ds, batch_size=self.batch_size, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=self.batch_size, shuffle=False)

        # Edge index (constant) → torch
        edge_index_t = torch.from_numpy(edge_index).long()

        # Model
        cfg_model = STGCNConfig(
            num_nodes=self.config.num_nodes,
            hidden_channels=self.config.hidden_channels,
            seq_len=self.config.seq_len,
            in_channels=self.config.in_channels,
        )
        model = build_module(cfg_model)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)
        loss_fn = nn.MSELoss()

        # MLflow tracking via tracker centralisé (Sprint 9)
        tracker = _make_tracker()
        run_name = f"stgcn_h{horizon_min}_{time.strftime('%Y%m%d_%H%M%S')}"
        try:
            best_mae = float("inf")
            best_state = None
            patience_counter = 0

            with tracker.start_run(run_name=run_name) as _run:
                tracker.set_tag("model", "stgcn")
                tracker.set_tag("horizon_min", str(horizon_min))
                for epoch in range(self.epochs):
                    t0 = time.time()
                    # Train
                    model.train()
                    train_loss = 0.0
                    for xb, yb in train_loader:
                        optimizer.zero_grad()
                        pred = model(xb, edge_index_t)  # (B, N, 1)
                        pred = pred.squeeze(-1)  # (B, N)
                        loss = loss_fn(pred, yb)
                        loss.backward()
                        optimizer.step()
                        train_loss += loss.item() * len(xb)
                    train_loss /= len(X_train)

                    # Val
                    model.eval()
                    val_preds: list[np.ndarray] = []
                    val_targets: list[np.ndarray] = []
                    with torch.no_grad():
                        for xb, yb in val_loader:
                            pred = model(xb, edge_index_t).squeeze(-1)
                            val_preds.append(pred.numpy())
                            val_targets.append(yb.numpy())
                    val_preds_arr = np.concatenate(val_preds, axis=0)
                    val_targets_arr = np.concatenate(val_targets, axis=0)
                    metrics = compute_metrics(val_preds_arr, val_targets_arr)
                    # metrics reste dict[str, float] — pas d'enrichissement ici
                    scheduler.step(metrics["mae"])
                    elapsed = time.time() - t0

                    logger.info(
                        "Epoch %d/%d — train_loss=%.4f val_mae=%.4f val_rmse=%.4f (%.1fs)",
                        epoch + 1,
                        self.epochs,
                        train_loss,
                        metrics["mae"],
                        metrics["rmse"],
                        elapsed,
                    )

                    # MLflow log
                    tracker.log_metrics(
                        {
                            "train_loss": train_loss,
                            "val_mae": metrics["mae"],
                            "val_rmse": metrics["rmse"],
                            "val_mape_pct": metrics["mape_pct"],
                            "val_r2": metrics["r2"],
                            "lr": optimizer.param_groups[0]["lr"],
                        },
                        step=epoch,
                    )

                    # Early stopping
                    if metrics["mae"] < best_mae:
                        best_mae = metrics["mae"]
                        best_state = {k: v.clone() for k, v in model.state_dict().items()}
                        patience_counter = 0
                    else:
                        patience_counter += 1
                        if patience_counter >= self.early_stopping_patience:
                            logger.info("Early stopping at epoch %d", epoch + 1)
                            break

                # Restore best (inside context manager)
                if best_state is not None:
                    model.load_state_dict(best_state)

                # Final metrics
                model.eval()
                with torch.no_grad():
                    final_preds: list[np.ndarray] = []
                    final_targets: list[np.ndarray] = []
                    for xb, yb in val_loader:
                        pred = model(xb, edge_index_t).squeeze(-1)
                        final_preds.append(pred.numpy())
                        final_targets.append(yb.numpy())
                final_metrics: dict[str, Any] = dict(
                    compute_metrics(np.concatenate(final_preds), np.concatenate(final_targets))
                )

                # Save model
                model_path = self.model_dir / f"stgcn_h{horizon_min}.pt"
                torch.save(
                    {
                        "config": asdict(cfg_model),
                        "state_dict": model.state_dict(),
                        "metrics": final_metrics,
                    },
                    model_path,
                )
                logger.info("Saved STGCN H+%dmin to %s (MAE=%.4f)", horizon_min, model_path, final_metrics["mae"])

                # Quality gate
                prev_mae = self._load_prev_mae(horizon_min)
                try:
                    check_quality_gate(final_metrics["mae"], prev_mae)
                    tracker.log_metrics({"quality_gate_pass": 1.0})
                except QualityGateError:
                    tracker.log_metrics({"quality_gate_pass": 0.0})
                    if os.getenv("LYONFLOW_STRICT_QUALITY", "false").lower() == "true":
                        raise
                    logger.warning("Quality gate failed but continuing (LYONFLOW_STRICT_QUALITY=false)")

                tracker.log_artifact(str(model_path))
                tracker.log_params(
                    {
                        "horizon_min": horizon_min,
                        "horizon_steps": horizon_steps,
                        "num_nodes": cfg_model.num_nodes,
                        "hidden_channels": cfg_model.hidden_channels,
                        "seq_len": cfg_model.seq_len,
                        "epochs_trained": self.epochs,
                        "batch_size": self.batch_size,
                        "lr": self.learning_rate,
                        "model_version": "0.3.0",
                    },
                )

                final_metrics["mlflow_run_id"] = tracker.run_id or "no_mlflow"
                final_metrics["model_path"] = str(model_path)
                return final_metrics
        except Exception as e:
            logger.exception("Training failed for H+%dmin: %s", horizon_min, e)
            raise

    def train_all(self) -> dict[int, dict]:
        """Entraîne tous les horizons déclarés.

        Returns:
            Dict {horizon_min: metrics_dict}.
        """
        results: dict[int, dict] = {}
        for h in self.horizons:
            try:
                results[h] = self.train_one(horizon_min=h)
            except Exception as e:
                logger.exception("H+%dmin failed: %s", h, e)
                results[h] = {"error": str(e)}
        return results
