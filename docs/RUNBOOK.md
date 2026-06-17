# LyonFlowFull — Runbook opérationnel

**Dernière mise à jour : 2026-06-12 (Sprint VPS-8)**

Procédures d'urgence, maintenance planifiée, et diagnostic fail loud (Sprint 8+).

---

## Procédures d'urgence

### Service down

**Symptôme** : Container `lyonflow-xxx` status != "Up (healthy)"

```bash
# 1. Healthcheck global (Sprint 8+)
./scripts/healthcheck-vps.sh

# 2. Logs
docker compose logs --tail=200 streamlit

# 3. Restart
docker compose restart streamlit

# 4. Si toujours KO, hard restart
docker compose down streamlit && docker compose up -d streamlit

# 5. Vérifier healthcheck
docker compose ps streamlit  # status = "Up (healthy)"

# 6. Smoke test
curl http://localhost/api/health
```

### DB saturée / disque plein

**Symptôme** : `df -h /opt` > 90% (sda1 à 80% = 19 Go libres), requêtes lentes

```bash
# 1. Top tables par taille
docker compose exec postgres psql -U lyonflow -d lyonflow -c "
SELECT schemaname || '.' || tablename AS tbl,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
LIMIT 20;
"

# 2. Purge Bronze manuelle (si DAG bloqué)
docker compose exec postgres psql -U lyonflow -d lyonflow -c "
DELETE FROM bronze.trafic_boucles WHERE fetched_at < NOW() - INTERVAL '7 days';
DELETE FROM bronze.velov WHERE fetched_at < NOW() - INTERVAL '3 days';
DELETE FROM bronze.meteo WHERE fetched_at < NOW() - INTERVAL '7 days';
DELETE FROM bronze.air_quality WHERE fetched_at < NOW() - INTERVAL '7 days';
DELETE FROM bronze.tcl_vehicles WHERE fetched_at < NOW() - INTERVAL '3 days';
"

# 3. VACUUM pour récupérer l'espace
docker compose exec postgres psql -U lyonflow -d lyonflow -c "VACUUM FULL;"

# 4. Si sda1 critique : migrer volumes vers sdb (Sprint 9+)
# Cf. scripts/migrate-postgres-to-sdb.sh
```

### Airflow DAG échoue (DAG import error)

**Symptôme** : `airflow dags list-import-errors` affiche une trace

```bash
# 1. Voir l'erreur
docker compose exec airflow-scheduler airflow dags list-import-errors

# 2. Si c'est un "ModuleNotFoundError" :
#    - soit le module n'est pas pushé sur le VPS (cat local | ssh user@host "cat > remote")
#    - soit .airflowignore bloque (vérifier dags/legacy_github/.airflowignore)
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "ls -la /opt/lyonflow/src/ingestion/ | head -20"

# 3. Purger le cache Python (Sprint 8+ leçon)
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "cd /opt/lyonflow && docker compose exec -T airflow-scheduler \
   find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +"

# 4. Restart scheduler
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "cd /opt/lyonflow && docker compose restart airflow-scheduler"

# 5. Vérifier après 30s
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "cd /opt/lyonflow && docker compose exec -T airflow-scheduler airflow dags list | head -15"
```

### Airflow DAG task échoue (runtime)

**Symptôme** : Tâche Airflow en échec (rouge dans l'UI)

```bash
# 1. Voir le log de la tâche
# Via UI : Admin > Tasks > [task] > Log
# Ou en CLI :
docker compose exec airflow-webserver airflow tasks log <dag_id> <task_id> <execution_date>

# 2. Clear & retry
docker compose exec airflow-webserver airflow tasks clear <dag_id> -t <task_id> -e <exec_date>
docker compose exec airflow-webserver airflow tasks run <dag_id> <task_id> <exec_date>

# 3. Si récurrent : investiguer la source
docker compose logs --tail=100 transform_bronze_to_silver

# 4. Test manuel d'une tâche (Sprint 8+ usage courant)
docker compose exec -T airflow-scheduler \
  airflow tasks test collect_bronze collect_airqualityopenmeteo 2026-06-12T07:00:00
```

### Bug ingestion Bronze (UNIQUE INDEX duplicate key)

**Symptôme** : logs Airflow worker `duplicate key value violates unique constraint "uq_<table>_nodup"`

**Cause** : UNIQUE INDEX sur colonnes extracted NULLS (dette schéma Sprint 5). Le collecteur insère 1 ligne par cycle (fetched_at + raw_data JSONB), les colonnes extracted restent NULL → duplicate.

**Fix** (Sprint 8+) : DROP INDEX dans PostgreSQL + mettre à jour `deploy/init-db.sql` :

```bash
# 1. Identifier les uq_*_nodup problématiques
docker compose exec -T postgres psql -U lyonflow -d lyonflow -c "
SELECT indexname FROM pg_indexes
WHERE schemaname='bronze' AND indexname LIKE 'uq_%_nodup';
"

# 2. Drop l'index (idempotent)
docker compose exec -T postgres psql -U lyonflow -d lyonflow -c "
DROP INDEX IF EXISTS bronze.uq_air_quality_nodup;
DROP INDEX IF EXISTS bronze.uq_chantiers_nodup;
"

# 3. Vérifier que deploy/init-db.sql est à jour (commenté les CREATE UNIQUE INDEX)
grep "uq_air_quality_nodup\|uq_chantiers_nodup" deploy/init-db.sql
# Doit afficher en commentaire (--), pas en CREATE actif
```

### Modèle ML en chute de performance

**Symptôme** : MAE > prev × 1.15 (alerte DAG)

```bash
# 1. Voir les métriques
docker compose exec mlflow mlflow runs list --experiment-name lyonflow-traffic

# 2. Comparer avec version précédente
docker compose exec mlflow mlflow runs describe <run_id>

# 3. Rollback vers version précédente (focus H+1h Sprint 8+)
docker compose exec streamlit python -c "
from src.models.xgboost_speed import XGBoostSpeedModel
m = XGBoostSpeedModel()
m.load([60])  # H+1h uniquement
print('Modèle H+1h chargé — re-déploiement possible')
"

# 4. Forcer retrain
docker compose exec airflow-webserver airflow dags trigger dag_live_speed_retrain
```

### Panne Redis (Celery broker)

**Symptôme** : Tasks Airflow ne se lancent pas

```bash
# 1. Check
docker compose exec redis redis-cli ping

# 2. Restart Redis
docker compose restart redis

# 3. Vérifier que Airflow reprend
docker compose exec airflow-webserver airflow celery worker
```

### Disque VPS plein

**Symptôme** : Pas de réponse aux commandes `docker compose`

```bash
# 1. Vérifier
df -h /opt
du -sh /opt/lyonflow/*

# 2. Purger images Docker inutilisées
docker image prune -a --filter "until=24h"
docker volume prune

# 3. Purger anciens backups (sda1)
find /opt/lyonflow/backups -name "lyonflow_*" -mtime +7 -delete

# 4. Logs rotatés
find /var/log -name "*.gz" -mtime +30 -delete
```

### Prometheus / Grafana / Alertmanager down (Sprint 8+)

**Symptôme** : container en restart-loop

```bash
# 1. Vérifier la config
docker logs lyonflow-prometheus --tail 5 2>&1 | head -10
docker logs lyonflow-grafana --tail 5 2>&1 | head -10
docker logs lyonflow-alertmanager --tail 5 2>&1 | head -10

# 2. Causes typiques Sprint 8+ :
#    - Prometheus YAML v2.54 (storage.tsdb.retention.time au mauvais endroit)
#    - Alertmanager webhook URL manquante
#    - --web.enable-lifecycle déclenche reloads en boucle

# 3. Vérifier que deploy/monitoring/prometheus.yml ne contient PAS :
grep "retention.time:" monitoring/prometheus/prometheus.yml
# Doit être en commentaire, pas en config active

# 4. Vérifier que monitoring/alertmanager/alertmanager.yml pointe vers null-receiver
grep "name:" monitoring/alertmanager/alertmanager.yml

# 5. Redémarrer le monitoring stack
docker compose -f docker-compose.monitoring.yml restart prometheus grafana alertmanager
```

---

## Maintenance planifiée

### Daily
- ✅ Airflow tourne (10 DAGs schedulés : 8 Bronze + 1 cron backfill + 1 TomTom no-op)
- ✅ Backups Bronze/Postgres tournent (offsite via `scripts/backup-offsite.sh`)
- ✅ Health checks OK : `./scripts/healthcheck-vps.sh` 20/20
- ✅ Backfill lat/lon tourne toutes les 5 min (Sprint 8+)

### Weekly
- [ ] Vérifier métriques modèles (MAE/R²) via MLflow
- [ ] Vérifier espace disque (sda1 < 80%, sdb < 70%)
- [ ] Vérifier les alertes drift (Evidently à 06h)
- [ ] Vérifier que les DAGs Bronze tournent (12 collecteurs/h attendus)

### Monthly
- [ ] Mise à jour OS (`apt update && apt upgrade`)
- [ ] Vérifier les CVE deps (`pip-audit`)
- [ ] Rotation des secrets si nécessaire
- [ ] Backup verification : tester un restore
- [ ] `docker system prune` (images dangling)

### Quarterly
- [ ] Audit sécurité
- [ ] Revue ADR
- [ ] Performance profiling
- [ ] Capacity planning (migration volumes sda1 → sdb si sda1 > 85%)

---

## Diagnostic Sprint VPS-8 (fail loud)

### Widget affiche `⚠️ Données pipeline indisponibles`

**Symptôme** : un ou plusieurs widgets Streamlit affichent un `st.error` rouge avec un message contenant `DashboardDataError` ou `[postgresql]` / `[airflow]` / `[mlflow]`.

**Diagnostic** :

```bash
# 1. Identifier la source impactée via healthcheck
./scripts/healthcheck-vps.sh

# 2. Logs DB
docker compose logs --tail=100 postgres | grep -i "error\|crash"

# 3. Logs Airflow
docker compose logs --tail=100 airflow-webserver | grep -i "error\|crash"

# 4. Test connexion manuelle
docker compose exec postgres pg_isready -U $POSTGRES_USER -d $POSTGRES_DB
```

**Cause typique 1** : DB/Service down → restart.

**Cause typique 2** : Table Gold vide (DAG en retard) → vérifier que les DAGs tournent :
```bash
# DAG collect_bronze (*/5min) — doit avoir tourné il y a < 10 min
docker compose exec airflow-webserver airflow dags list-runs -d collect_bronze --state success --limit 3
# DAG transform_silver_to_gold (*/10min) — idem
```

**Cause typique 3** : `LYONFLOW_DEMO_MODE=1` accidentel sur le VPS (interdit en prod).
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "grep LYONFLOW_DEMO_MODE /opt/lyonflow/.env"
# Doit afficher : LYONFLOW_DEMO_MODE=0
# Si =1 → corriger + redeploy + restart streamlit
# Si manquant → check-deploy-env.sh a dû bloquer le deploy
```

**Cause typique 4** (Sprint 8+) : Cache Python .pyc obsolète dans container.
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "cd /opt/lyonflow && docker compose exec -T airflow-scheduler \
   find /opt/airflow -name __pycache__ -type d -exec rm -rf {} + && \
   docker compose restart airflow-scheduler airflow-worker"
```

**Récupération** : corriger la cause, puis soit attendre le TTL cache (5-30 min),
soit forcer un refresh côté browser (`Ctrl+R`).

Voir [PLAN_NO_MOCK_VPS.md](PLAN_NO_MOCK_VPS.md) pour la politique complète.

### Le dashboard n'affiche plus rien depuis le deploy

**Symptôme** : tous les widgets en erreur après un `make deploy-vps`.

**Cause probable** : nouveau schéma DB (Sprint VPS-6+ ajoute `referentiel.*`,
Sprint 7+ ajoute `gold.mv_*`, Sprint 8+ drop `uq_*_nodup`).

**Fix** : appliquer les scripts de migration sur le VPS :
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224
cd /opt/lyonflow
for sql in scripts/sql/create_referentiel_lieux.sql \
           scripts/sql/create_referentiel_transports.sql \
           scripts/sql/create_lieux_calendrier.sql \
           scripts/sql/create_pathfinder_helpers.sql \
           scripts/sql/create_mv_line_kpis_otp.sql \
           scripts/sql/audit_dim_spatial_writers.sql; do
    cat $sql | docker compose exec -T postgres psql -U lyonflow -d lyonflow
done
# Recalculer les cadences (idempotent)
docker compose exec -T streamlit python scripts/seed_lieux_calendrier.py
# Backfill lat/lon (Sprint 8)
docker compose exec -T streamlit python /app/scripts/maintenance/backfill_dim_spatial_lat_lon.py
```

### Le pathfinding voiture retourne 0 segments

**Symptôme** : `plan_car_trip()` retourne 0 segments, `distance_m=None`.

**Cause probable 1** (Sprint 8 hotfix 5) : `dim_spatial_grid_mapping.lat/lon` NULL.
```bash
docker compose exec -T postgres psql -U lyonflow -d lyonflow -c "
SELECT count(*) AS total, count(lat) AS with_lat, count(lon) AS with_lon
FROM gold.dim_spatial_grid_mapping;
"
# Si with_lat < total → le DAG backfill n'a pas encore tourné
# Attendre 5 min (DAG cron) ou forcer :
docker compose exec -T streamlit python /app/scripts/maintenance/backfill_dim_spatial_lat_lon.py
```

**Cause probable 2** : coordonnées source invalides (loin de Lyon, ex. > 100km).
```bash
docker compose exec -T streamlit python -c "
from src.routing.pathfinder import compute_itinerary
from src.routing.graph import get_nearest_node, build_routing_graph
G = build_routing_graph()
print('origin node:', get_nearest_node(G, 4.8589, 45.7607))
print('dest node:', get_nearest_node(G, 4.8525, 45.7745))
"
```

### Cron `refresh_lieux_calendrier` tourne mal (Sprint 7+)

**Symptôme** : KPIs TCL pas à jour, `gold.mv_line_kpis_live` stale.

**Vérification** :
```bash
# Le DAG tourne tous les jours à 5h (Sprint 7+)
docker compose exec airflow-webserver airflow dags list-runs -d refresh_lieux_calendrier --limit 3
# Doit avoir 1 succès récent (< 24h)
```

**Refresh manuel** :
```bash
docker compose exec -T postgres psql -U lyonflow -d lyonflow -c "
REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_line_kpis_live;
REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_otp_heatmap;
"
docker compose exec -T streamlit python /app/scripts/seed_lieux_calendrier.py
```

### DAG TomTom no-op (Sprint 8+)

**Symptôme** : `collect_tomtom_traffic` toujours en "success" mais 0 rows.

**Cause** : Module `src.ingestion.tomtom_traffic` n'a jamais eu la classe `TomTomTrafficFlow` (juste des helpers cache/quota). Le DAG est volontairement en no-op.

**Pour réactiver** (Sprint 12+) :
1. Coder `class TomTomTrafficFlow(DataCollector)` avec `fetch_raw()` / `_save_raw()`
2. Ajouter dans `REALTIME_COLLECTORS` de `src/ingestion/__init__.py`
3. Configurer `TOMTOM_API_KEY` dans `/opt/lyonflow/.env` (free tier 2500 req/jour sur https://developer.tomtom.com/)
4. Unpause le DAG : `airflow dags unpause collect_tomtom_traffic`

---

## Contacts

| Rôle | Contact |
|------|---------|
| Dev principal | Patrice DUCLOS |
| RGPD / DPO | dpo@lyonflowfull.fr |
| Sécurité | security@lyonflowfull.fr |
| Infra VPS | hostinger support |
| Healthcheck | `./scripts/healthcheck-vps.sh` |

## Liens utiles

- Airflow UI : http://localhost/airflow
- MLflow : http://localhost/mlflow
- MinIO Console : http://localhost/minio
- Grafana : http://localhost:3000
- Prometheus : http://localhost:9090
- Alertmanager : http://localhost:9093
- Status page (à venir) : https://status.lyonflowfull.fr

## Voir aussi

- [CLAUDE.md](../CLAUDE.md) — Mémoire projet (état, dette, conventions)
- [AGENTS.md](../AGENTS.md) — Mémoire pour assistants IA (phases, règles strictes)
- [docs/PROJECT_STATUS_AND_GOALS.md](PROJECT_STATUS_AND_GOALS.md) — État + objectifs
- [docs/PLAN_NO_MOCK_VPS.md](PLAN_NO_MOCK_VPS.md) — Politique zéro mock
- [docs/MONITORING.md](MONITORING.md) — Prometheus/Grafana
- [docs/VPS_HARDENING.md](VPS_HARDENING.md) — SSH/firewall
- [docs/DEPLOYMENT.md](DEPLOYMENT.md) — Procédure deploy
- [archive/sprints/SPRINT_VPS-8_REPORT.md](../archive/sprints/SPRINT_VPS-8_REPORT.md) — Dernier sprint
