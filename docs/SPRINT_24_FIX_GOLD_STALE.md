# Sprint 24 — Fix & optimisation du pipeline gold stale (2026-06-29)

> Incident : dashboard affiche **0 lignes TCL**, **carte trafic indisponible**
> (`gold.traffic_features_live` stale > 10 min), **`gold.mv_bus_traffic_spatial`
> à 0 ligne**. Ce document explique la cause racine, le correctif, les
> optimisations, et la procédure de déploiement / vérification.

---

## 1. Symptômes observés

| Widget | Symptôme | Table lue |
|--------|----------|-----------|
| Bandeau « LIGNES TCL » | `0` (badge « live DB ») | `gold.tcl_vehicle_realtime` |
| Carte NW / Trafic live | « Carte trafic indisponible » | `gold.traffic_features_live` (âge **22 min**, seuil 10) |
| Pro TCL / Élu_2 bottlenecks | vide | `gold.mv_bus_traffic_spatial` (**0 ligne**) |

Diagnostic terrain (`healthcheck-gold-stale.sh`) :

```
traffic_features_live | 22.1   (min d'âge, attendu < 10)
mv_line_kpis_live     | 167    (OK — non vide)
mv_bus_traffic_spatial| 0      (VIDE)
```

---

## 2. Cause racine — deux problèmes distincts, une même origine

### 2.1 `mv_bus_traffic_spatial` à 0 — bug `REFRESH CONCURRENTLY`

`_refresh_bus_traffic_spatial()` exécutait **uniquement** :

```python
cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_bus_traffic_spatial")
```

**Règle PostgreSQL** : `REFRESH ... CONCURRENTLY` est **interdit tant que la MV
n'a jamais été peuplée** en mode non-concurrent →
`ERROR: CONCURRENTLY ... not populated`.

Conséquence : après chaque `DROP/CREATE ... WITH NO DATA` (migration) ou tout
état non-peuplé, **chaque run plantait avant d'écrire une seule ligne**. La MV
restait éternellement à 0. Les autres refresh du projet (`refresh_lieux_calendrier`,
`refresh_meteo_impact`, …) avaient un fallback `try CONCURRENTLY / except → plain`,
**pas celui-ci**. C'était l'oubli de fond.

### 2.2 `traffic_features_live` stale 22 min — tête de file bloquée

Le DAG `transform_silver_to_gold` (`*/10 min`, `max_active_runs=1`) contenait
**les refresh lourds** en fin de graphe :

* `refresh_mv_bus_traffic_spatial` : `execution_timeout=15 min`, `retries=1`
  → jusqu'à **30 min** d'occupation sur un seul run.
* `build_infrastructure_bottlenecks` : JOIN global par heure sur ~4,4 M lignes,
  `timeout=10 min`.

Avec `max_active_runs=1`, tant que ces tasks tournent, **le run `*/10` suivant
ne démarre pas** → `build_traffic_features` (rapide, 5 min) n'est jamais
ré-exécuté → la carte trafic vieillit jusqu'à 22 min. **La fraîcheur du trafic
temps réel était l'otage des MV analytiques lourdes.**

### 2.3 Gaspillage de calcul — fenêtre vs cadence

`mv_bus_traffic_spatial` agrégeait **7 jours** de données mais se rafraîchissait
toutes les **10-15 min**. En 15 min, 7 jours bougent de ~0,15 %. On recomputait
3 M+ lignes à chaque cycle pour quasi rien.

---

## 3. Correctifs livrés

### 3.1 `_refresh_matview_safe()` — refresh robuste centralisé
`src/transformation/silver_to_gold.py`

Nouveau helper qui remplace la logique dupliquée de `_refresh_multimodal_grid`
et `_refresh_bus_traffic_spatial` :

1. **MV absente** → warning + `return 0` (le DAG continue).
2. **MV non peuplée** (`pg_matviews.ispopulated = false`) → `REFRESH` **plain**
   (obligatoire au 1er passage — corrige le bug 2.1).
3. **MV déjà peuplée** → `REFRESH ... CONCURRENTLY` (pas de lock lecture
   dashboard), **fallback `REFRESH` plain** si CONCURRENTLY échoue (index unique
   manquant, conflit…).
4. **`SET statement_timeout`** (10 min) → garde-fou anti-hang : Postgres abort la
   requête au lieu de laisser le worker Celery + un lock bloqués 30 min.

### 3.2 DAG `refresh_heavy_mv` — découplage du chemin critique
`dags/transforms/refresh_heavy_mv.py` (nouveau)

Les deux refresh lourds **sortent** de `transform_silver_to_gold` et passent dans
un DAG dédié `*/30 min` :

* `build_infrastructure_bottlenecks`
* `refresh_mv_bus_traffic_spatial`

Exécutés **séquentiellement** (pas parallèle) pour éviter l'OOM-kill du worker
sur le VPS 12 Go (deux GROUP BY lourds simultanés). Cadence `*/30` alignée sur la
fenêtre de données 48 h → plus de recompute inutile.

`transform_silver_to_gold` reste `*/10` mais **léger** : traffic, velov,
tcl_realtime, bus_delay, multimodal_grid (refresh 1 km, 2 min). **La fraîcheur du
trafic n'est plus bloquée par les MV analytiques.**

### 3.3 Migration 036 — fenêtre MV 7 j → 48 h
`scripts/sql/migration_036_bus_traffic_spatial_48h.sql`

`DROP + CREATE` idempotent de `gold.mv_bus_traffic_spatial` avec
`INTERVAL '48 hours'` (au lieu de `'7 days'`) sur les deux sources. Scan ÷3 sur
`traffic_features_live`. **Logique métier strictement inchangée** (diagnostic
infra/operations/bus_lane_ok/ok, zones 0,001°, ROI downstream). Index unique
`idx_mv_bus_traffic_spatial_pk` recréé → réautorise CONCURRENTLY après le 1er
refresh plain.

---

## 4. Déploiement (sur le VPS `51.83.159.224`)

```bash
# 1. Récupérer le code (rsync / git pull selon ta procédure habituelle)
make deploy-vps        # ou rsync manuel de src/ + dags/ + scripts/sql/

# 2. Appliquer la migration 036 (recrée la MV en fenêtre 48 h)
docker exec -i lyonflow-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < scripts/sql/migration_036_bus_traffic_spatial_48h.sql

# 3. Purger le cache .pyc Airflow (sinon ancienne version des DAGs chargée)
docker exec lyonflow-airflow-scheduler \
  find /opt/airflow -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 4. 1er refresh manuel (plain — la MV vient d'être recréée WITH/ sans données)
docker exec lyonflow-airflow-scheduler \
  airflow dags trigger refresh_heavy_mv

# 5. Vérifier que le nouveau DAG est bien chargé
docker exec lyonflow-airflow-scheduler airflow dags list | grep refresh_heavy_mv
```

---

## 5. Vérification post-déploiement

```bash
bash scripts/healthcheck-gold-stale.sh
```

Attendu :

| Check | Avant | Après |
|-------|-------|-------|
| `traffic_features_live` âge | 22 min | **< 10 min** |
| `mv_bus_traffic_spatial` count | 0 | **> 0** |
| Run `transform_silver_to_gold` durée | 15-30 min | **< 5 min** |
| Task `refresh_mv_bus_traffic_spatial` | plante (CONCURRENTLY) | **OK** (plain au 1er passage) |

---

## 6. Fichiers touchés

### Sprint 24 (3 modifiés + 3 nouveaux)

| Fichier | Nature | Changement |
|---------|--------|-----------|
| `src/transformation/silver_to_gold.py` | modifié | helper `_refresh_matview_safe` + refacto des 2 refresh |
| `dags/transforms/transform_silver_to_gold.py` | modifié | retrait des 2 tasks lourdes, docstring/desc à jour |
| `scripts/sql/migration_036_bus_traffic_spatial_48h.sql` | **nouveau** | MV fenêtre 48 h |
| `dags/transforms/refresh_heavy_mv.py` | **nouveau** | DAG `*/30` pour les MV lourdes |
| `scripts/healthcheck-gold-stale.sh` | **nouveau** | diagnostic gold stale |
| `docs/SPRINT_24_FIX_GOLD_STALE.md` | **nouveau** | ce document |

### Bonus Sprint 23 glissés dans le même working tree (2 modifiés + 2 nouveaux)

| Fichier | Nature | Changement |
|---------|--------|-----------|
| `scripts/sql/migration_035_mv_latest_sensor_position.sql` | **nouveau** | MV `gold.mv_latest_sensor_position` (corrige le sort RAM 24h+ de `build_spatial_mapping`) |
| `dags/transforms/build_spatial_mapping.py` | modifié | lit la MV (au lieu de `DISTINCT ON` direct sur silver) + task refresh en amont |
| `dags/maintenance/critical_pipeline_health.py` | **nouveau** | DAG monitoring `*/15` (DAGs critiques + fraîcheur gold) |
| `dashboard/components/widgets/pro_tcl/gnn_map.py` | modifié | `pd.to_numeric(errors="coerce")` sur colonnes LEFT JOIN + message d'erreur enrichi |

> Aucun commit/push effectué (règle projet : pas de git sans accord explicite).

---

## 7. Reste à faire (non bloquant)

* **`infrastructure_bottlenecks` est du poids mort** : Sprint 22++ a acté son
  remplacement par `mv_bus_traffic_spatial`. Quand `correlation_matrix.py` et
  `segment_table.py` liront la MV spatiale, supprimer la table + sa task du DAG
  `refresh_heavy_mv` → -12 min de calcul par cycle.

---

## 8. Sprint 24+ (2026-06-29) — quick wins de la section 7 livrés

| Quick win | Statut | Fichier(s) touché(s) |
|-----------|--------|----------------------|
| `statement_timeout` sur `_build_infrastructure_bottlenecks` | ✅ livré | `src/transformation/silver_to_gold.py` |
| Purge `gold.traffic_features_live` > 48 h (env var `GOLD_TRAFFIC_FEATURES_RETENTION_HOURS`) | ✅ livré | `src/transformation/silver_to_gold.py` (`_purge_old_traffic_features`) + `dags/transforms/refresh_heavy_mv.py` (tâche `purge_old_traffic_features`) |
| Index `idx_gold_traffic_features_live_computed_at` | ✅ livré | `scripts/sql/migration_037_idx_purge_traffic_features_live.sql` |
| Retrait de `infrastructure_bottlenecks` du check `critical_pipeline_health` (legacy → MV spatiale) | ✅ livré | `dags/maintenance/critical_pipeline_health.py` |

### Déploiement Sprint 24+

```bash
# 1. Récupérer le code
make deploy-vps

# 2. Appliquer la migration 037 (index sur computed_at — CREATE INDEX IF NOT EXISTS)
docker exec -i lyonflow-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < scripts/sql/migration_037_idx_purge_traffic_features_live.sql

# 3. Purge .pyc Airflow + restart
docker exec lyonflow-airflow-scheduler \
  find /opt/airflow -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 4. Vérifier que la nouvelle tâche est chargée
docker exec lyonflow-airflow-scheduler airflow dags list | grep refresh_heavy_mv
docker exec lyonflow-airflow-scheduler airflow dags show refresh_heavy_mv | grep purge
```

### Vérification post-déploiement Sprint 24+

```bash
# Vérifier que l'index existe (1) et que la table reste à ~50-100k rows
# (48h × 600 sensors × 1 row/5min ≈ 345k max, moins si collecte sparse)
bash scripts/healthcheck-gold-stale.sh
docker exec lyonflow-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
  SELECT count(*), max(computed_at), min(computed_at)
  FROM gold.traffic_features_live;"
```

---

## 9. RCA — incident de déploiement Sprint 24++ (2026-06-29)

> Le **fix applicatif** était correct. C'est le **déploiement** qui a dérapé
> ~1 h. Conservé pour traçabilité RNCP 38777 et pour les fixes préventifs.

### Chronologie

| # | Événement | Cause racine |
|---|-----------|--------------|
| 1 | `pg-audit.sh` révèle 29 GB `silver.trafic_vitesse_propre` + index morts | audit proactif (à traiter à froid) |
| 2 | Deux `deploy-sprint24.sh` lancés en parallèle (chaîne A manuelle + chaîne B nohup) | **pas d'advisory lock** dans `apply-migrations.sh` |
| 3 | A et B racent sur migration 035 (`CREATE INDEX` vs `CREATE MV` concurrents sur `silver.trafic_boucles_clean`) | course + `work_mem=4MB` + `shared_buffers=128MB` |
| 4 | ~1 h de blocage, dont 1 h sur un `COUNT(DISTINCT)` zombie parallèle | monitoring passif, pas de kill-switch |
| 5 | Kill zombie + 4 `REFRESH mv_velov_transit` → 3 queries | — |
| 6 | Kill chaîne B (Mac PID 69553/69566) + `pg_cancel_backend(3455237)` → 1 chaîne | doublon identifié par timing DB↔Mac |
| 7 | Le `CREATE MV` 035 (3450535) rame 52 min en `DataFileRead` | **disque sdb throttlé** (`bi`≈2 MB/s, `wa` bas, `id` haut = IO rate-limit OVH) + swap résiduel 1,2 GB |
| 8 | **DÉCOUPLE** : kill 035 (bonus Sprint 23) + apply **036+037** à la main | 035 ≠ fix incident ; 036/037 en sont indépendants |
| 9 | 036 ✅ (MV 1182 rows) + 037 ✅ (index + tracking). Scheduler restart → `PermissionError` | `deploy-sprint24.sh` avait **oublié le `chown 50000:0`** post-rsync (gotcha Sprint VPS-5) |
| 10 | `sudo chown -R 50000:0 dags/ src/` + purge pyc → scheduler repart | fix immédiat |
| 11 | `mv_bus_traffic_spatial` = 1182 rows, `traffic_features_live` rattrape | **incident clos** |

### Fixes préventifs livrés (Sprint 24++)

| Fix | Fichier | Effet |
|-----|---------|-------|
| **`flock` exclusif** (modes apply uniquement, pas `--status`/`--dry-run`) | `scripts/apply-migrations.sh` | un 2ᵉ run refuse de démarrer → **plus de course** (cause #2/#3) |
| **`chown 50000:0` + `chmod u+rX` post-rsync** sur `dags/ src/ dashboard/` | `scripts/deploy-sprint24.sh` (étape 2/7) | **plus de `PermissionError`** scheduler (cause #9) |
| **Restart scheduler seul** (LocalExecutor, pas de container worker) | `scripts/deploy-sprint24.sh` (étape 5/7) | corrige `No such container: lyonflow-airflow-worker` |
| **RCA** (cette section) | `docs/SPRINT_24_FIX_GOLD_STALE.md` | traçabilité |

### Reste à traiter à froid (post-incident)

* **Re-appliquer migration 035** off-peak (disque idle, burst IO plein) : `./scripts/apply-migrations.sh`. En attendant, `build_spatial_mapping` (DAG 02h30, non-critique) plantera proprement.
* **Tuning PostgreSQL (Option A)** — `docs/POSTGRES_TUNING_PROD.md` : `shared_buffers 128MB→1GB`, `work_mem 4MB→32MB`, conteneur `2.5G→4G`. Aurait évité la lenteur des CREATE MV/INDEX (cause #3/#7).
* **29 GB `silver.trafic_vitesse_propre`** : DAG `silver_archive_to_minio` silently-fail + `VACUUM` ≠ `VACUUM FULL`. À investiguer pour récupérer l'espace disque.
* **Migration 038** (`DROP INDEX CONCURRENTLY` des index morts) : à dé-commenter **après** re-mesure `pg-audit.sh` post-Sprint 24 (les index `traffic_features_live` étaient à `idx_scan=0` à cause des refresh qui plantaient).

> Aucun commit/push effectué (règle projet : pas de git sans accord explicite).
