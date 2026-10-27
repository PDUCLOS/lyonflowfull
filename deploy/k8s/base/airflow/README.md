# Airflow (Helm chart officiel)

Airflow est déployé via le chart Helm officiel `apache-airflow/airflow`
plutôt qu'avec des manifests Kustomize (le chart gère 15+ ressources et
ses propres CRDs).

## Install

```bash
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# Sceller le secret avant
kubeseal < secret-airflow.yaml > sealed-secret-airflow.yaml
kubectl apply -f sealed-secret-airflow.yaml

# Install
helm upgrade --install airflow apache-airflow/airflow \
  --namespace lyonflow \
  --version 1.13.1 \
  --values values.yaml \
  --wait --timeout 10m
```

## values.yaml

Configuration ciblée pour LyonFlowFull :
* `KubernetesExecutor` — un pod par task, pas de Celery worker pool
* DAGs via `git-sync` depuis le repo (branche `kubernetes`)
* Postgres metastore = service `postgres` du namespace lyonflow
* Redis = service `redis` du namespace lyonflow (broker pour Celery si besoin)
* Webserver Ingress sur `airflow.lyonflow.fr`

## Migration depuis Docker Compose

Les DAGs et `requirements.txt` du repo sont injectés tels quels via git-sync.
Aucune réécriture nécessaire — Airflow 2.9 = même API.

Diff principaux vs docker-compose :
* `LocalExecutor` → `KubernetesExecutor`
* Workers Celery supprimés (pas nécessaires avec KubernetesExecutor)
* DAGs montés via git-sync, pas via volume bind-mount
