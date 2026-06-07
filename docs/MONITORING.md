# =============================================================================
# docs/MONITORING.md — Stack monitoring production (Sprint VPS-3)
# =============================================================================

# Monitoring LyonFlowFull — VPS production

Stack Prometheus + Alertmanager + Grafana, activée via `make monitoring-up`.

## Vue d'ensemble

```
┌─────────────────┐   scrape    ┌──────────────┐
│  FastAPI        │─────────────▶│              │
│  PostgreSQL     │─────────────▶│  Prometheus  │──alert──▶  Alertmanager ──▶ Discord
│  Nginx          │─────────────▶│   (15s)      │                          webhook
│  Airflow        │─────────────▶│              │
│  Redis, MinIO   │─────────────▶└──────────────┘
│  Node (host)    │─────────────▶        │
└─────────────────┘                       ▼
                                    ┌──────────┐
                                    │ Grafana  │ ◀── dashboards JSON
                                    └──────────┘
```

## Services & ports

| Service | Port (localhost) | Exposé via Nginx | Métriques clés |
|---------|------------------|------------------|----------------|
| Prometheus | 9090 | /prometheus/ | scrape_interval=15s, retention 30j |
| Alertmanager | 9093 | /alertmanager/ | Discord webhook |
| Grafana | 3000 | /grafana/ | 1 dashboard "LyonFlowFull — API + DB Overview" provisionné |
| Node exporter | 9100 | interne | CPU, RAM, disk, load, network |
| Postgres exporter | 9187 | interne | connections, locks, queries, WAL |
| Nginx exporter | 9113 | interne | requests, 5xx, latency, active conns |
| Redis exporter | 9121 | interne | hit rate, memory, evictions |

Tous les ports sont bindés sur `127.0.0.1` (uniquement). Nginx reverse proxy
fait l'exposition publique (à configurer avec TLS).

## Règles d'alerte

| Fichier | Cible | Alertes |
|---------|-------|---------|
| `rules/api.yml` | API FastAPI | 5xx > 5%, p95 > 1s, API down, traffic spike >100rps |
| `rules/database.yml` | PostgreSQL | connections > 85%, DB down, long queries, lock contention, disk > 85%, WAL > 10GB |
| `rules/system.yml` | VPS host + Docker + TLS | CPU > 80%, RAM > 90%, load > 4, container restarting, container down, cert TLS expire < 14j |

## Webhook Discord (ou Slack)

Configurer dans `.env` (ou `.deploy.env`) :

```bash
# Discord webhook URL (Server Settings > Integrations > Webhooks)
ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/XXXXX/YYYYY

# Optionnel : webhook séparé pour les critiques (ping @here)
ALERT_WEBHOOK_CRITICAL_URL=https://discord.com/api/webhooks/AAAAA/BBBBB
```

Les templates de messages sont dans `monitoring/alertmanager/` (à enrichir
si besoin). Format par défaut : `[{severity}] {alertname}: {summary}`.

## Commandes utiles

```bash
# Démarrer monitoring
make monitoring-up

# Voir les targets scrapés
make monitoring-status

# Logs temps réel
make monitoring-logs

# UI Prometheus
open http://localhost:9090

# UI Grafana
open http://localhost:3000
# Login: admin / $GRAFANA_ADMIN_PASSWORD (défini dans .env)

# Vérifier une alerte précise
curl -s 'http://localhost:9090/api/v1/alerts' | jq '.data.alerts[] | select(.labels.alertname=="ApiHighErrorRate")'
```

## Dashboards Grafana provisionnés

1. **LyonFlowFull — API + DB Overview** (uid: `lyonflow-overview`)
   - API request rate (rps par endpoint)
   - API p95 latency (ms)
   - API 5xx errors
   - PostgreSQL connections (% du max)

D'autres dashboards à provisionner (post-prod) :
- DAGs Airflow (durée, succès, échec)
- ML training (loss, accuracy, drift)
- MLflow (runs actifs, latency inference)
- Business metrics (utilisateurs par persona, requêtes par endpoint)

## Notes d'opération

- **Prometheus consomme ~500MB-1GB** selon la rétention. À monitorer.
- **Grafana provisioning** : tout dashboard ajouté dans `monitoring/grafana/dashboards/`
  est auto-importé au démarrage (updateIntervalSeconds=30).
- **Alertmanager inhibition** : si DB down, on inhibe les autres alertes DB
  (cf `inhibit_rules` dans alertmanager.yml).
- **Webhook Discord vide** : si `ALERT_WEBHOOK_URL` n'est pas défini,
  Alertmanager log un warning mais ne crash pas.
- **Backup Prometheus data** : actuellement non sauvegardé (volume Docker).
  Sprint VPS-2 backup.sh ne couvre que PostgreSQL. À ajouter en post-prod.

## Sprint suivant (VPS-4)

- Métriques business FastAPI (compteurs par endpoint, latence par persona)
- ML training metrics (loss, accuracy via MLflow)
- Métriques Airflow (DAG duration, success rate)
- Tests E2E pour valider que les exporters scrapent bien
