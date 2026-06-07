# Déploiement LyonFlowFull sur Kubernetes — Guide step-by-step

## 0. Pré-requis

| Outil | Install macOS | Vérif |
|-------|--------------|-------|
| `kubectl` | `brew install kubectl` | `kubectl version --client` |
| `kustomize` | `brew install kustomize` | `kustomize version` |
| `helm` | `brew install helm` | `helm version` |
| `kubeseal` | `brew install kubeseal` | `kubeseal --version` |

Cluster K8s opérationnel (Scaleway Kapsule par défaut) avec kubeconfig
exporté dans `KUBECONFIG`.

## 1. Bootstrap cluster (une fois)

```bash
cd kubernetes
./scripts/bootstrap-cluster.sh
```

Installe :
* ingress-nginx (controller + 2 replicas)
* cert-manager + ClusterIssuer Let's Encrypt prod
* sealed-secrets controller
* Export de la clé publique → `.sealed-secrets/pub-cert.pem`

## 2. Préparer les secrets

```bash
cp ../.env.example .env
# Éditer .env : remplir POSTGRES_PASSWORD, JWT_SECRET_KEY, etc.

./scripts/seal-secrets.sh .env > base/secrets/sealed-secret.yaml
```

Le `sealed-secret.yaml` est chiffré et commit-safe (chiffré pour CE cluster
uniquement). Le `.env` original ne quitte jamais ta machine.

## 3. Build et apply (overlay dev)

```bash
# Vérifier le rendu
kustomize build overlays/dev | less

# Apply
kustomize build overlays/dev | kubectl apply -f -

# Suivre le rollout
kubectl -n lyonflow get pods -w
```

## 4. Airflow (Helm chart séparé)

```bash
helm repo add apache-airflow https://airflow.apache.org
helm upgrade --install airflow apache-airflow/airflow \
  --namespace lyonflow \
  --version 1.13.1 \
  --values base/airflow/values.yaml \
  --wait --timeout 10m
```

## 5. Migration données VPS → K8s

```bash
# 1. Dump VPS
ssh vps "sudo -u postgres pg_dump -Fc lyonflow > /tmp/lyonflow.dump"
scp vps:/tmp/lyonflow.dump ./

# 2. Copier dans le pod K8s et restore
kubectl -n lyonflow cp ./lyonflow.dump postgres-0:/tmp/lyonflow.dump
kubectl -n lyonflow exec -it postgres-0 -- bash -c '
  pg_restore -U lyonflow -d lyonflow --no-owner --no-privileges /tmp/lyonflow.dump
'
```

## 6. DNS

Pointer les A records sur l'IP du LoadBalancer ingress-nginx :

```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

Records à créer :
* `api.lyonflow.fr` → IP LB (prod)
* `app.lyonflow.fr` → IP LB (prod)
* `airflow.lyonflow.fr` → IP LB (prod)
* `api-dev.lyonflow.fr` → IP LB (dev)
* `app-dev.lyonflow.fr` → IP LB (dev)

cert-manager déclenche automatiquement l'émission Let's Encrypt à la
première requête HTTPS.

## 7. Vérification

```bash
# Tous les pods Ready
kubectl -n lyonflow get pods

# Endpoints exposés
kubectl -n lyonflow get ingress

# Test API
curl -fsSL https://api-dev.lyonflow.fr/health

# Test dashboard
open https://app-dev.lyonflow.fr
```

## 8. Promotion dev → prod

```bash
# Mêmes secrets pré-scellés (overlay prod utilise le même base/secrets)
kustomize build overlays/prod | kubectl apply -f -
```

## Rollback

```bash
# Rollback Deployment FastAPI
kubectl -n lyonflow rollout undo deployment/fastapi

# Rollback Airflow (Helm)
helm -n lyonflow rollback airflow

# Restore Postgres depuis backup
CONFIRM=yes ./scripts/restore-pg.sh backups/lyonflow_YYYYMMDD.sql.gz
```
