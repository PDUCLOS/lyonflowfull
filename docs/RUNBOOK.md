# LyonFlowFull — Runbook opérationnel

## Procédures d'urgence

### Service down

**Symptôme** : Container `lyonflow-xxx` status != "Up (healthy)"

```bash
# 1. Logs
docker compose logs --tail=200 streamlit

# 2. Restart
docker compose restart streamlit

# 3. Si toujours KO, hard restart
docker compose down streamlit && docker compose up -d streamlit

# 4. Vérifier healthcheck
docker compose ps streamlit  # status = "Up (healthy)"

# 5. Smoke test
curl http://localhost/api/health
```

### DB saturée / disque plein

**Symptôme** : `df -h /` > 90%, requêtes lentes

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
"

# 3. VACUUM pour récupérer l'espace
docker compose exec postgres psql -U lyonflow -d lyonflow -c "VACUUM FULL;"
```

### Airflow DAG échoue

**Symptôme** : Tâche Airflow en échec (rouge dans l'UI)

```bash
# 1. Voir le log de la tâche
# Via UI : Admin > Tasks > [task] > Log
# Ou en CLI :
docker compose exec airflow-webserver airflow tasks log <dag_id> <task_id> <execution_date>

# 2. Clear & retry
docker compose exec airflow-webserver airflow tasks clear <dag_id> -t <task_id> -e <exec_date>
docker compose exec airflow-webserver airflow tasks run <dag_id> <task_id> <exec_date>

# 3. Si récurrent : investiguer la source (transform_to_silver logs)
docker compose logs --tail=100 transform_bronze_to_silver
```

### Modèle ML en chute de performance

**Symptôme** : MAE > prev × 1.15 (alerte DAG)

```bash
# 1. Voir les métriques
docker compose exec mlflow mlflow runs list --experiment-name lyonflow-traffic

# 2. Comparer avec version précédente
docker compose exec mlflow mlflow runs describe <run_id>

# 3. Rollback vers version précédente (dans gold.predictions_vs_actuals)
docker compose exec streamlit python -c "
from src.models.xgboost_speed import XGBoostSpeedModel
m = XGBoostSpeedModel()
m.load([5, 60, 180, 360])
print('Modèle chargé — re-déploiement possible')
"

# 4. Forcer retrain
docker compose exec airflow-webserver airflow dags trigger retrain_xgboost_speed
```

### Panne Redis (Celery broker)

**Symptôme** : Tasks Airflow ne se lancent pas

```bash
# 1. Check
docker compose exec redis redis-cli ping

# 2. Restart Redis
docker compose restart redis

# 3. Vérifier que Airflow reprend
docker compose exec airflow-webserver airflow celery worker  # dans container worker
```

### Disque VPS plein

**Symptôme** : Pas de réponse aux commandes `docker compose`

```bash
# 1. Vérifier
df -h /
du -sh /opt/lyonflow/*

# 2. Purger images Docker inutilisées
docker image prune -a --filter "until=24h"
docker volume prune

# 3. Purger anciens backups
find /opt/lyonflow/backups -name "lyonflow_*" -mtime +7 -delete

# 4. Logs rotatés
find /var/log -name "*.gz" -mtime +30 -delete
```

## Maintenance planifiée

### Daily
- ✅ Airflow tourne (6 DAGs schedulés)
- ✅ Backups Bronze/Postgres tournent
- ✅ Health checks OK

### Weekly
- [ ] Vérifier métriques modèles (MAE/R²)
- [ ] Vérifier espace disque
- [ ] Vérifier les alertes drift

### Monthly
- [ ] Mise à jour OS (`apt update && apt upgrade`)
- [ ] Vérifier les CVE deps (`pip-audit`)
- [ ] Rotation des secrets si nécessaire
- [ ] Backup verification : tester un restore

### Quarterly
- [ ] Audit sécurité
- [ ] Revue ADR
- [ ] Performance profiling
- [ ] Capacity planning

## Diagnostic Sprint VPS-6 (fail loud)

### Widget affiche `⚠️ Données pipeline indisponibles`

**Symptôme** : un ou plusieurs widgets Streamlit affichent un `st.error` rouge avec un message contenant `DashboardDataError` ou `[postgresql]` / `[airflow]` / `[mlflow]`.

**Diagnostic** :

```bash
# 1. Identifier la source impactée
# Le message d'erreur contient [postgresql], [airflow] ou [mlflow].
docker compose ps postgres   # doit être "Up (healthy)"
docker compose ps airflow-webserver  # idem
docker compose ps mlflow     # idem

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
# DAG collect_bronze (5min) — doit avoir tourné il y a < 10 min
docker compose exec airflow-webserver airflow dags list-runs -d collect_bronze --state success --limit 3
# DAG transform_silver_to_gold (10min) — idem
```

**Cause typique 3** : `LYONFLOW_DEMO_MODE=1` accidentel sur le VPS (interdit en prod).
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  "grep LYONFLOW_DEMO_MODE /opt/lyonflow/.env"
# Doit afficher : LYONFLOW_DEMO_MODE=0
# Si =1 → corriger + redeploy + restart streamlit
```

**Récupération** : corriger la cause, puis soit attendre le TTL cache (5-30 min),
soit forcer un refresh côté browser (`Ctlr+R`).

Voir [PLAN_NO_MOCK_VPS.md](PLAN_NO_MOCK_VPS.md) pour la politique complète.

### Le dashboard n'affiche plus rien depuis le deploy

**Symptôme** : tous les widgets en erreur après un `make deploy-vps`.

**Cause probable** : nouveau schéma DB (Sprint VPS-6 ajoute `referentiel.lieux_lyon`,
`referentiel.lieux_transports`, `referentiel.lieux_calendrier` + fonctions SQL).

**Fix** : appliquer les scripts de migration sur le VPS :
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224
cd /opt/lyonflow
for sql in scripts/sql/create_referentiel_lieux.sql \
           scripts/sql/create_referentiel_transports.sql \
           scripts/sql/create_lieux_calendrier.sql \
           scripts/sql/create_pathfinder_helpers.sql; do
    PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -f $sql
done
# Recalculer les cadences (idempotent)
python scripts/seed_lieux_calendrier.py
```

### Cron `refresh_lieux_calendrier` recommandé (Sprint 7+)

À mettre en place après le Sprint VPS-6 : un DAG Airflow quotidien 5h qui
recrée `referentiel.lieux_calendrier` depuis les 7 derniers jours de
`gold.tcl_vehicle_realtime`. En attendant, lancer manuellement :
```bash
ssh ... "cd /opt/lyonflow && python scripts/seed_lieux_calendrier.py"
```

## Contacts

| Rôle | Contact |
|------|---------|
| Dev principal | Patrice DUCLOS |
| RGPD / DPO | dpo@lyonflowfull.fr |
| Sécurité | security@lyonflowfull.fr |
| Infra VPS | hostinger support |

## Liens utiles

- Airflow UI : http://localhost/airflow
- MLflow : http://localhost/mlflow
- MinIO Console : http://localhost/minio
- Grafana (à venir) : http://localhost:3000
- Status page (à venir) : https://status.lyonflowfull.fr
