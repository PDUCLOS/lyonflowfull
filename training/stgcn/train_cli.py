"""Standalone CLI pour entraîner le SpatioTemporalGCN sur EC2.

Ce script est conçu pour tourner sur une instance EC2 (ou n'importe
quelle machine avec GPU) SANS avoir besoin d'Airflow. Il est appelé soit :

* Manuellement par SSH pour un entraînement ponctuel
* Par un cron système sur l'instance EC2
* Par le DAG ``retrain_gnn`` sur VPS via SSH/subprocess distant
* Par un Step Function AWS ou un workflow GitHub Actions

## Usage

```bash
# Train par défaut (tous les horizons)
python -m training.stgcn.train_cli

# Train un horizon spécifique
python -m training.stgcn.train_cli --horizon 60

# Train sur DB réelle (par défaut: synthetic si DB down)
python -m training.stgcn.train_cli --use-db

# Custom epochs / batch size
python -m training.stgcn.train_cli --epochs 100 --batch-size 32

# Upload modèle vers S3 après training
python -m training.stgcn.train_cli --upload-s3 s3://my-bucket/models/

# Notification Slack en fin de training
python -m training.stgcn.train_cli --slack-webhook $SLACK_WEBHOOK
```

## Variables d'environnement

* ``POSTGRES_*`` (host, port, db, user, password) — pour charger gold.*
* ``MLFLOW_TRACKING_URI`` — où logger les runs
* ``LYONFLOW_MODELS_DIR`` — où sauvegarder les .pt (défaut: /app/models)
* ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY`` — pour --upload-s3
* ``SLACK_WEBHOOK_URL`` — pour --slack-webhook

## Pré-requis EC2

1. Instance EC2 g4dn.xlarge ou g5.xlarge (GPU T4/L4)
2. AMI : Deep Learning Base GPU (Ubuntu 22.04)
3. Setup :
   ```bash
   pip install torch torch-geometric h3 mlflow psycopg2-binary pandas
   ```
4. Clone repo + checkout cette branche
5. Copier le .env du VPS (POSTGRES_PASSWORD etc.)
6. Lancer : ``python -m training.stgcn.train_cli --use-db``
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Permet l'import depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.stgcn.dataset import STGCNDataset
from training.stgcn.model import STGCNConfig, is_available
from training.stgcn.train import STGCNTrainer

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# CLI argument parser
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construit le parser argparse."""
    p = argparse.ArgumentParser(
        prog="train_stgcn",
        description="Standalone STGCN training CLI (EC2-friendly)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[5, 15, 30, 60, 180, 360],
        help="Horizons à entraîner (en minutes). Défaut: tous les 6 horizons CLAUDE.md.",
    )
    p.add_argument(
        "--use-db",
        action="store_true",
        help="Charger gold.traffic_features_live depuis la DB (défaut: synthetic).",
    )
    p.add_argument(
        "--num-nodes-max",
        type=int,
        default=1520,
        help="Nombre max de nœuds (DB mode only).",
    )
    p.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Nombre d'epochs par horizon.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Taille des batches.",
    )
    p.add_argument(
        "--hidden-channels",
        type=int,
        default=128,
        help="Dimension cachée GRU/GCN.",
    )
    p.add_argument(
        "--seq-len",
        type=int,
        default=12,
        help="Longueur de la fenêtre d'entrée (timesteps × 5 min).",
    )
    p.add_argument(
        "--patience",
        type=int,
        default=5,
        help="Early stopping patience.",
    )
    p.add_argument(
        "--model-dir",
        type=str,
        default=os.getenv("LYONFLOW_MODELS_DIR", "/app/models"),
        help="Répertoire de sauvegarde des modèles.",
    )
    p.add_argument(
        "--upload-s3",
        type=str,
        default=None,
        help="Upload les modèles vers S3 après training (ex: s3://bucket/models/).",
    )
    p.add_argument(
        "--slack-webhook",
        type=str,
        default=None,
        help="URL du webhook Slack pour notifier fin de training.",
    )
    p.add_argument(
        "--quality-tolerance",
        type=float,
        default=0.15,
        help="Tolérance quality gate (15%% par défaut).",
    )
    p.add_argument(
        "--strict-quality",
        action="store_true",
        help="Si activé, lever une erreur si le quality gate échoue (default: warn + continue).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Charge le dataset + init trainer, sans entraîner. Utile pour smoke test.",
    )
    p.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _notify_slack(webhook_url: str, message: str) -> None:
    """Envoie une notif Slack (best-effort, ne lève pas si erreur)."""
    try:
        import urllib.request

        data = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:  # pragma: no cover
        logger.warning("Slack notification failed: %s", e)


def _upload_to_s3(local_dir: Path, s3_uri: str) -> None:
    """Upload les .pt vers S3 (best-effort)."""
    try:
        import boto3

        if not s3_uri.startswith("s3://"):
            raise ValueError(f"s3_uri doit commencer par s3://, got: {s3_uri}")
        bucket, prefix = s3_uri[5:].split("/", 1)
        prefix = prefix.rstrip("/") + "/"
        s3 = boto3.client("s3")
        for pt_file in local_dir.glob("stgcn_*.pt"):
            key = f"{prefix}{pt_file.name}"
            s3.upload_file(str(pt_file), bucket, key)
            logger.info("Uploaded %s to s3://%s/%s", pt_file, bucket, key)
    except ImportError:
        logger.warning("boto3 non installé — skip upload S3")
    except Exception as e:  # pragma: no cover
        logger.exception("S3 upload failed: %s", e)


def _set_strict_quality(strict: bool) -> None:
    """Configure la variable d'env pour le quality gate strict."""
    os.environ["LYONFLOW_STRICT_QUALITY"] = "true" if strict else "false"


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI. Retourne un exit code (0 = succès)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("STGCN training CLI — Sprint 8")
    logger.info("=" * 60)
    logger.info("Arguments: %s", vars(args))

    # Pré-flight checks
    if not is_available():
        logger.error("torch + torch_geometric non installés")
        logger.error("Installation: pip install torch torch-geometric")
        return 1

    _set_strict_quality(args.strict_quality)

    # Chargement dataset
    logger.info("Chargement dataset (use_db=%s)...", args.use_db)
    t0 = time.time()
    if args.use_db:
        try:
            dataset = STGCNDataset.from_db(
                num_nodes_max=args.num_nodes_max,
                seq_len=args.seq_len,
                horizon=max(args.horizons) // 5,  # le plus long horizon
            )
            logger.info("Dataset DB chargé: %s", dataset)
        except Exception as e:
            logger.warning("DB load failed (%s) — fallback synthetic", e)
            dataset = STGCNDataset.synthetic(
                num_nodes=min(args.num_nodes_max, 200),
                seq_len=args.seq_len,
                horizon=max(args.horizons) // 5,
            )
    else:
        dataset = STGCNDataset.synthetic(
            num_nodes=200,
            seq_len=args.seq_len,
            horizon=max(args.horizons) // 5,
        )
    logger.info("Dataset prêt en %.1fs", time.time() - t0)

    if args.dry_run:
        logger.info("[DRY RUN] Mode dry-run — pas d'entraînement, exit 0")
        return 0

    # Configuration modèle
    config = STGCNConfig(
        num_nodes=dataset.X.shape[2],
        hidden_channels=args.hidden_channels,
        seq_len=args.seq_len,
        in_channels=5,
    )

    # Trainer
    trainer = STGCNTrainer(
        dataset=dataset,
        config=config,
        horizons=tuple(args.horizons),
        epochs=args.epochs,
        batch_size=args.batch_size,
        early_stopping_patience=args.patience,
        model_dir=args.model_dir,
    )

    # Training
    logger.info("Démarrage training %d horizons...", len(args.horizons))
    t0 = time.time()
    try:
        results = trainer.train_all()
    except Exception as e:
        logger.exception("Training failed: %s", e)
        if args.slack_webhook:
            _notify_slack(args.slack_webhook, f"❌ STGCN training FAILED: {e}")
        return 2
    elapsed = time.time() - t0

    # Summary
    logger.info("=" * 60)
    logger.info("Training terminé en %.1fs (%.1f min)", elapsed, elapsed / 60)
    for h, metrics in results.items():
        if "error" in metrics:
            logger.warning("  %s: ERROR %s", h, metrics["error"])
        else:
            logger.info(
                "  %s: MAE=%.4f RMSE=%.4f MAPE=%.2f%% R²=%.3f",
                h,
                metrics.get("mae", 0),
                metrics.get("rmse", 0),
                metrics.get("mape_pct", 0),
                metrics.get("r2", 0),
            )
    logger.info("=" * 60)

    # Upload S3
    if args.upload_s3:
        logger.info("Upload S3 vers %s...", args.upload_s3)
        _upload_to_s3(Path(args.model_dir), args.upload_s3)

    # Slack
    if args.slack_webhook:
        msg = (
            f"✅ STGCN training terminé en {elapsed/60:.1f}min\n"
            f"Horizons: {', '.join(str(h) for h in args.horizons)}\n"
            f"Modèle dir: {args.model_dir}\n"
            f"MAE moyen: {sum(m.get('mae', 0) for m in results.values() if 'mae' in m) / max(1, len(results)):.4f}"
        )
        _notify_slack(args.slack_webhook, msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
