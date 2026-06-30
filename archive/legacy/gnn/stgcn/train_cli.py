"""Standalone CLI pour l'entraînement du modèle SpatioTemporalGCN (STGCN).

Ce script est conçu pour s'exécuter sur une instance EC2 (ou toute machine équipée
d'un GPU) de manière autonome, sans nécessiter l'orchestration par Airflow.

Il peut être invoqué de plusieurs manières :
* Manuellement via SSH pour un entraînement ad-hoc.
* Via une tâche cron configurée sur le système hôte.
* Par le DAG Airflow ``retrain_gnn`` via un appel SSH ou subprocess distant.
* Via AWS Step Functions ou un workflow GitHub Actions.

Usage:
    # Entraînement par défaut sur tous les horizons définis
    python -m training.stgcn.train_cli

    # Entraînement sur un horizon spécifique (ex: 60 minutes)
    python -m training.stgcn.train_cli --horizon 60

    # Utilisation des données réelles de la base de données
    python -m training.stgcn.train_cli --use-db

Variables d'environnement attendues:
    POSTGRES_* : Identifiants de connexion à la base de données.
    MLFLOW_TRACKING_URI : URI du serveur MLflow pour le suivi des expériences.
    LYONFLOW_MODELS_DIR : Répertoire de destination pour les modèles exportés (.pt).
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY : Identifiants pour l'upload S3.
    SLACK_WEBHOOK_URL : URL du webhook pour les notifications de fin d'entraînement.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ajout dynamique de la racine du projet au PYTHONPATH pour permettre
# les imports absolus (ex: `from training.stgcn...`)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.stgcn.dataset import STGCNDataset
from training.stgcn.model import STGCNConfig, is_available
from training.stgcn.train import STGCNTrainer

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Configuration du parseur d'arguments CLI
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construit et configure le parseur d'arguments en ligne de commande.

    Returns:
        argparse.ArgumentParser: Le parseur configuré avec toutes les options.
    """
    p = argparse.ArgumentParser(
        prog="train_stgcn",
        description="CLI d'entraînement autonome pour le modèle STGCN.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Groupe d'arguments liés aux données
    data_group = p.add_argument_group("Données et Horizons")
    data_group.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[5, 15, 30, 60, 180, 360],
        help="Liste des horizons de prédiction (en minutes) à entraîner.",
    )
    data_group.add_argument(
        "--use-db",
        action="store_true",
        help="Si activé, charge les données de trafic réelles depuis la base (sinon utilise des données synthétiques).",
    )
    data_group.add_argument(
        "--num-nodes-max",
        type=int,
        default=1520,
        help="Nombre maximum de nœuds à charger (uniquement en mode DB).",
    )

    # Groupe d'arguments liés à l'entraînement
    train_group = p.add_argument_group("Hyperparamètres d'entraînement")
    train_group.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Nombre maximum d'époques pour chaque horizon.",
    )
    train_group.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Taille des lots (batch size) pour l'entraînement.",
    )
    train_group.add_argument(
        "--hidden-channels",
        type=int,
        default=128,
        help="Dimension des couches cachées (GCN et GRU).",
    )
    train_group.add_argument(
        "--seq-len",
        type=int,
        default=12,
        help="Longueur de la séquence d'entrée (historique en nombre de pas de temps).",
    )
    train_group.add_argument(
        "--patience",
        type=int,
        default=5,
        help="Nombre d'époques de patience pour l'arrêt précoce (early stopping).",
    )

    # Groupe d'arguments liés aux artefacts et notifications
    ops_group = p.add_argument_group("Opérations (Artefacts, S3, Slack)")
    ops_group.add_argument(
        "--model-dir",
        type=str,
        default=os.getenv("LYONFLOW_MODELS_DIR", "/app/models"),
        help="Chemin du répertoire local où sauvegarder les modèles générés.",
    )
    ops_group.add_argument(
        "--upload-s3",
        type=str,
        default=None,
        help="URI S3 pour l'upload des modèles (ex: s3://mon-bucket/models/).",
    )
    ops_group.add_argument(
        "--slack-webhook",
        type=str,
        default=None,
        help="URL du Webhook Slack pour notifier de la fin ou de l'échec de l'entraînement.",
    )

    # Groupe lié à la qualité et au debugging
    sys_group = p.add_argument_group("Système et Qualité")
    sys_group.add_argument(
        "--quality-tolerance",
        type=float,
        default=0.15,
        help="Tolérance d'erreur pour la validation de qualité (défaut 15%%).",
    )
    sys_group.add_argument(
        "--strict-quality",
        action="store_true",
        help="Active le mode strict : échoue si la qualité minimale n'est pas atteinte.",
    )
    sys_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Exécute l'initialisation sans lancer l'entraînement réel (utile pour tests).",
    )
    sys_group.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de verbosité des logs.",
    )

    return p


# -----------------------------------------------------------------------------
# Fonctions utilitaires (Helpers)
# -----------------------------------------------------------------------------

def _notify_slack(webhook_url: str, message: str) -> None:
    """Envoie une notification Slack via un webhook fourni.
    
    Cette fonction agit en mode 'best-effort', c'est-à-dire qu'elle
    ne crashera pas le script principal en cas d'erreur réseau.

    Args:
        webhook_url (str): L'URL du webhook Slack.
        message (str): Le contenu du message à envoyer.
    """
    try:
        import urllib.request

        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:  # pragma: no cover
        logger.warning("Échec de la notification Slack : %s", e)


def _upload_to_s3(local_dir: Path, s3_uri: str) -> None:
    """Upload les modèles (.pt) présents dans un répertoire local vers S3.
    
    Nécessite la bibliothèque `boto3`. Agit en 'best-effort'.

    Args:
        local_dir (Path): Le répertoire local contenant les fichiers `.pt`.
        s3_uri (str): L'URI de destination S3 (ex: s3://bucket/prefix).
    """
    try:
        import boto3

        if not s3_uri.startswith("s3://"):
            raise ValueError(f"L'URI S3 doit commencer par s3://, reçu : {s3_uri}")

        # Séparation du bucket et du préfixe
        bucket, prefix = s3_uri[5:].split("/", 1)
        prefix = prefix.rstrip("/") + "/"

        s3 = boto3.client("s3")
        for pt_file in local_dir.glob("stgcn_*.pt"):
            key = f"{prefix}{pt_file.name}"
            s3.upload_file(str(pt_file), bucket, key)
            logger.info("Upload S3 réussi : %s -> s3://%s/%s", pt_file.name, bucket, key)

    except ImportError:
        logger.warning("Bibliothèque boto3 non installée — l'upload S3 a été ignoré.")
    except Exception as e:  # pragma: no cover
        logger.exception("Échec lors de l'upload S3 : %s", e)


def _set_strict_quality(strict: bool) -> None:
    """Configure la variable d'environnement pour activer ou non le contrôle qualité strict.

    Args:
        strict (bool): Si True, définit la variable `LYONFLOW_STRICT_QUALITY` à 'true'.
    """
    os.environ["LYONFLOW_STRICT_QUALITY"] = "true" if strict else "false"


# -----------------------------------------------------------------------------
# Fonction Principale (Main)
# -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de l'application CLI d'entraînement.

    Args:
        argv (list[str] | None): Arguments de ligne de commande optionnels.

    Returns:
        int: Code de retour (0 pour succès, non-zéro pour échec).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configuration initiale du logging
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("CLI d'entraînement STGCN — Démarrage")
    logger.info("=" * 60)
    logger.info("Arguments de lancement : %s", vars(args))

    # Vérification des pré-requis (modules torch et torch_geometric)
    if not is_available():
        logger.error("Dépendances manquantes : torch ou torch_geometric ne sont pas installés.")
        logger.error("Veuillez exécuter : pip install torch torch-geometric")
        return 1

    # Application de la configuration qualité
    _set_strict_quality(args.strict_quality)

    # 1. Chargement des données (Dataset)
    logger.info("Initialisation du dataset (mode DB : %s)...", args.use_db)
    start_time = time.time()

    if args.use_db:
        try:
            # Calcul de l'horizon maximum en pas de temps (chaque pas = 5 min)
            max_horizon_steps = max(args.horizons) // 5
            dataset = STGCNDataset.from_db(
                num_nodes_max=args.num_nodes_max,
                seq_len=args.seq_len,
                horizon=max_horizon_steps,
            )
            logger.info("Dataset chargé avec succès depuis la base de données : %s", dataset)
        except Exception as e:
            logger.warning("Échec du chargement DB (%s) — Basculement vers des données synthétiques.", e)
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

    logger.info("Dataset prêt en %.1fs", time.time() - start_time)

    # Mode test (dry-run) : on arrête l'exécution ici
    if args.dry_run:
        logger.info("[DRY RUN] Mode vérification activé — pas d'entraînement réel. Fin de l'exécution (exit 0).")
        return 0

    # 2. Configuration du modèle STGCN
    config = STGCNConfig(
        num_nodes=dataset.X.shape[2],
        hidden_channels=args.hidden_channels,
        seq_len=args.seq_len,
        in_channels=5,
    )

    # 3. Initialisation de l'orchestrateur d'entraînement
    trainer = STGCNTrainer(
        dataset=dataset,
        config=config,
        horizons=tuple(args.horizons),
        epochs=args.epochs,
        batch_size=args.batch_size,
        early_stopping_patience=args.patience,
        model_dir=args.model_dir,
    )

    # 4. Lancement de l'entraînement
    logger.info("Début de l'entraînement pour %d horizons...", len(args.horizons))
    train_start = time.time()
    try:
        results = trainer.train_all()
    except Exception as e:
        logger.exception("Échec critique lors de l'entraînement : %s", e)
        if args.slack_webhook:
            _notify_slack(args.slack_webhook, f"❌ Échec de l'entraînement STGCN : {e}")
        return 2

    elapsed_time = time.time() - train_start

    # 5. Synthèse et affichage des résultats
    logger.info("=" * 60)
    logger.info("Entraînement finalisé en %.1fs (%.1f min)", elapsed_time, elapsed_time / 60)

    # Agrégation manuelle pour le rapport global
    total_mae = 0.0
    valid_horizons = 0

    for horizon, metrics in results.items():
        if "error" in metrics:
            logger.warning("  Horizon %s : ERREUR %s", horizon, metrics["error"])
        else:
            mae = metrics.get("mae", 0)
            total_mae += mae
            valid_horizons += 1

            logger.info(
                "  Horizon %s : MAE=%.4f | RMSE=%.4f | MAPE=%.2f%% | R²=%.3f",
                horizon,
                mae,
                metrics.get("rmse", 0),
                metrics.get("mape_pct", 0),
                metrics.get("r2", 0),
            )
    logger.info("=" * 60)

    # 6. Post-traitement (Upload S3)
    if args.upload_s3:
        logger.info("Début de l'export vers S3 (%s)...", args.upload_s3)
        _upload_to_s3(Path(args.model_dir), args.upload_s3)

    # 7. Post-traitement (Notification Slack)
    if args.slack_webhook:
        avg_mae = (total_mae / valid_horizons) if valid_horizons > 0 else 0.0
        msg = (
            f"✅ Entraînement STGCN réussi en {elapsed_time / 60:.1f}min\n"
            f"Horizons traités : {', '.join(str(h) for h in args.horizons)}\n"
            f"Répertoire des modèles : {args.model_dir}\n"
            f"MAE moyen sur les horizons : {avg_mae:.4f}"
        )
        _notify_slack(args.slack_webhook, msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
