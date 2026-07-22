# Audit Airflow + PostgreSQL — Sprint 24 (2026-06-29)

> Demande : « regarde si dans les DAG Airflow il y a pas de l'optimisation, et
> fais le point aussi sur la base Postgres ». Audit statique du code (26 DAGs,
> migrations, docker-compose). Les chiffres live se confirment avec
> `scripts/pg-audit.sh` (lecture seule, à lancer sur le VPS).

> **MAJ 2026-07-01** — Item #1 (tuning Postgres) confirmé appliqué (voir
> `POSTGRES_TUNING_PROD.md`). **Item #3 (thundering herd :00/:30) toujours PAS
> fait** — root cause confirmé de 3 incidents I/O récurrents le 2026-07-01
> (sessions `refresh_traffic_costs`/`mv_sensor_saturation` bloquées 20-45 min,
> pileup de retries). Mitigation ajoutée en attendant : `statement_timeout=240s`
> sur les connexions psycopg2 de `refresh_osm_traffic_costs.py` et
> `refresh_sensor_saturation.py` (empêche le pileup mais ne règle pas la
> contention de fond — item #3 reste la vraie priorité). `build_spatial_mapping`
> découvert en échec quotidien depuis 8+ jours (même bug : `execute_query()`
> sans statement_timeout bloqué sur `silver.trafic_boucles_clean`), à corriger.

---

## A. Synthèse — le fix Sprint 24 ne suffit pas seul

Le fix gold-stale (Sprint 24) corrige le **symptôme** (refresh CONCURRENTLY cassé,
MV lourdes sur le chemin critique). Mais l'audit révèle **2 causes structurelles**
qui re-créeront des lenteurs : PostgreSQL **sous-dimensionné/non tuné** et tables
gold **sans rétention**. Classées par ROI ci-dessous.

---

## B. PostgreSQL — le point

### B1. Postgres bridé à 2,5 Go / 1 CPU avec config par défaut
`docker-compose.yml` (service `postgres`)

```yaml
deploy: { resources: { limits: { cpus: "1.0", memory: 2.5G } } }
```

* Aucun `postgresql.conf` custom monté → **valeurs par défaut** :
  `shared_buffers=128MB`, `work_mem=4MB`, `maintenance_work_mem=64MB`,
  `effective_cache_size=4GB`.
* Conséquence directe : les `GROUP BY` lourds (MV spatiale, bottleneck, congestion)
  débordent `work_mem=4MB` → **tri/hash sur disque** au lieu de la RAM. C'est une
  cause de fond de la lenteur des refresh, indépendante du scheduling.
* Sur un VPS 12 Go dont Postgres est le cœur, **2,5 Go est trop serré** : la base
  fait tourner 3 DB logiques (lyonflow, airflow, mlflow) + PostGIS + pgRouting.

**Reco** (tuning conservateur pour ~4 Go alloués à Postgres) :

```conf
shared_buffers = 1GB
effective_cache_size = 3GB
work_mem = 32MB            # x8 — supprime les sorts disque des GROUP BY
maintenance_work_mem = 256MB
max_parallel_workers_per_gather = 2
random_page_cost = 1.1     # SSD (défaut 4.0 = pénalise l'index scan)
```

+ relever `memory: 2.5G → 4G` dans le compose. Gain attendu : refresh MV **2-5×**
plus rapides, sans toucher au SQL.

### B2. Tables gold sans rétention → croissance non bornée
`dags/maintenance/maintenance.py`

`PURGE_WHITELIST` ne contient **que du `bronze.*`** (rétention 7 j). **Aucune purge
sur `gold.*`**. Or `gold.traffic_features_live` est **réinséré toutes les 10 min**
sans jamais être purgé : CLAUDE.md le donnait à ~889k lignes, le commentaire
bottleneck à **~4,4 M**. Il grossit en continu.

C'est la **cause amont du Sprint 24** : plus la table grossit, plus le `GROUP BY 7
jours` des MV scanne de lignes, plus le refresh est lent — jusqu'au timeout.

**Reco** : ajouter une purge gold (rétention 3-4 j suffit pour une table « live »)
au DAG `purge_bronze`, ou un DAG dédié. Combiné à la fenêtre MV 48 h (migration
036), les scans gold restent petits et constants dans le temps.

### B3. Confirmer bloat / cache / index inutilisés
À objectiver avec `scripts/pg-audit.sh` :

* **§3 dead tuples** : tables à fort churn (`trafic_predictions` TRUNCATE+INSERT
  toutes les 15 min, `tcl_vehicle_realtime` DELETE 1 h) accumulent du bloat si
  l'autovacuum est trop espacé → envisager `autovacuum_vacuum_scale_factor=0.05`
  sur ces tables.
* **§4 cache hit** : si < 99 %, c'est `shared_buffers` (cf. B1).
* **§5 index inutilisés** : chaque index inutile ralentit les INSERT `*/10`.

---

## C. Airflow — optimisations DAGs

### C1. Thundering herd à :00 et :30
26 DAGs, schedules non décalés. À **:00** et **:30** se déclenchent simultanément :

| Minute | DAGs concurrents |
|--------|------------------|
| `:00` (et :30) | collect_bronze (*/5), transform_bronze_to_silver (*/5), transform_silver_to_gold (*/10), collect_tomtom (*/15), dag_inference_xgboost (*/15), refresh_velov_transit_coupling (*/15), critical_pipeline_health (*/15), refresh_xgb_vs_tomtom (*/30), refresh_congestion_propagation (*/30), refresh_heavy_mv (*/30) |

→ jusqu'à **10 DAGs en parallèle** tapant une base limitée à **1 CPU**. Pics de
contention, lock waits, et c'est exactement quand les refresh lourds rament.

**Reco** : décaler les cadences pour étaler la charge. Exemples :
`refresh_xgb_vs_tomtom` → `5,35`, `refresh_congestion_propagation` → `10,40`,
`refresh_heavy_mv` → `15,45`, `refresh_velov_transit_coupling` → `7,22,37,52`.
Aucune dépendance inter-DAG cassée (ils lisent des tables déjà produites).

### C2. `infrastructure_bottlenecks` — poids mort confirmé
`src/transformation/silver_to_gold.py` (`_BOTTLENECK_SQL`)

* Scanne **7 jours** de `traffic_features_live` (`GROUP BY` heure) → même problème
  de fenêtre que la MV spatiale (cf. migration 036, devrait passer à 48 h).
* Les coordonnées sont **factices** : `45.76 + HASHTEXT(line_ref) % 100 * 0.0002`
  (positions pseudo-aléatoires, pas géographiques).
* CLAUDE.md Sprint 22++ acte son **remplacement** par `mv_bus_traffic_spatial`.

**Reco** : migrer `correlation_matrix.py` / `segment_table.py` vers la MV spatiale,
puis **supprimer** la table + sa task de `refresh_heavy_mv` → −12 min de calcul par
cycle `*/30`.

### C3. `refresh_sensor_saturation` — même bug latent que le Sprint 24
`dags/maintenance/refresh_sensor_saturation.py`

Fait `REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_sensor_saturation` **sans
fallback plain**. Si la MV est un jour recréée/non peuplée (migration, DROP), le
refresh plantera en boucle — exactement le bug qui a vidé `mv_bus_traffic_spatial`.

**Reco** : router ce refresh via `_refresh_matview_safe()` (helper Sprint 24) pour
homogénéiser et immuniser. Idem vérifier `refresh_congestion_propagation`,
`refresh_velov_transit_coupling`, `refresh_xgb_vs_tomtom` (ceux-là ont déjà le
fallback try/except — OK).

### C4. Points sains (RAS)
* `max_active_runs=1` + `catchup=False` partout → pas de backfill sauvage. Bon.
* `build_xgb_training_set` (TRUNCATE+INSERT) et `dag_inference_xgboost`
  (DELETE ciblé) sont idempotents et bornés. Bon.
* Découplage train/inference (Sprint 9+) déjà fait. Bon.

---

## D. Plan d'action priorisé

| # | Action | Effort | Gain | Risque |
|---|--------|--------|------|--------|
| 1 | `postgresql.conf` tuné + RAM 2,5→4 Go (B1) | 30 min | refresh 2-5× + tout le SQL | faible (config) |
| 2 | Rétention `gold.traffic_features_live` 3-4 j (B2) | 1 h | scans gold constants dans le temps | faible (purge bornée) |
| 3 | Décaler les schedules :00/:30 (C1) | 30 min | fin des pics de contention | nul |
| 4 | Fallback `_refresh_matview_safe` sur sensor_saturation (C3) | 20 min | immunise un bug latent | nul |
| 5 | Retirer `infrastructure_bottlenecks` (C2) | 2 h | −12 min/cycle | moyen (migrer 2 consumers) |

#1 + #2 + #3 sont les plus rentables et à risque quasi nul. Ils s'attaquent à la
**cause structurelle** ; le fix Sprint 24 s'attaquait au symptôme immédiat.

---

## E. Pour objectiver (sur le VPS)

```bash
bash scripts/pg-audit.sh          # config mémoire, tailles, bloat, cache, index, MV
bash scripts/healthcheck-gold-stale.sh   # fraîcheur gold post-fix Sprint 24
```

> Aucun commit/push effectué (règle projet). Cet audit est descriptif : les
> changements B1/B2/C1 sont à valider avant implémentation.
