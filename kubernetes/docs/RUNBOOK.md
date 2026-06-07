# RUNBOOK — Opérations courantes K8s LyonFlowFull

## Diagnostic rapide

```bash
# État global
kubectl -n lyonflow get pods,svc,ingress,hpa

# Pods en erreur
kubectl -n lyonflow get pods --field-selector=status.phase!=Running

# Events récents
kubectl -n lyonflow get events --sort-by=.lastTimestamp | tail -20
```

## Pod FastAPI en CrashLoopBackOff

```bash
# Logs container actuel
kubectl -n lyonflow logs deploy/fastapi --tail=100

# Logs container précédent (post-crash)
kubectl -n lyonflow logs deploy/fastapi --previous --tail=100

# Decrire pod (events, probes)
kubectl -n lyonflow describe pod -l app.kubernetes.io/name=fastapi
```

Causes fréquentes :
* `POSTGRES_PASSWORD` mauvais → vérifier sealed-secret + secret réel
* Postgres pas Ready → `kubectl -n lyonflow get pods -l app.kubernetes.io/name=postgres`
* OOM kill → augmenter `resources.limits.memory` dans overlay

## HPA ne scale pas

```bash
# Vérifier métriques disponibles
kubectl -n lyonflow get hpa fastapi -o yaml | grep -A 5 status:

# metrics-server installé ?
kubectl top pods -n lyonflow
```

Si `unknown` → installer metrics-server :
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Certificat TLS bloqué

```bash
# Lister les CertificateRequest
kubectl -n lyonflow get certificate,certificaterequest

# Voir l'ordre Let's Encrypt
kubectl -n lyonflow describe certificate fastapi-tls
```

Si l'order est `pending` plus de 5 min :
* Vérifier que le DNS pointe bien sur l'ingress LB
* Vérifier challenge http01 : `kubectl -n lyonflow get challenges`

## Postgres : connexions saturées

```bash
kubectl -n lyonflow exec -it statefulset/postgres -- psql -U lyonflow -d lyonflow -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
```

Si > 80 connexions → réduire pool SQLAlchemy dans FastAPI ou
scale-down workers Airflow.

## Restart ordonné de tous les services

```bash
kubectl -n lyonflow rollout restart deploy/fastapi
kubectl -n lyonflow rollout restart deploy/streamlit
kubectl -n lyonflow rollout restart deploy/mlflow
helm -n lyonflow upgrade airflow apache-airflow/airflow \
  -f base/airflow/values.yaml --reuse-values --recreate-pods
```

Pour Postgres (StatefulSet, downtime ~30s) :
```bash
kubectl -n lyonflow rollout restart statefulset/postgres
```

## Drain d'un node

```bash
kubectl drain node-XXX --ignore-daemonsets --delete-emptydir-data
# Les PDB (PodDisruptionBudget) garantissent qu'au moins 1 replica reste up.
```

## Backups

| Quoi | Quand | Où |
|------|-------|-----|
| Postgres dump | CronJob 02h UTC | PVC `postgres-backup-pvc` + Object Storage si configuré |
| MLflow artifacts | PVC | À sauvegarder manuellement (TODO : snapshot) |
| Sealed-secrets master key | À l'install | Backup hors cluster (perte = re-sceller tout) |

```bash
# Backup ad-hoc Postgres
./scripts/backup-pg.sh lyonflow ./backups/

# Backup master key sealed-secrets
kubectl -n kube-system get secret sealed-secrets-key \
  -o yaml > sealed-secrets-master.yaml
# Chiffrer avec age et stocker offsite
```

## Cleanup namespace

```bash
# ATTENTION : destructif
kustomize build overlays/dev | kubectl delete -f -
kubectl delete namespace lyonflow
```
