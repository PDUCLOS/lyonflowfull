# Plan migration Phase 1 → Phase 2 (Kubernetes)

> **Date** : 2026-06-06
> **Statut** : préparation — pas de code K8s tant que l'utilisateur n'a pas fourni
> un répertoire dédié.
> **Trigger** : feu vert utilisateur + répertoire cible.

## 🎯 Objectif Phase 2

Reprendre les 12 services Docker Compose de Phase 1 et les orchestrer
via Kubernetes (manifests ou Helm chart) pour :

* **Auto-scaling** sur les pics (Airflow workers, FastAPI, Streamlit)
* **Self-healing** (liveness/readiness probes)
* **Rolling updates** sans downtime
* **Multi-node** (au-delà d'un seul VPS)
* **GPU node pool** dédié pour le GNN training (optionnel)

## 📦 Inventaire services Phase 1 (12 containers)

| Service | Image | CPU req | RAM req | Scaling | Notes |
|---------|-------|---------|---------|---------|-------|
| `postgres` | `postgis/postgis:16-3.4` | 1 | 2 GB | StatefulSet | PVC 50 GB, backup CronJob |
| `minio` | `minio/minio:latest` | 0.5 | 1 GB | StatefulSet | PVC 20 GB, ou pivot GDrive |
| `redis` | `redis:7-alpine` | 0.2 | 256 MB | Deployment | Cache + broker |
| `mlflow` | `ghcr.io/mlflow/mlflow:v2.12` | 0.5 | 1 GB | Deployment | Tracking server |
| `airflow-webserver` | custom (Dockerfile) | 0.5 | 1 GB | Deployment (×2) | LB ingress |
| `airflow-scheduler` | custom | 0.5 | 1 GB | Deployment (×1) | Singleton |
| `airflow-worker` | custom | 1 | 2 GB | Deployment (×2-4) | HPA sur queue depth |
| `api` | custom (FastAPI) | 0.5 | 512 MB | Deployment (×3) | HPA CPU > 70% |
| `streamlit` | custom | 0.3 | 512 MB | Deployment (×2) | HPA CPU > 70% |
| `nginx` | `nginx:1.25-alpine` | 0.1 | 64 MB | Deployment (×2) | Ingress edge |
| `minio-init` | `minio/mc` | 0.1 | 64 MB | Job (one-shot) | Bucket creation |
| `airflow-init` | custom | 0.2 | 256 MB | Job (one-shot) | DB migration |

**Total Phase 1** : ~6.2 CPU + ~12 GB RAM en régime nominal, ~12 CPU + 24 GB en pic.

## 🏗️ Architecture K8s cible

### Choix 1 : Manifests vs Helm

| Option | Pour | Contre |
|--------|------|--------|
| **Manifests YAML bruts** | Simple, pas de dépendance, debug facile | Verbeux, duplique les patterns |
| **Helm chart** | Templating, releases, rollback | Courbe d'apprentissage, rigidité |
| **Kustomize** | Overlays par env, pas de templating | Moins puissant que Helm |

**Recommandation** : **Kustomize** pour le MVP (overlays dev/staging/prod), puis
éventuellement Helm si on a besoin de distribuer le chart.

### Choix 2 : K8s managé vs self-hosted

| Option | Pour | Contre |
|--------|------|--------|
| **OVH Managed K8s** | Gratuit control plane, France, support FR | Vendor lock, scaling 5min |
| **Scaleway Kapsule** | Prix mini (5€/mois), France, intégré LB | Moins mature, support limité |
| **DigitalOcean DOKS** | Simple, prix correct | Hors UE (GDPR ++) |
| **GKE Autopilot** | Auto-scaling parfait, GPU | $, vendor lock US |
| **Self-hosted k3s** | 100% libre, control total | Operational burden |

**Recommandation** : **Scaleway Kapsule** pour la démo Jedha (5-10 €/mois,
RGPD-friendly, Paris). Si besoin GPU plus tard → migration GKE ou RunPod.

## 📋 Plan migration (séquencé)

### Étape 1 — Préparation (1-2 jours)

* [ ] Choix provider (Scaleway par défaut)
* [ ] Création cluster K8s (3 nodes minimum : 1 system + 2 worker)
* [ ] Setup `kubectl` + `helm` localement
* [ ] Stockage : Longhorn ou Rook-Ceph (PVC dynamiques)

### Étape 2 — Namespace + secrets (1 jour)

* [ ] Namespace `lyonflow` + `lyonflow-staging`
* [ ] Sealed Secrets pour : POSTGRES_PASSWORD, JWT_SECRET_KEY, API_KEY
* [ ] ConfigMap pour : non-secret env vars (URLs, LOG_LEVEL)
* [ ] NetworkPolicy (isolation inter-namespace)

### Étape 3 — Postgres (1-2 jours)

* [ ] StatefulSet + Service + PVC 50 GB
* [ ] Backup CronJob (pg_dump vers S3-compatible)
* [ ] Init Job (init-db.sql + seed users)
* [ ] Migration données depuis VPS (si applicable)
* [ ] Test failover (kill pod, vérifier redémarrage)

### Étape 4 — MinIO / GDrive (1 jour)

* [ ] StatefulSet MinIO + bucket init
* OU (préféré) : conserver le pivot GDrive, pas de MinIO en K8s

### Étape 5 — Redis (0.5 jour)

* [ ] Deployment + Service
* [ ] PVC si persistance requise, sinon StatefulSet éphémère

### Étape 6 — Airflow (2-3 jours)

* [ ] Helm chart officiel `apache-airflow/airflow` (recommandé)
* [ ] Customisation : DAGs, requirements.txt, entrypoint
* [ ] Executor : KubernetesExecutor (1 pod par task)
* [ ] DAGs in-process ou git-sync

### Étape 7 — FastAPI (1 jour)

* [ ] Deployment × 3 replicas
* [ ] HPA sur CPU + custom metric (request/sec)
* [ ] Liveness probe `/health`
* [ ] Readiness probe `/health/db`
* [ ] Ingress Nginx + cert-manager (Let's Encrypt)

### Étape 8 — Streamlit (1 jour)

* [ ] Deployment × 2 replicas
* [ ] HPA sur CPU
* [ ] Liveness probe `/healthz`
* [ ] Ingress séparé (`app.lyonflow.fr`)

### Étape 9 — MLflow (0.5 jour)

* [ ] Deployment + Service + PVC artifacts
* [ ] S3 backend optionnel (Scaleway Object Storage)

### Étape 10 — GPU pool GNN (1-2 jours, optionnel)

* [ ] Node pool `gpu-g5` (1× NVIDIA T4)
* [ ] Toleration sur pods GNN
* [ ] Test forward pass sur GPU

### Étape 11 — Monitoring (1 jour)

* [ ] Prometheus + Grafana (Helm chart `kube-prometheus-stack`)
* [ ] Alerting : alertmanager + Slack/Discord webhook
* [ ] Logs : Loki + Promtail (optionnel, pour économiser)

### Étape 12 — Tests de charge (1 jour)

* [ ] `k6` ou `locust` : simuler 100 users sur FastAPI
* [ ] Vérifier HPA scale-up à 70% CPU
* [ ] Vérifier PDB (PodDisruptionBudget) sur Postgres

### Étape 13 — Migration données (0.5 jour)

* [ ] Dump VPS PostgreSQL → restore dans K8s Postgres
* [ ] Vérifier intégrité (checksum MD5 sur tables Gold)
* [ ] Switch DNS / load balancer

### Étape 14 — Décommissionnement VPS (0.5 jour)

* [ ] Vérifier 0 requête sur VPS pendant 7 jours
* [ ] Backup final VPS (cold storage)
* [ ] Arrêt VM (garder 1 mois en cas de rollback)

**Total estimé** : ~12-15 jours de travail (Phase 1 → Phase 2).

## 💰 Estimation coûts K8s Scaleway Kapsule

| Ressource | Spec | Prix/mois |
|-----------|------|-----------|
| 3× node STARDUST (2 CPU, 8 GB) | Dev/staging | 3 × 8 € = 24 € |
| 3× node STARDUST (4 CPU, 16 GB) | Prod | 3 × 16 € = 48 € |
| Block storage 100 GB | Postgres + artifacts | 2 € |
| Object Storage 50 GB | Backups | 1 € |
| Load balancer | Ingress | 5 € |
| Traffic sortant | Modeste (10 GB/mois) | 1 € |
| **Total prod estimé** | | **~57 €/mois** |

Comparé à VPS actuel (51.83.159.224, 12 €/mois) : ~5× le coût, mais avec
auto-scaling + multi-node + GPU à la demande.

## 🚦 Critères GO/NO-GO pour Phase 2

| Critère | Requis | Bloquant |
|---------|--------|----------|
| Phase 1 stable > 30 jours en prod | oui | oui |
| Couverture tests > 80% | recommandé | non |
| Manifests K8s + Helm chart prêts | oui | oui |
| Provider choisi + budget OK | oui | oui |
| GPU dispo et rentable | pour GNN prod | non |
| Répertoire K8s séparé créé | oui | oui |

**Recommandation actuelle** : VPS actuel suffit pour la démo Jedha. K8s
devient utile quand on a besoin d'auto-scaling (charge réelle > 1 VPS)
ou de GPU partagé. **Pas avant la certification RNCP 38777**.

## 📁 Répertoire K8s cible (à créer par l'utilisateur)

```
lyonflowfull-k8s/
├── base/                       # Manifests communs
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── postgres/
│   ├── redis/
│   ├── airflow/
│   ├── fastapi/
│   ├── streamlit/
│   ├── mlflow/
│   └── ingress/
├── overlays/
│   ├── dev/
│   ├── staging/
│   └── prod/
├── helm-charts/                # Si on Helm un service
│   └── lyonflow-airflow/
├── scripts/
│   ├── bootstrap-cluster.sh
│   ├── backup-pg.sh
│   └── restore-pg.sh
└── docs/
    ├── RUNBOOK.md
    └── ARCHITECTURE.md
```

## 📌 TODO utilisateur (à fournir)

* [ ] Choix provider K8s (Scaleway par défaut)
* [ ] Nom de domaine (ex: `k8s.lyonflow.fr`)
* [ ] Répertoire cible (vide, prêt à accueillir le chart)
* [ ] Budget mensuel max (~60 € recommandé)
* [ ] Validation finale avant `kubectl apply`

Une fois ces 5 points clarifiés, le sprint de migration peut démarrer
sur ~2 semaines.
