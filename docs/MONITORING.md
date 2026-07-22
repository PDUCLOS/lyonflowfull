# =============================================================================
# docs/MONITORING.md — Stack monitoring production (Sprint VPS-3 + Sprint 8)
# =============================================================================

# Monitoring LyonFlow — VPS production

**Dernière mise à jour : 2026-06-12 (Sprint VPS-8 — Prometheus/Grafana/Alertmanager tous UP)**

Stack Prometheus + Alertmanager + Grafana, activée via `make monitoring-up`.

## Vue d'ensemble

```
┌─────────────────┐   scrape    ┌──────────────┐
│  FastAPI        │─────────────▶│              │
│  PostgreSQL     │─────────────▶│  Prometheus  │──alert──▶  Alertmanager ──▶ null-receiver
│  Nginx          │─────────────▶│   (15s)      │                          (Sprint 8 — webhooks no-op)
│  Airflow        │─────────────▶│              │
│  Redis, MinIO   │─────────────▶└──────────────┘
│  Node (host)    │─────────────▶        │
└─────────────────┘                       ▼
                                     ┌──────────┐
                                     │ Grafana  │ ◀── dashboards JSON
                                     └──────────┘
```

## Services & ports (Sprint 8 : tous UP et stables)

| Service | Port (localhost) | Exposé via Nginx | Métriques clés | Statut Sprint 8+ |
|---------|------------------|------------------|----------------|------------------|
| Prometheus | 9090 | /prometheus/ | scrape_interval=15s, retention 30j | UP (config YAML v2.54 fixée) |
| Alertmanager | 9093 | /alertmanager/ | Receivers (Sprint 8 : null-receiver) | UP (webhooks désactivés, no-op) |
| Grafana | 3000 | /grafana/ | 1 dashboard "LyonFlow — API + DB Overview" provisionné | UP |
| Node exporter | 9100 | interne | CPU, RAM, disk, load, network | |
| Postgres exporter | 9187 | interne | connections, locks, queries, WAL | |
| Nginx exporter | 9113 | interne | requests, 5xx, latency, active conns | |
| Redis exporter | 9121 | interne | hit rate, memory, evictions | |

Tous les ports sont bindés sur `127.0.0.1` (uniquement). Nginx reverse proxy
fait l'exposition publique (à configurer avec TLS).

## Règles d'alerte

**Sprint 8+** : les `rules/*.yml` sont **désactivées** (`rule_files` commenté dans
`prometheus.yml`) car `database.yml` utilise des fonctions Go templates
(`label_value`, `humanizeBytes`) non définies par défaut en Prometheus
v2.54. Réactivation Sprint 13+ avec template global.

| Fichier | Cible | Alertes (quand réactivé) |
|---------|-------|---------|
| `rules/api.yml` | API FastAPI | 5xx > 5%, p95 > 1s, API down, traffic spike >100rps |
| `rules/database.yml` | PostgreSQL | connections > 85%, DB down, long queries, lock contention, disk > 85%, WAL > 10GB |
| `rules/system.yml` | VPS host + Docker + TLS | CPU > 80%, RAM > 90%, load > 4, container restarting, container down, cert TLS expire < 14j |

## Webhook Discord (ou Slack) — DÉSACTIVÉ Sprint 8

Sprint 8 : `ALERT_WEBHOOK_URL` n'est pas dans `.env`, donc Alertmanager
plante en `unsupported scheme "" for URL` (restart-loop). Fix appliqué :
**receivers webhooks désactivés**, Alertmanager pointe vers un
`null-receiver` (no-op silencieux). Prometheus continue à scrapper
et à évaluer les règles, mais aucune alerte n'est pushée vers
Discord/Slack.

**Pour réactiver** (Sprint 13+) :
1. Provisionner un canal Discord/Slack et récupérer le webhook URL
2. Ajouter `ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...` dans `/opt/lyonflow/.env`
3. Décommenter les `webhook_configs:` dans `monitoring/alertmanager/alertmanager.yml`
4. Restart Alertmanager : `docker compose -f docker-compose.monitoring.yml restart alertmanager`

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

# Healthcheck complet (Sprint 8+)
./scripts/healthcheck-vps.sh
```

## Dashboards Grafana provisionnés

1. **LyonFlow — API + DB Overview** (uid: `lyonflowoverview`)
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
- **Webhook Discord vide (Sprint 8+)** : `null-receiver` configuré, pas de crash.
  Réactivation Sprint 13+ cf. ci-dessus.
- **Backup Prometheus data** : actuellement non sauvegardé (volume Docker).
  Sprint VPS-2 backup.sh ne couvre que PostgreSQL. À ajouter en post-prod.

## Sprint suivant (VPS-4)

- Métriques business FastAPI (compteurs par endpoint, latence par persona)
- ML training metrics (loss, accuracy via MLflow)
- Métriques Airflow (DAG duration, success rate)
- Réactiver les rules/*.yml avec template global (Sprint 13+)
- Tests E2E pour valider que les exporters scrapent bien
