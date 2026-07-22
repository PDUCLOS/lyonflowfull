# PostgreSQL Production Tuning — VPS LyonFlow

> **Statut** : **APPLIQUÉ** (confirmé live 2026-07-01 : `shared_buffers=1GB`,
> `work_mem=32MB`, `maintenance_work_mem=256MB`, `effective_cache_size=3GB`,
> `random_page_cost=1.1`, `effective_io_concurrency=200` tous actifs dans
> `postgresql.auto.conf`). `wal_compression` reste `off` (non appliqué, gain
> marginal). `idle_in_transaction_session_timeout` ajouté 2026-07-01 (0 → 10min,
> hors scope initial de ce doc — root cause d'un incident lock séparé).
> **Cible** : VPS unique `51.83.159.224` (6 CPU, 12 Go RAM, 2× 100 Go SSD)
> **Méthode** : `ALTER SYSTEM` (réversible, traçable dans `postgresql.auto.conf`)

---

## 1. Diagnostic (source : `pg-audit.sh` §1)

Tous les paramètres sont aux **défauts Ubuntu**, ce qui sous-exploite complètement le VPS :

| Paramètre | Actuel (défaut) | Impact |
|-----------|-----------------|--------|
| `shared_buffers` | 128 MB | 98.53% cache hit (cible >99.5%, attendu avec 3-4 GB) |
| `work_mem` | 4 MB | Tri/hash sur disque pour les GROUP BY lourds |
| `maintenance_work_mem` | 64 MB | VACUUM / CREATE INDEX lents |
| `random_page_cost` | 4 (HDD) | Planner défavorise les index sur SSD |
| `effective_cache_size` | 4 GB | Sous-évalué → planner préfère seq scan |

**Conteneur Docker bridé** : `docker-compose.yml` ligne 102-106 → `cpus: "1.0"` + `memory: 2.5G`. Manque de RAM pour `shared_buffers=3GB`.

---

## 2. Cible (justifiée pour 6 CPU / 12 Go RAM / SSD) — **Option A (safe)**

| Paramètre | Cible | Justification |
|-----------|-------|---------------|
| `shared_buffers` | **1 GB** | 25% de la RAM du **conteneur** (4 Go), PAS du host (12 Go). Règle corrigée par Patrice 2026-06-29 (audit Sprint 24+). |
| `work_mem` | **32 MB** | × 8 le défaut. **ATTENTION** : work_mem est par opération × par connexion × par sort/hash. Avec 20-40 connexions concurrentes (Airflow LocalExecutor + dashboard + API + MLflow), peut consommer 0.6-1.3 GB en bursts. Le 32MB (vs 64MB) garde une marge sécurité. |
| `maintenance_work_mem` | **256 MB** | VACUUM / CREATE INDEX 4× plus rapides. Réduit vs 1GB (dans un 4 Go, 1GB maint + 1GB shared + bursts work_mem = OOM-kill). |
| `effective_cache_size` | **3 GB** | ~75% de la RAM conteneur. Hint planner, à 3 il sur-estime pas le cache réel dispo. |
| `random_page_cost` | **1.1** | SSD : accès aléatoire ≈ accès séquentiel. |
| `effective_io_concurrency` | **200** | SSD moderne : permet lectures parallèles. |
| `max_worker_processes` | **6** | = nb CPU. |
| `max_parallel_workers_per_gather` | **2** | Conservateur (peut monter à 3-4 si besoin, à tester). |
| `max_parallel_workers` | **6** | = nb CPU. |
| `max_connections` | 100 (inchangé) | Largement suffisant pour la stack actuelle. |

### Pourquoi **Option A (safe)** plutôt que Option B (perf max) ?

**Option B (rejetée)** aurait été : conteneur Postgres 8-10 GB, shared_buffers=3GB, work_mem=64MB, maintenance_work_mem=1GB. Plus performant MAIS :
- Le host a 12 Go partagé entre airflow + dashboard + api + mlflow + minio + Postgres
- Donner 8-10 Go à Postgres seul affamerait les autres services
- Risque OOM-kill global du host (pas juste du cgroup Postgres)

**Option A (sélectionnée)** : gain principal vient de :
- `work_mem 4MB → 32MB` (× 8) → élimine les sort/hash sur disque pour les aggregats multimodal_grid / bus_traffic_spatial
- `shared_buffers 128MB → 1GB` (× 8) → cache hit ratio 98.5% → >99% (suffisant)
- `random_page_cost 4 → 1.1` → planner utilise plus les index SSD

**Budget RAM conteneur 4 Go (Option A) :**
- shared_buffers : 1 GB (fixe)
- work_mem : 32 MB × N connexions en parallèle (burst, max ~1.3 GB en pic)
- maintenance_work_mem : 256 MB (uniquement pendant VACUUM/CREATE INDEX)
- Autres processus Postgres (postmaster, autovacuum, stats collector, WAL writer) : ~400 MB
- Headroom : ~1 GB
- **Total max worst-case** : 1 + 1.3 + 0.256 + 0.4 = ~3 GB → comfortable dans 4 Go.

---

## 3. Patch docker-compose.yml (Fait dans la même PR)

**Avant** (`docker-compose.yml:102-106`) :

```yaml
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 2.5G
```

**Après** :

```yaml
    deploy:
      resources:
        limits:
          cpus: "2.0"          # 1 → 2 : laisse de la marge pour le parallel gather
          memory: 4G           # 2.5 → 4 : shared_buffers 3GB + overhead
```

Le `cpus: "2.0"` n'est PAS demandé dans le diagnostic Patrice (focus = RAM), mais sans ça le `max_parallel_workers_per_gather=2` ne sert à rien (limité à 1 CPU). À confirmer avant d'appliquer.

---

## 4. Commandes d'application (ALTER SYSTEM)

```bash
# Toutes les valeurs en un seul ALTER SYSTEM par paramètre.
# Chaque commande écrit dans postgresql.auto.conf, lu APRÈS postgresql.conf.
# → Reload (SELECT pg_reload_conf()) ne suffit PAS pour shared_buffers,
#   work_mem (non), maintenance_work_mem (non), max_worker_processes (non).
#   → RESTART complet du conteneur postgres requis.

ssh ubuntu@51.83.159.224 docker exec -i lyonflow-postgres psql -U lyonflow -d lyonflow -P pager=off <<'SQL'
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET work_mem = '32MB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET effective_cache_size = '3GB';
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET max_worker_processes = 6;
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;
ALTER SYSTEM SET max_parallel_workers = 6;
-- max_connections: NE PAS TOUCHER (100 par défaut, OK)
SQL

# Vérifier ce qui a été écrit :
ssh ubuntu@51.83.159.224 docker exec -i lyonflow-postgres \
  cat /var/lib/postgresql/data/postgresql.auto.conf
```

---

## 5. Procédure de restart (downtime ~10-20s)

```bash
# 1. Arrêter les consumers (Streamlit, FastAPI) pour pas de requêtes
#    orphelines pendant le restart
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  docker compose stop streamlit api"

# 2. Restart postgres (les valeurs ALTER SYSTEM sont prises en compte)
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  docker compose restart postgres"

# 3. Attendre que le healthcheck passe
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if docker exec lyonflow-postgres pg_isready -U lyonflow -d lyonflow >/dev/null 2>&1; then
      echo \"Postgres ready after \${i} attempts\"; break
    fi; sleep 2
  done"

# 4. Vérifier que les nouvelles valeurs sont actives
ssh ubuntu@51.83.159.224 docker exec -i lyonflow-postgres psql -U lyonflow -d lyonflow -P pager=off -c "
  SELECT name, setting, unit FROM pg_settings
  WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem',
                 'effective_cache_size','random_page_cost','effective_io_concurrency',
                 'max_worker_processes','max_parallel_workers_per_gather','max_parallel_workers');
"

# 5. Relancer streamlit + api
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  docker compose up -d streamlit api"

# 6. Healthcheck global
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  bash scripts/healthcheck-vps.sh"
```

**Downtime attendu** : 10-20s (pg_isready + warmup shared_buffers vide → première query un peu lente le temps de remplir le cache).

---

## 6. Mesure d'impact (avant/après)

À faire 30 min après le restart, une fois le cache warm :

```bash
# Cache hit ratio (cible >99.5%, avant 98.53%)
ssh ubuntu@51.83.159.224 docker exec -i lyonflow-postgres psql -U lyonflow -d lyonflow -P pager=off -c "
  SELECT round(100.0*sum(heap_blks_hit)/GREATEST(sum(heap_blks_hit)+sum(heap_blks_read),1),2) AS cache_hit_pct
  FROM pg_statio_user_tables;
"

# Durée du refresh bus_traffic_spatial (avant : on a pas mesuré, après : cible -50%)
# Trigger manuel puis log :
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  docker exec lyonflow-airflow-scheduler airflow dags trigger refresh_heavy_mv && \
  sleep 30 && \
  docker logs lyonflow-airflow-scheduler --tail 50 | grep -E 'bus_traffic|bottleneck' "
```

**Gains attendus** (d'après expérience tuning PostgreSQL sur SSD) :
- Cache hit : 98.5 → 99.7%
- Refresh `bus_traffic_spatial` : -40 à -60% (40-60s → 20-30s)
- Refresh `mv_multimodal_grid` : -30 à -50%
- Pas d'impact sur les INSERT `*/5` (write path déjà optimal sur SSD)

---

## 7. Rollback (si tuning casse quelque chose)

```bash
# Restaurer les défauts (ALTER SYSTEM RESET)
ssh ubuntu@51.83.159.224 docker exec -i lyonflow-postgres psql -U lyonflow -d lyonflow -P pager=off <<'SQL'
ALTER SYSTEM RESET shared_buffers;
ALTER SYSTEM RESET work_mem;
ALTER SYSTEM RESET maintenance_work_mem;
ALTER SYSTEM RESET effective_cache_size;
ALTER SYSTEM RESET random_page_cost;
ALTER SYSTEM RESET effective_io_concurrency;
ALTER SYSTEM RESET max_worker_processes;
ALTER SYSTEM RESET max_parallel_workers_per_gather;
ALTER SYSTEM RESET max_parallel_workers;
SQL

# Restart pour appliquer
ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && \
  docker compose restart postgres && \
  sleep 10"
```

`ALTER SYSTEM RESET` supprime la ligne de `postgresql.auto.conf` → retour aux valeurs de `postgresql.conf` (les défauts Ubuntu dans notre cas).

---

## 8. Pourquoi `ALTER SYSTEM` et pas éditer `postgresql.conf` ?

1. **Réversible** : `ALTER SYSTEM RESET nom_param` revient à la valeur par défaut.
2. **Persistant à travers les rebuilds d'image** : `postgresql.conf` peut être écrasé par un `docker compose up -d --build`, pas `postgresql.auto.conf`... ah si en fait, le volume `${POSTGRES_DATA_DIR}` est bind-mounté, donc les deux persistent. Mais ALTER SYSTEM est quand même plus propre car :
3. **Auditable** : `SELECT * FROM pg_file_settings WHERE source = 'override'` montre toutes les valeurs actives avec leur source.
4. **Pas besoin d'éditer un fichier sur le VPS** : on peut tout faire en SQL distant.

---

## 9. Roadmap

- [x] **Sprint 24+** : préparer la doc + les commandes (ce document)
- [ ] **Sprint 25** : appliquer le tuning, mesurer, ajuster si besoin
- [ ] **Sprint 26+** : explorer `pg_prewarm` pour warmup plus rapide après restart, `pg_stat_statements` pour identifier les requêtes candidates à EXPLAIN ANALYZE
