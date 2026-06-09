"""DAG — Retrain GNN SpatioTemporalGCN (Sprint 9 — préparation, non activé).

Sprint 9 — Le DAG est **préparé mais désactivé** par défaut. Pour l'activer :

1. Set ``LYONFLOW_STGCN_TRAINING=true`` dans .env (toggle principal)
2. Set ``EC2_TRAINING_HOST=<ip_instance_gpu>`` (pour le mode EC2)
3. Set ``LYONFLOW_GNN_EXECUTION_MODE=ec2`` (ou ``local`` pour tester en CPU)
4. (Optionnel) Set ``LYONFLOW_NOTIFICATION_EMAIL=patrice@lyonflowfull.fr``
5. (Optionnel) Set ``LYONFLOW_SMTP_HOST=smtp.gmail.com`` + creds
6. ``airflow dags unpause retrain_gnn``

Le DAG est créé avec ``is_paused_upon_creation=True`` (Airflow 2.4+) et
``LYONFLOW_STGCN_TRAINING=false`` par défaut → il ne s'exécute jamais
même si le scheduler le déclenche. Le check interne skip proprement
avec un log clair.

Sprint 8 — Toggle ``LYONFLOW_GNN_EXECUTION_MODE`` :
* ``"local"`` (défaut si activé) : entraîne en local sur le VPS avec le
  STGCNTrainer Python. CPU-only, petit nombre de nœuds, lent.
* ``"ec2"`` : délègue l'entraînement à une instance EC2 via SSH
  (commande ``ssh ec2-host 'python -m training.stgcn.train_cli ...'``).

Voir ``docs/EC2_TRAINING_GUIDE.md`` pour le détail de l'infra EC2.

**État actuel (2026-06-07)** : DAG créé, présent dans l'UI Airflow,
mais PAUSED et skip par feature flag. Aucun training ne se lance.
L'email de notification est défini avec des paramètres vides
(``LYONFLOW_NOTIFICATION_EMAIL=""``), à remplir avant activation.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Email notification (préparé mais vide — à remplir avant activation)
# -----------------------------------------------------------------------------


def _send_email_notification(
    subject: str,
    body: str,
    to_email: str | None = None,
) -> bool:
    """Envoie un email de notification (SMTP).

    Préparation Sprint 9 : le template est prêt mais les paramètres
    sont vides. Pour activer les notifications :

    1. Set ``LYONFLOW_NOTIFICATION_EMAIL=patrice@lyonflowfull.fr``
    2. Set ``LYONFLOW_SMTP_HOST=smtp.gmail.com`` (ou autre)
    3. Set ``LYONFLOW_SMTP_PORT=587``
    4. Set ``LYONFLOW_SMTP_USER=<user>`` + ``LYONFLOW_SMTP_PASSWORD=<pwd>``

    Pour l'instant, si l'email est vide → on log uniquement (no-op).
    """
    to_email = to_email or os.getenv("LYONFLOW_NOTIFICATION_EMAIL", "")
    if not to_email:
        logger.info(
            "[email no-op] destinataire vide. Pour activer : set LYONFLOW_NOTIFICATION_EMAIL dans .env. Subject: %s",
            subject,
        )
        return False

    smtp_host = os.getenv("LYONFLOW_SMTP_HOST", "")
    smtp_user = os.getenv("LYONFLOW_SMTP_USER", "")
    smtp_pwd = os.getenv("LYONFLOW_SMTP_PASSWORD", "")
    if not smtp_host or not smtp_user:
        logger.warning(
            "[email skipped] SMTP_HOST ou SMTP_USER manquant. Body (à destination de %s):\n%s",
            to_email,
            body,
        )
        return False

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email

        smtp_port = int(os.getenv("LYONFLOW_SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pwd)
            server.send_message(msg)
        logger.info("Email notification sent to %s", to_email)
        return True
    except Exception as e:  # pragma: no cover
        logger.exception("Email send failed: %s", e)
        return False


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _is_torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401

        return True
    except ImportError as e:
        logger.warning("torch/torch_geometric non disponibles : %s", e)
        return False


def _is_stgcn_dag_enabled() -> bool:
    """Vérifie le toggle LYONFLOW_STGCN_TRAINING + LYONFLOW_MODELS_ACTIVE."""
    from src.ml.model_registry import (
        is_stgcn_enabled,
        is_stgcn_training_enabled,
    )

    if not is_stgcn_training_enabled():
        logger.info("LYONFLOW_STGCN_TRAINING=False — DAG skip (préparation only)")
        return False
    if not is_stgcn_enabled():
        logger.info("STGCN pas dans LYONFLOW_MODELS_ACTIVE — DAG skip")
        return False
    return True


# -----------------------------------------------------------------------------
# Modes d'exécution
# -----------------------------------------------------------------------------


def _train_local() -> dict:
    """Mode local : entraîne directement dans l'environnement Airflow."""
    from training.stgcn.dataset import STGCNDataset
    from training.stgcn.model import STGCNConfig
    from training.stgcn.train import STGCNTrainer

    try:
        dataset = STGCNDataset.from_db(num_nodes_max=200, seq_len=12, horizon=360 // 5)
    except Exception as e:
        logger.warning("DB load failed (%s) — fallback synthetic", e)
        dataset = STGCNDataset.synthetic(num_nodes=100, seq_len=12, horizon=360 // 5)

    config = STGCNConfig(
        num_nodes=dataset.X.shape[2],
        hidden_channels=64,
        seq_len=12,
        in_channels=5,
    )
    trainer = STGCNTrainer(
        dataset=dataset,
        config=config,
        horizons=(5, 15, 30, 60, 180, 360),
        epochs=20,
        batch_size=8,
        early_stopping_patience=3,
    )
    return trainer.train_all()


def _train_remote_ec2() -> dict:
    """Mode EC2 : SSH vers l'instance GPU et déclenche le training CLI.

    Pré-requis :
    * Variable d'env ``EC2_TRAINING_HOST`` (DNS ou IP publique de l'instance)
    * Clé SSH ``~/.ssh/lyonflow_ec2`` configurée
    * L'instance EC2 a cloné le repo + installé les deps

    Returns:
        Dict avec ``{"remote_host": ..., "returncode": ...}``.
    """
    host = os.getenv("EC2_TRAINING_HOST")
    if not host:
        raise RuntimeError("EC2_TRAINING_HOST non défini. Configure l'IP de l'instance GPU dans .env")

    s3_bucket = os.getenv("LYONFLOW_MODELS_S3_BUCKET", "")
    s3_arg = f"--upload-s3 s3://{s3_bucket}/models/" if s3_bucket else ""
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_arg = f"--slack-webhook {slack_webhook}" if slack_webhook else ""

    remote_cmd = (
        "cd ~/lyonflowfull && "
        "source venv/bin/activate && "
        f"python -m training.stgcn.train_cli "
        f"--use-db --epochs 50 --batch-size 32 "
        f"--hidden-channels 128 --num-nodes-max 1520 "
        f"{s3_arg} {slack_arg} "
        "2>&1 | tee -a /tmp/gnn_training.log"
    )

    ssh_cmd = [
        "ssh",
        "-i",
        os.path.expanduser("~/.ssh/lyonflow_ec2"),
        "-o",
        "StrictHostKeyChecking=no",
        f"ubuntu@{host}",
        remote_cmd,
    ]

    logger.info("Lancement training EC2 sur %s ...", host)
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=4 * 3600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("EC2 training timeout après 4h")
        return {"remote_host": host, "error": "timeout", "returncode": -1}
    except Exception as e:
        logger.exception("EC2 training failed to launch: %s", e)
        return {"remote_host": host, "error": str(e), "returncode": -1}

    logger.info("EC2 training terminé, returncode=%d", result.returncode)
    if result.returncode != 0:
        logger.error("stderr: %s", result.stderr[:1000])
    return {
        "remote_host": host,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:] if result.stdout else "",
        "stderr_tail": result.stderr[-1000:] if result.stderr else "",
    }


# -----------------------------------------------------------------------------
# Task principal
# -----------------------------------------------------------------------------


def _train_orchestrator(**context) -> dict:
    """Décide du mode d'exécution (local vs EC2) et appelle le bon trainer."""
    if not _is_stgcn_dag_enabled():
        body = (
            "STGCN retrain skipped — feature flag off.\n\n"
            "Pour activer :\n"
            "1. Set LYONFLOW_STGCN_TRAINING=true dans .env\n"
            "2. Set EC2_TRAINING_HOST=<ip_gpu> pour le mode EC2\n"
            "3. airflow dags unpause retrain_gnn"
        )
        _send_email_notification(
            subject="[LyonFlowFull] STGCN retrain skipped (preparation mode)",
            body=body,
        )
        return {"skipped": "DAG disabled by feature flag"}

    if not _is_torch_available():
        if os.getenv("EC2_TRAINING_HOST"):
            logger.info("torch indispo en local — délégation EC2")
            return _train_remote_ec2()
        logger.info("torch indispo et pas de EC2_TRAINING_HOST — DAG skip")
        return {"skipped": "torch not available locally and no EC2 host"}

    mode = os.getenv("LYONFLOW_GNN_EXECUTION_MODE", "local").lower()
    if mode == "ec2":
        return _train_remote_ec2()
    return _train_local()


# -----------------------------------------------------------------------------
# DAG (Sprint 9 — préparation, non activé)
# -----------------------------------------------------------------------------


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=4),
    "email": [os.getenv("LYONFLOW_NOTIFICATION_EMAIL", "")],
    "email_on_failure": bool(os.getenv("LYONFLOW_NOTIFICATION_EMAIL", "")),
    "email_on_retry": False,
}

# is_paused_upon_creation=True : Airflow crée le DAG en pause.
# Il faudra faire `airflow dags unpause retrain_gnn` pour l'activer.
# Combiné avec LYONFLOW_STGCN_TRAINING=false → le DAG ne s'exécute jamais.
with DAG(
    dag_id="retrain_gnn",
    description=(
        "Retrain SpatioTemporalGCN (6 horizons: 5/15/30/60/180/360 min) — "
        "daily 03h — local OR EC2 — DÉSACTIVÉ par défaut, à activer via "
        "LYONFLOW_STGCN_TRAINING=true"
    ),
    default_args=default_args,
    schedule="0 3 * * *",  # daily 03h (match CLAUDE.md)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,  # Sprint 9 — créé en pause
    tags=["ml", "gnn", "traffic", "heavy", "ec2-optional", "preparation"],
) as dag:
    PythonOperator(
        task_id="train_stgcn_orchestrator",
        python_callable=_train_orchestrator,
        execution_timeout=timedelta(hours=4),
    )


