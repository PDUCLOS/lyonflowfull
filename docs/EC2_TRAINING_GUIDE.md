# Guide EC2 — Entraînement du SpatioTemporalGCN

> **Date** : 2026-06-06 (Sprint 8)
> **Audience** : Patrice (data scientist architecte AI) + toute personne
> qui doit setup / opérer l'instance GPU EC2.
> **But** : entraîner le GNN sur une instance GPU AWS (ou GCP / Scaleway /
> n'importe quel cloud GPU) sans dépendre du VPS Phase 1.

## 🎯 Pourquoi EC2 et pas le VPS ?

| | VPS (51.83.159.224) | EC2 GPU |
|---|---|---|
| CPU | 6 vCPU, 12 GB RAM | g4dn.xlarge : 4 vCPU + 1× T4 16 GB |
| GPU | ❌ Pas de GPU | ✅ NVIDIA T4 (16 GB VRAM) |
| Prix | ~12 €/mois | ~$0.50/h (~$370/mois 24/7) ou spot ~$0.20/h |
| Stabilité | Très bien pour XGBoost | Nécessaire pour GNN nightly |
| Usage | Streamlit, FastAPI, XGBoost, ETL | **GNN training uniquement** (à la demande) |

**Décision** : on garde le VPS pour tout (XGBoost, dashboard, ETL, MLflow).
L'EC2 sert UNIQUEMENT au training GNN (lourd). On l'allume 1×/jour pendant
~30 min, puis on l'éteint. Coût réel : ~$3-5/mois (spot instance).

## 🏗️ Architecture

```
VPS 51.83.159.224 (Phase 1)             EC2 GPU (Sprint 8)
┌──────────────────────────┐            ┌──────────────────────────┐
│                          │            │                          │
│ Airflow scheduler        │            │ Spot instance            │
│   └─ DAG retrain_gnn     │ SSH        │   g4dn.xlarge / T4       │
│      (orchestrateur)     │───────────▶│   venv + training/stgcn/ │
│                          │            │   python train_cli.py    │
│ Postgres gold.* ─────────┼─── read ──▶│                          │
│                          │            │ Output:                  │
│ MLflow tracking          │◀──── log ──│   s3://bucket/models/    │
│                          │            │   stgcn_h{60}.pt        │
│ Streamlit Pro_7          │            │                          │
│   └─ Model Registry      │            │ Auto-shutdown            │
│      (XGBoost + GNN)     │            │   après training         │
│                          │            │                          │
└──────────────────────────┘            └──────────────────────────┘
                  │                                   │
                  └───────── S3 (modèles) ──────────┘
```

## 🚀 Setup EC2 (one-shot)

### 1. Lancer l'instance

```bash
# Option recommandée : AWS CLI + spot instance
aws ec2 run-instances \
    --image-id ami-0c7217cdde317cfec \   # Deep Learning Base GPU (Ubuntu 22.04)
    --instance-type g4dn.xlarge \
    --key-name lyonflow-ec2 \
    --security-group-ids sg-xxxxx \
    --subnet-id subnet-xxxxx \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=lyonflow-gnn-trainer}]' \
    --instance-market-options '{"MarketType":"spot","SpotOptions":{"MaxPrice":"0.30"}}' \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]'
```

Alternative : lancer via console AWS EC2 avec les mêmes paramètres.

### 2. Configuration post-boot (user-data ou SSH)

```bash
# Connexion
ssh -i ~/.ssh/lyonflow_ec2 ubuntu@<EC2_PUBLIC_IP>

# Setup Python + venv
sudo apt update
sudo apt install -y python3.11 python3.11-venv git
git clone https://github.com/PDUCLOS/lyonflowfull.git
cd lyonflowfull
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch torch-geometric h3 mlflow psycopg2-binary pandas boto3

# Copier .env depuis le VPS (POSTGRES_PASSWORD, etc.)
# (NE PAS commit le .env, scp sécurisé)
scp -i ~/.ssh/lyonflow_deploy patrice@51.83.159.224:.env.production .env

# Tester l'accès à la DB
psql -h 51.83.159.224 -U lyonflow -d lyonflow -c "SELECT COUNT(*) FROM gold.traffic_features_live;"

# Tester l'accès au S3
aws s3 ls s3://lyonflow-models/
```

### 3. Premier training manuel (smoke test)

```bash
source venv/bin/activate
python -m training.stgcn.train_cli --dry-run
# → doit charger le dataset, init le trainer, return 0

python -m training.stgcn.train_cli --use-db --epochs 5 --horizons 60
# → 1 horizon, 5 epochs, ~5 min, qualité basse mais on valide la chaîne
```

### 4. Configuration du bucket S3

```bash
# Créer le bucket (one-shot)
aws s3 mb s3://lyonflow-models --region eu-west-3

# Donner les droits à l'instance EC2
# (via IAM role attaché à l'instance, pas d'access keys sur disque)
```

## 🔄 Workflow nightly

### Option A — Cron sur l'EC2 (simple, recommandé MVP)

```bash
# Sur l'EC2, dans venv
crontab -e
# Ajouter :
0 3 * * * cd /home/ubuntu/lyonflowfull && /home/ubuntu/lyonflowfull/venv/bin/python -m training.stgcn.train_cli --use-db --epochs 50 --batch-size 32 --hidden-channels 128 --num-nodes-max 1520 --upload-s3 s3://lyonflow-models/models/ --slack-webhook $SLACK_WEBHOOK_URL >> /home/ubuntu/gnn_training.log 2>&1
```

**Avantage** : l'EC2 gère elle-même son cycle (training → upload → shutdown).
**Inconvénient** : si l'EC2 est off, le cron ne tourne pas (mais c'est le but).

### Option B — Orchestration par le DAG VPS

Le DAG `retrain_gnn` (Sprint 8) peut déléguer à EC2 via SSH :

```python
# dans dags/ml/retrain_gnn.py — déjà implémenté
def _train_remote_ec2():
    ssh_cmd = ["ssh", "-i", "~/.ssh/lyonflow_ec2", f"ubuntu@{host}", remote_cmd]
    result = subprocess.run(ssh_cmd, timeout=4*3600)
    return result.returncode
```

**Avantage** : orchestration centralisée sur le VPS, logs dans Airflow.
**Inconvénient** : si l'EC2 est off, le DAG va timeout (4h).

### Option C — AWS Step Functions / EventBridge (overkill pour MVP)

Déclenche automatiquement le training sur EventBridge cron, lance l'instance,
exécute le training, sync S3, termine l'instance. Le plus propre mais
setup lourd.

**Recommandation actuelle** : **Option A** (cron sur EC2, on/off à la main)
pour la phase MVP. Migrer vers Option B quand le DAG est stable en prod.

## 📥 Récupération des modèles vers le VPS

```bash
# Sur le VPS, après le training EC2
aws s3 sync s3://lyonflow-models/models/ /app/models/

# OU scp direct (sans S3)
scp -i ~/.ssh/lyonflow_ec2 ubuntu@<EC2_IP>:/home/ubuntu/lyonflowfull/models/*.pt /app/models/
```

Le STGCNWrapper sur le VPS (Sprint 7) charge automatiquement les `.pt`
depuis `LYONFLOW_MODELS_DIR` (défaut `/app/models`).

## 🔀 Toggle XGBoost vs GNN (le workflow validation)

L'instance EC2 peut tourner pendant des jours sans que Patrice ne touche
au toggle. Quand il a accumulé assez de données (monitoring `Pro_7` →
Model Registry Status) :

### Phase 1 : les 2 en // (défaut actuel)
```bash
# .env sur VPS
LYONFLOW_MODELS_ACTIVE=both
LYONFLOW_XGBOOST_TRAINING=true
LYONFLOW_STGCN_TRAINING=true
```
→ Les 2 modèles tournent, dashboard compare.

### Phase 2 : Patrice valide le GNN
```bash
LYONFLOW_MODELS_ACTIVE=stgcn        # GNN devient prod
LYONFLOW_XGBOOST_TRAINING=false     # Arrête le retrain XGBoost
LYONFLOW_STGCN_TRAINING=true        # Continue
```
→ Seul GNN sert les prédictions, dashboard désactive la section XGBoost.
→ Le DAG `retrain_xgboost_speed` skip automatiquement (log "disabled by feature flag").
→ Le DAG `retrain_gnn` continue sur EC2.

### Phase 3 : rollback si GNN foire
```bash
LYONFLOW_MODELS_ACTIVE=xgboost
LYONFLOW_XGBOOST_TRAINING=true
LYONFLOW_STGCN_TRAINING=false       # On coupe le coût EC2
```
→ Retour XGBoost seul, EC2 peut être arrêtée.

## 💰 Coût EC2 (estimation)

| Scénario | Prix/h spot | Heures/mois | Coût mensuel |
|----------|------------|-------------|--------------|
| Daily 30 min (recommandé) | $0.20 | 15h | **~$3** |
| Daily 2h (debug initial) | $0.20 | 60h | ~$12 |
| 24/7 (overkill) | $0.20 | 720h | $144 |
| On-demand g4dn.xlarge | $0.526 | 15h | ~$8 |

→ **~3-5 $/mois** en mode optimal, vs $144 en 24/7.

Alternative moins cher : **RunPod** spot GPU à $0.20/h T4, même API.

## 🛡️ Sécurité EC2

1. **Security Group** : autoriser uniquement SSH (port 22) depuis ton IP
2. **IAM Role** : `AmazonS3ReadWriteAccess` sur bucket `lyonflow-models` (pas
   d'access keys sur disque)
3. **SSH key** dédiée `~/.ssh/lyonflow_ec2` (jamais commit)
4. **Pas de PII** : le training manipule des features, pas de données nominatives
5. **Logs centralisés** : le CLI log dans stdout → CloudWatch (optionnel)
6. **Shutdown auto** : la dernière instruction du training CLI est
   `sudo shutdown -h now` (décommenter dans le cron si tu veux)
7. **EBS encryption** : activée par défaut sur gp3
8. **VPC** : l'instance est dans le VPC LyonFlow, pas sur Internet public
   sauf pour SSH (bastion recommandé pour la prod)

## 📊 Monitoring EC2

* **CloudWatch** : CPU, GPU util, RAM, disk, network (gratuit basique)
* **MLflow tracking** : le training log dans `stgcn_traffic` experiment,
  visible sur le VPS (même backend Postgres)
* **S3 lifecycle** : bucket versionné, retention 30 jours (anciens modèles)
* **Slack notif** : `--slack-webhook` à la fin du training, summary + status

## 🐛 Troubleshooting

### L'instance ne se lance pas (quota AWS)

```bash
aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-DB2E81BA \
    --region eu-west-3
# → "G et VT instances" : augmenter la demande
```

### torch.cuda.is_available() retourne False

```bash
# Vérifier le driver NVIDIA
nvidia-smi
# Si erreur : reboot + check que l'AMI est bien "Deep Learning" (pas "Standard")
```

### SSH connection refused

```bash
# Vérifier le security group + IP publique
aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[].Instances[].PublicIpAddress'
# Update le SG si besoin
```

### DB connection failed (depuis EC2 vers VPS)

```bash
# Le VPS 51.83.159.224 n'autorise peut-être pas l'IP EC2
# Option 1 : ajouter l'IP EC2 au pg_hba.conf
# Option 2 : tunnel SSH (ssh -L 5433:vps:5432)
# Option 3 : VPN entre VPC AWS et VPS (overkill)
```

### Modèle pas trouvé sur le VPS après upload S3

```bash
# Vérifier le path
ls -la /app/models/stgcn_h60.pt
# Vérifier LYONFLOW_MODELS_DIR
echo $LYONFLOW_MODELS_DIR
# Re-trigger le load (le wrapper cache, restart FastAPI)
docker compose restart api streamlit
```

## 📚 Liens utiles

* AWS Deep Learning AMI : https://aws.amazon.com/machine-learning/amis/
* PyTorch GPU install : https://pytorch.org/get-started/locally/
* torch-geometric install : https://pytorch-geometric.readthedocs.io/en/latest/install/installation.html
* Spot instance advisor : https://aws.amazon.com/ec2/spot/instance-advisor/
* MLflow tracking : https://mlflow.org/docs/latest/tracking.html

## 🔄 Évolution Phase 2 (K8s)

Quand on migre en K8s, l'EC2 GPU devient un **node pool GPU** dans le
cluster (cf. `docs/K8S_MIGRATION_PLAN.md` section "GPU pool GNN") :

* nodeSelector `gpu: yes`
* Toleration `nvidia.com/gpu=true:NoSchedule`
* Resource limit `nvidia.com/gpu: 1`
* Training = KubernetesJob qui spawn 1 pod GPU

L'EC2 spot "à l'ancienne" reste utile pour le debug rapide (console
AWS, SSH direct, pas de YAML).
