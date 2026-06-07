# LyonFlowFull — Phase 2 Kubernetes

Manifests Kustomize pour déployer LyonFlowFull sur Kubernetes (Scaleway
Kapsule par défaut, portable sur tout cluster K8s ≥ 1.27).

Référence plan : `docs/K8S_MIGRATION_PLAN.md` (branche `main`).

## Architecture

```
kubernetes/
├── base/                 # Manifests de référence (sans overlay)
│   ├── namespace.yaml
│   ├── postgres/         # StatefulSet PostgreSQL + PostGIS + PVC
│   ├── redis/            # Deployment Redis (cache + broker Celery)
│   ├── mlflow/           # Deployment MLflow + PVC artifacts
│   ├── airflow/          # Helm values + DAG ConfigMap reference
│   ├── fastapi/          # Deployment + HPA + Service + Ingress
│   ├── streamlit/        # Deployment + HPA + Service + Ingress
│   ├── nginx/            # Ingress controller config
│   └── secrets/          # SealedSecret templates (NE PAS commit les secrets)
├── overlays/
│   ├── dev/              # 1 replica par service, ressources minimales
│   └── prod/             # HPA, replicas multiples, ressources prod
├── scripts/
│   ├── bootstrap-cluster.sh   # Init cluster (NS, secrets, CRDs)
│   ├── backup-pg.sh           # Dump Postgres → Object Storage
│   ├── restore-pg.sh          # Restore depuis Object Storage
│   └── seal-secrets.sh        # Wrap .env → SealedSecret
└── docs/
    ├── RUNBOOK.md             # Opérations courantes
    └── DEPLOY.md              # Guide de déploiement step-by-step
```

## Prérequis

| Outil | Version min | Usage |
|-------|-------------|-------|
| `kubectl` | 1.27+ | Apply manifests |
| `kustomize` | 5.0+ | Builds overlays |
| `helm` | 3.12+ | Airflow chart |
| `kubeseal` | 0.24+ | SealedSecrets |
| Cluster K8s | 1.27+ | Scaleway Kapsule recommandé |

## Quick start (overlay dev)

```bash
# 1. Connecter kubectl au cluster
export KUBECONFIG=~/.kube/kapsule-dev.kubeconfig
kubectl get nodes

# 2. Bootstrap (namespaces, CRDs, sealed-secrets controller)
./scripts/bootstrap-cluster.sh

# 3. Sceller les secrets locaux
cp .env.example .env  # remplir les valeurs
./scripts/seal-secrets.sh .env > base/secrets/sealed-secret.yaml

# 4. Build + apply
kustomize build overlays/dev | kubectl apply -f -

# 5. Vérifier
kubectl -n lyonflow get pods,svc,ingress
kubectl -n lyonflow logs deploy/fastapi -f
```

## Services et ports

| Service | Port interne | Replicas dev | Replicas prod | HPA |
|---------|-------------|--------------|---------------|-----|
| postgres | 5432 | 1 (StatefulSet) | 1 | non |
| redis | 6379 | 1 | 1 | non |
| mlflow | 5000 | 1 | 1 | non |
| airflow-webserver | 8080 | 1 | 2 | non |
| airflow-scheduler | — | 1 | 1 | non (singleton) |
| airflow-worker | — | 1 | 2-6 | sur queue depth |
| fastapi | 8000 | 1 | 3-10 | CPU > 70% |
| streamlit | 8501 | 1 | 2-5 | CPU > 70% |
| nginx (ingress) | 80/443 | 1 | 2 | non |

## Statut Phase 2

| Étape | Statut |
|-------|--------|
| Préparation (provider, kubectl) | ⏸ utilisateur |
| Namespace + secrets | ✅ manifests prêts |
| Postgres StatefulSet | ✅ manifests prêts |
| Redis | ✅ manifests prêts |
| MLflow | ✅ manifests prêts |
| Airflow (Helm) | ✅ values prêtes |
| FastAPI Deployment+HPA+Ingress | ✅ manifests prêts |
| Streamlit Deployment+HPA+Ingress | ✅ manifests prêts |
| GPU node pool GNN | ⏸ optionnel |
| Prometheus + Grafana | ⏸ étape 11 |
| Tests de charge | ⏸ étape 12 |
| Migration données VPS → K8s | ⏸ étape 13 |
| Décommissionnement VPS | ⏸ étape 14 |

## Branches Git

- `main` — pointeur Phase 1 + plan migration
- `vps` — copie figée Phase 1 (production VPS actuelle)
- `kubernetes` — **cette branche**, Phase 2 (manifests K8s)
