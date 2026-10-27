# Monitoring — Prometheus + Grafana + Alertmanager

Deploye via Helm chart `kube-prometheus-stack` (Prometheus Operator).
Les manifests YAML de ce dossier complement le chart : ServiceMonitor,
PrometheusRule, dashboards Grafana JSON.

## Install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kps prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --version 56.21.4 \
  --values values.yaml \
  --wait --timeout 10m
```

## Manifests fournis

| Fichier | Role |
|---------|------|
| `values.yaml` | Helm values (selector, persistance, ingress) |
| `servicemonitor-fastapi.yaml` | Scrape `/metrics` FastAPI |
| `servicemonitor-postgres.yaml` | Scrape postgres-exporter (sidecar) |
| `servicemonitor-airflow.yaml` | Scrape Airflow webserver `/admin/metrics` |
| `prometheusrule-alerts.yaml` | Regles d'alerte (HPA, DB connections, errors) |
| `grafana-dashboards/` | JSON dashboards (importes auto via ConfigMap) |

## Acces

| Service | URL interne | URL externe |
|---------|------------|-------------|
| Prometheus | `kps-kube-prometheus-stack-prometheus.monitoring.svc:9090` | `https://prom.lyonflow.fr` |
| Grafana | `kps-grafana.monitoring.svc:80` | `https://grafana.lyonflow.fr` |
| Alertmanager | `kps-kube-prometheus-stack-alertmanager.monitoring.svc:9093` | `https://alerts.lyonflow.fr` |

Credentials initiaux Grafana : `admin` / valeur de
`kubectl -n monitoring get secret kps-grafana -o jsonpath='{.data.admin-password}' | base64 -d`
