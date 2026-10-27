# deploy/k8s — cible Kubernetes de LyonFlowFull

La production tourne aujourd'hui sur **un VPS en Docker Compose** (`docker-compose.yml`,
`make deploy-vps`). Une migration Kubernetes avait été préparée en juin 2026 sur la
branche `kubernetes` (Phase 2), puis mise en sommeil : cette branche visait encore
l'ancien tandem GNN + XGBoost et un Redis que `main` a depuis supprimés.

Ce dossier **réveille cette cible et la réaligne sur `main`**, sous forme
kustomize `base` + `overlays`.

```
deploy/k8s/
├── base/                    # commun dev + prod
│   ├── namespace.yaml       # Namespace + NetworkPolicy default-deny (ingress)
│   ├── postgres/            # StatefulSet pgRouting 16-3.5-3.7.3 + CronJob pg_dump
│   ├── mlflow/              # MLflow 2.12.1 (backend Postgres, PVC artefacts)
│   ├── fastapi/             # API : Deployment, Service, HPA, Ingress, PDB
│   ├── streamlit/           # Dashboard : idem
│   └── airflow/             # values.yaml du chart Helm officiel (hors kustomize)
├── components/monitoring/   # ServiceMonitor + PrometheusRule (CRD Prometheus Operator)
├── overlays/dev/            # 1 réplica, HPA 1→2, 10 Gi, Secret factice généré
├── overlays/prod/           # HPA API 3→15, Postgres 100 Gi, monitoring activé
└── scripts/                 # bootstrap-cluster.sh, seal-secrets.sh (SealedSecrets)
```

## Validation

```bash
kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/overlays/dev
kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/overlays/prod
```

`--load-restrictor` est nécessaire car le schéma Postgres (`deploy/init-db.sql`,
2 501 lignes) reste la **source unique** partagée avec Compose : on ne le duplique pas.

Résultat mesuré le 27/10/2026 (kubectl client Docker Desktop, kustomize intégré) :

| Overlay | Lignes rendues | Objets |
|---------|---------------:|--------|
| dev  | 1 759 | 3 Deployment, 1 StatefulSet, 4 Service, 2 HPA, 2 Ingress, 2 PDB, 2 PVC, 1 CronJob, 2 ConfigMap, 1 Secret, Namespace, NetworkPolicy |
| prod | 1 972 | 4 Deployment (dont postgres-exporter), 1 StatefulSet, 5 Service, 2 HPA, 2 Ingress, 2 PDB, 2 PVC, 1 CronJob, 2 ConfigMap, 3 ServiceMonitor, 1 PrometheusRule, Namespace, NetworkPolicy |

Seul le **rendu** est validé. Aucun `kubectl apply` n'a été fait (pas de cluster
disponible sur la machine de test), donc pas de validation côté serveur ni de pods démarrés.

## Changements par rapport à la branche dormante

| Branche `kubernetes` | Ici | Pourquoi |
|---|---|---|
| `postgis/postgis:16-3.4` | `pgrouting/pgrouting:16-3.5-3.7.3` | `main` utilise `pgr_dijkstra` : PostGIS seul casse le routage |
| images `-api` et `-dashboard` | une image `lyonflowfull-app` | même `Dockerfile` pour les deux, comme en Compose |
| `gnn-trainer` (CronJob GPU) | supprimé | GNN purgé de `main` ; le réentraînement XGBoost est fait par Airflow |
| `redis` | supprimé | Redis retiré de `main` (LocalExecutor) |
| `commonLabels` | `labels` | `commonLabels` est déprécié |
| référence `base/secrets` absente → build en échec | Secret factice en dev, SealedSecret en prod | la base ne rendait pas |
| monitoring dans la base | `Component`, prod seulement | les CRD du Prometheus Operator ne sont pas présentes en dev |
| git-sync des DAGs sur la branche `kubernetes` | branche `main` | |

## Reste à faire avant une vraie bascule

1. **Images** : publier `ghcr.io/pduclos/lyonflowfull-app:0.5.0` (aucune image n'est
   poussée aujourd'hui) et l'image Airflow (`Dockerfile.airflow`).
2. **Airflow** : installer le chart Helm avec `base/airflow/values.yaml`. Il faut vérifier
   les 27 DAGs sous KubernetesExecutor, car ils ont été écrits pour LocalExecutor
   avec volumes partagés (`/tmp/models`).
3. **MinIO** : pas encore de manifeste. Il faut soit un StatefulSet MinIO, soit un
   stockage objet managé pour l'archivage Silver.
4. **Nginx / TLS** : remplacé par ingress-nginx + cert-manager (annotations prêtes,
   `ClusterIssuer` à créer).
5. **Données** : migrer le dump Postgres du VPS (`pg_dump` → `restore`), puis rejouer
   les health checks.
6. **Tests** : `kubectl apply --dry-run=server` sur un cluster kind/k3d, puis test de charge.
