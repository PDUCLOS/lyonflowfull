# Diagnostic VPS — Dashboard LyonFlowFull

> Date : 2026-06-19 · Version : v0.7.0 · Branche : `vps`

## 1. Widgets avec messages "vide" — Diagnostic par page

### Pro_1_PCC_Live (4 quadrants)

| Widget | Message affiché | Source SQL | Cause probable | Fix |
|--------|----------------|------------|----------------|-----|
| **Carte bus GPS** | "Aucun bus en circulation" | `silver.tcl_vehicles_clean WHERE measurement_time >= NOW() - 15 min` | Fenêtre trop serrée (était 5 min, fixé à 15 min). Si persiste : DAG `collect_bronze_data` ou `transform_bronze_to_silver` stuck | Deployer le fix `db_query.py` (commit en attente) |
| **Alertes live** | "Aucun chantier actif ni alerte en cours" | `silver.chantiers_actifs WHERE is_active = true` | Table vide OU collecteur chantiers pas alimenté OU aucun chantier en cours (légitime) | Vérifier données (voir check 1.1) |
| **Heatmap OTP** | "Aucune donnée OTP" | `gold.mv_otp_heatmap` | MV pas peuplée / DAG `transform_silver_to_gold` stuck | Vérifier MV (voir check 1.2) |
| **Top bottlenecks** | "Aucun bottleneck détecté" | `gold.infrastructure_bottlenecks` | Table vide — le DAG `build_infrastructure_bottlenecks` dépend de bus_delay + traffic | Vérifier (voir check 1.3) |
| **KPIs par ligne** | "Aucun KPI ligne disponible" | `gold.mv_line_kpis_live` | MV pas peuplée | Vérifier (voir check 1.4) |

### Usager_1_Mon_Trajet

| Widget | Message | Source SQL | Cause probable |
|--------|---------|------------|----------------|
| **Prédiction trafic** | "Pas de prédiction H+1h" | `gold.trafic_predictions WHERE computed_at >= NOW() - 2h` | DAG `dag_inference_xgboost` stuck ou modèle pas chargé (baseline 30.0 bug) |
| **Météo** | "Météo indisponible" | `silver.meteo_hourly` | Collecteur Open-Meteo pas alimenté |
| **Vélov** | "Aucune station Vélov" | `silver.velov_clean` | Collecteur GBFS pas alimenté |

### Elu_1_Synthese

| Widget | Message | Source SQL | Cause probable |
|--------|---------|------------|----------------|
| **KPI cards** | "Aucun KPI disponible" | `gold.mv_kpis_12_months` | MV pas créée ou vide |
| **Bottleneck map** | "Aucun bottleneck disponible" | `gold.infrastructure_bottlenecks` | Même que Pro_1 |

### Pro_3_Correlation

| Widget | Message | Source SQL | Cause probable |
|--------|---------|------------|----------------|
| **Correlation matrix** | "Aucun segment bottleneck" | `gold.infrastructure_bottlenecks` | Table vide |
| **Coherence TomTom** | "Aucune paire" | `gold.v_coherence_tomtom_vs_grandlyon` | Vue pas créée (migration 14) OU `TOMTOM_API_KEY` pas dans `.env` |
| **Multimodal heatmap** | "Aucune cellule" | `gold.mv_multimodal_grid` | MV pas créée (migration 17) |
| **Bus × trafic spatial** | "Pas de données" | `gold.mv_bus_traffic_spatial` | MV pas créée (migration 18) |

---

## 2. Commandes diagnostic VPS

Se connecter au VPS puis exécuter dans l'ordre :

### 2.1 État général

```bash
# Santé globale (20 checks)
cd /opt/lyonflow && ./scripts/healthcheck-vps.sh

# Containers UP ?
docker compose ps --format "table {{.Name}}\t{{.Status}}"

# Disque
df -h /dev/sda1 /dev/sdb1
```

### 2.2 DAGs Airflow — derniers runs

```bash
# Collecteurs Bronze (doivent tourner */5 min)
docker exec airflow-scheduler airflow dags list-runs -d collect_bronze_data --limit 5

# Transform Silver → Gold (doit tourner */10 min)
docker exec airflow-scheduler airflow dags list-runs -d transform_silver_to_gold --limit 5

# Inference XGBoost (doit tourner */30 min)
docker exec airflow-scheduler airflow dags list-runs -d dag_inference_xgboost --limit 3

# TomTom (doit tourner */15 min)
docker exec airflow-scheduler airflow dags list-runs -d collect_tomtom_traffic --limit 3
```

### 2.3 Données Bronze — fraîcheur

```bash
docker exec postgres psql -U lyonflow -d lyonflow -c "
SELECT 'trafic_boucles' AS source, COUNT(*) AS n, MAX(fetched_at) AS last_fetch
FROM bronze.trafic_boucles WHERE fetched_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'tcl_vehicles', COUNT(*), MAX(fetched_at)
FROM bronze.tcl_vehicles WHERE fetched_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'velov', COUNT(*), MAX(fetched_at)
FROM bronze.velov WHERE fetched_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'meteo', COUNT(*), MAX(fetched_at)
FROM bronze.meteo WHERE fetched_at > NOW() - INTERVAL '2 hours'
UNION ALL
SELECT 'chantiers', COUNT(*), MAX(fetched_at)
FROM bronze.chantiers
UNION ALL
SELECT 'tomtom', COUNT(*), MAX(fetched_at)
FROM bronze.tomtom_traffic WHERE fetched_at > NOW() - INTERVAL '1 hour'
ORDER BY source;
"
```

### 2.4 Données Silver — fraîcheur

```bash
docker exec postgres psql -U lyonflow -d lyonflow -c "
SELECT 'tcl_vehicles_clean' AS table_name, COUNT(*) AS n, MAX(measurement_time) AS latest
FROM silver.tcl_vehicles_clean WHERE measurement_time > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'velov_clean', COUNT(*), MAX(fetched_at)
FROM silver.velov_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'meteo_hourly', COUNT(*), MAX(measurement_time)
FROM silver.meteo_hourly WHERE measurement_time > NOW() - INTERVAL '2 hours'
UNION ALL
SELECT 'chantiers_actifs', COUNT(*), MAX(fetched_at)
FROM silver.chantiers_actifs WHERE is_active = true
UNION ALL
SELECT 'trafic_boucles_clean', COUNT(*), MAX(fetched_at)
FROM silver.trafic_boucles_clean WHERE fetched_at > NOW() - INTERVAL '1 hour'
ORDER BY table_name;
"
```

### 2.5 Données Gold — tables et vues matérialisées

```bash
docker exec postgres psql -U lyonflow -d lyonflow -c "
SELECT 'traffic_features_live' AS table_name, COUNT(*) AS n, MAX(fetched_at) AS latest
FROM gold.traffic_features_live WHERE fetched_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'tcl_vehicle_realtime', COUNT(*), MAX(recorded_at)
FROM gold.tcl_vehicle_realtime WHERE recorded_at > NOW() - INTERVAL '1 hour'
UNION ALL
SELECT 'trafic_predictions', COUNT(*), MAX(computed_at)
FROM gold.trafic_predictions WHERE computed_at > NOW() - INTERVAL '2 hours'
UNION ALL
SELECT 'infrastructure_bottlenecks', COUNT(*), NULL::timestamptz
FROM gold.infrastructure_bottlenecks
UNION ALL
SELECT 'bus_delay_segments', COUNT(*), NULL::timestamptz
FROM gold.bus_delay_segments
ORDER BY table_name;
"
```

### 2.6 Vues matérialisées — existence + fraîcheur

```bash
docker exec postgres psql -U lyonflow -d lyonflow -c "
SELECT schemaname, matviewname,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || matviewname)) AS size
FROM pg_matviews
WHERE schemaname = 'gold'
ORDER BY matviewname;
"
```

### 2.7 Migrations manquantes

```bash
# Vérifier que les migrations récentes ont été appliquées
docker exec postgres psql -U lyonflow -d lyonflow -c "
SELECT EXISTS(SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_multimodal_grid') AS migration_017,
       EXISTS(SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_bus_traffic_spatial') AS migration_018,
       EXISTS(SELECT 1 FROM pg_proc WHERE proname = 'fn_network_health_score') AS migration_019;
"
```

---

## 3. Arbre de décision — Réparation

```
Healthcheck KO ?
├── Container DOWN → docker compose up -d --build
├── Disque sda > 90% → docker system prune + vérifier data-root sdb
└── Healthcheck OK → continuer ci-dessous

DAGs stuck (state = running depuis > 30 min) ?
├── OUI → Airflow UI : Mark Failed + Clear
│         docker exec airflow-scheduler airflow dags unpause <dag_id>
└── NON → continuer

Bronze vide (count = 0 sur 1h) ?
├── trafic_boucles = 0 → API Grand Lyon down OU rate limit
├── tcl_vehicles = 0 → SIRI Lite down OU credentials expirées
├── velov = 0 → GBFS endpoint changed OU rate limit
├── meteo = 0 → Open-Meteo down (rare)
├── tomtom = 0 → TOMTOM_API_KEY manquante dans .env
└── Tous OK → problème Silver, continuer

Silver vide malgré Bronze OK ?
├── OUI → DAG transform_bronze_to_silver stuck
│         → Purger __pycache__ puis relancer :
│           find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +
│           docker restart airflow-scheduler airflow-worker
└── NON → problème Gold, continuer

Gold vide malgré Silver OK ?
├── OUI → DAG transform_silver_to_gold stuck
│         → Même fix : purge __pycache__ + restart
└── NON → données existent mais pas visibles

Données existent mais widgets vides ?
├── Fenêtre temporelle trop courte (NOW() - N min)
│   → Fix déjà appliqué pour buses (5 → 15 min)
│   → Vérifier autres queries si applicable
├── Code pas déployé (ancien code sur VPS)
│   → make deploy-vps
│   → Purger __pycache__ containers Airflow
└── Cache Streamlit périmé
    → Redémarrer container streamlit
```

---

## 4. Migrations à appliquer

| Migration | Fichier | Statut attendu | Commande |
|-----------|---------|----------------|----------|
| 017 | `migration_017_multimodal_grid.sql` | MV `gold.mv_multimodal_grid` | `psql -f scripts/sql/migration_017_multimodal_grid.sql` |
| 018 | `migration_018_bus_traffic_spatial.sql` | MV `gold.mv_bus_traffic_spatial` | `psql -f scripts/sql/migration_018_bus_traffic_spatial.sql` |
| 019 | `migration_019_network_health.sql` | Fonction `gold.fn_network_health_score()` | `psql -f scripts/sql/migration_019_network_health.sql` |

Toutes idempotentes (DROP IF EXISTS + CREATE).

---

## 5. Procédure de réparation complète

```bash
# 1. Se connecter au VPS
ssh -i ~/.ssh/lyonflow_deploy lyonflow@51.83.159.224

# 2. Déployer le code
cd /opt/lyonflow
make deploy-vps

# 3. Appliquer les migrations manquantes
docker exec -i postgres psql -U lyonflow -d lyonflow < scripts/sql/migration_017_multimodal_grid.sql
docker exec -i postgres psql -U lyonflow -d lyonflow < scripts/sql/migration_018_bus_traffic_spatial.sql
docker exec -i postgres psql -U lyonflow -d lyonflow < scripts/sql/migration_019_network_health.sql

# 4. Purger le cache Python (gotcha Sprint 8+)
docker exec airflow-scheduler find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +
docker exec airflow-worker find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +

# 5. Redémarrer les services
docker restart airflow-scheduler airflow-worker streamlit

# 6. Débloquer les DAGs stuck
docker exec airflow-scheduler airflow dags unpause collect_bronze_data
docker exec airflow-scheduler airflow dags unpause transform_bronze_to_silver
docker exec airflow-scheduler airflow dags unpause transform_silver_to_gold
docker exec airflow-scheduler airflow dags unpause dag_inference_xgboost

# 7. Vérifier (attendre 10 min pour 2 cycles)
./scripts/healthcheck-vps.sh
```

---

## 6. Fixes code appliqués (pas encore commités)

| Fichier | Modification | Raison |
|---------|-------------|--------|
| `src/data/db_query.py:833` | `INTERVAL '5 minutes'` → `'15 minutes'` | Fenêtre bus GPS trop serrée vs latence pipeline |
| `dashboard/pages/Pro_1_PCC_Live.py:63` | `hours=2` → `hours=24` | Cohérent avec la query (pas de filtre temporel) |
| `dashboard/pages/Pro_1_PCC_Live.py:65` | Message → "Aucun chantier actif ni alerte en cours" | Source = chantiers, pas "alertes" au sens strict |

### Fichiers Axe 5 en cours (pas finis)

| Fichier | Statut |
|---------|--------|
| `scripts/sql/migration_019_network_health.sql` | ✅ Fait + appliqué VPS 2026-06-19 |
| `src/data/db_query.py` — `get_network_health_score()` | ✅ Fait |
| `src/data/data_loader.py` — `load_network_health_score()` | ✅ Fait |
| `dashboard/components/data_cache.py` — `cached_network_health_score()` | ✅ Fait |
| `dashboard/components/widgets/elu/network_health_gauge.py` | ✅ Fait |
| `dashboard/components/widgets/elu/__init__.py` — wiring | ✅ Fait |
| `dashboard/pages/Elu_1_Synthese.py` — bandeau | ✅ Fait |
| `tests/data/test_network_health.py` | ✅ Fait (17 tests) |

---

## 7. Session migrations VPS — 2026-06-19 13:45 → 15:00

> Action : application des 6 migrations Sprint 15+ (Axes 1, 3, 5) sur le VPS
> production `51.83.159.224` (branche `vps`).
> Demandé par Patrice après état des lieux DB (cf. section 6 mise à jour).

### 7.1 Backup

| Backup | Taille | Localisation | Note |
|--------|--------|--------------|------|
| `schema.dump` | 218 KB | `/opt/lyonflow/backups/pre_migrations_20260619_1245/` | Schema-only de toute la DB |
| `data_targeted.dump` | 62 MB | idem | Data-only des tables impactées : `bus_delay_segments`, `mv_line_kpis_live`, `mv_otp_heatmap`, `tarifs_modes`, `v_coherence_*`, `tcl_vehicle_realtime`, `traffic_features_live` |
| ~~Full backup~~ | ~~n/a~~ | ~~/opt/lyonflow/backups/~~ | **Non fait** — un dump full CRON était en cours depuis 11h34 (PID 848204), jamais arrivé à terme en 4h+. Récupéré ce qui était faisable : schema + data ciblé. |

### 7.2 Migrations appliquées

| # | Migration | Résultat | Notes |
|---|-----------|----------|-------|
| 14 | `gold.v_coherence_tomtom_vs_grandlyon` (CREATE OR REPLACE) + `gold.v_tomtom_gl_drift` | **❌ ÉCHEC** | La table référencée `bronze.tomtom_traffic` n'existe pas — à la place, `bronze.tomtom_flow` (4340 lignes, données figées depuis 2026-06-06). **Dette pré-existante** : quelqu'un a renommé/recréé la table sans mettre à jour le code. **v_coherence_tomtom_vs_grandlyon reste l'ancienne version (partiellement appliquée).** |
| 15 | `gold.mv_line_kpis_live` (DROP/RECREATE) + `gold.mv_otp_heatmap` | ✅ OK | 163 lignes physiques (plus de suffixe `_hNN`), 18 903 triplets OTP. **BUG-01 résolu** : `charge_pct` clampé à 100 via `LEAST(..., 100.0)`. Anciennes valeurs 675%, 1800%, 3951% → toutes à 100% désormais. |
| 16 | `gold.tarifs_modes` (INSERT) | ✅ OK | 13 nouvelles lignes ajoutées : total 30 (tcl=15, velov=9, voiture=6). **À noter** : doublons préexistants TCL/Vélov (clé UNIQUE `(mode, produit, age_min, age_max)` ajoutée mais les INSERT préalables n'étaient pas ON CONFLICT). Nettoyage à planifier. |
| 17 | `gold.mv_multimodal_grid` (DROP/RECREATE) | ✅ OK | 502 cellules. Score multimodal 0-10 + diagnostic dominant (saturated / road_congested / transit_delayed / velov_scarce / ok). |
| 18 | `gold.mv_bus_traffic_spatial` (DROP/RECREATE) | ✅ OK | 2 497 lignes bus × trafic. JOIN spatial 0.001° (~100 m). |
| 19 | `gold.fn_network_health_score()` (DROP/CREATE) | ✅ OK après patch | **Patch nécessaire** : la migration originale référençait `precipitation`/`temperature_2m` (noms spec initial) mais le schéma effectif `silver.meteo_hourly` utilise `rain_mm`/`temperature_c` (cf. Sprint VPS-3 + migration 17). Patch appliqué : `precipitation`→`rain_mm`, `temperature_2m`→`temperature_c`. **Fichier local `scripts/sql/migration_019_network_health.sql` patché** — à commit/push par Patrice. |

### 7.3 Post-migration

- ✅ VACUUM ANALYZE sur les 5 objets impactés (`mv_line_kpis_live`, `mv_otp_heatmap`, `mv_multimodal_grid`, `mv_bus_traffic_spatial`, `tarifs_modes`)
- ✅ REFRESH manuel des MVs (créées avec données par CREATE MATERIALIZED VIEW, rafraîchies via CONCURRENTLY)
- ✅ Streamlit `/_stcore/health` → HTTP 200
- ✅ FastAPI `/health` → `{"status":"ok","version":"0.6.6","db":true}`
- ✅ `__pycache__` purgé sur `lyonflow-airflow-scheduler` et `lyonflow-airflow-worker` (déjà clean)
- ✅ Cleanup fichiers temporaires : `/tmp/migrations/` supprimé, `/tmp/migration_*.sql` dans container postgres supprimés
- ✅ DAG `transform_silver_to_gold` a déjà les tasks `refresh_mv_multimodal_grid` et `refresh_mv_bus_traffic_spatial` (lignes 47-52 + 104-129)

### 7.4 Tests fonctionnels post-migration

```sql
-- mv_multimodal_grid (Axe 1) : 502 cellules, score 0-10
SELECT lat, lon, avg_speed_kmh, pct_congestion, score_multimodal, diagnosis
FROM gold.mv_multimodal_grid WHERE score_multimodal > 5 LIMIT 3;
-- Résultat : cellules "saturated" et "road_congested" retournées ✅

-- mv_bus_traffic_spatial (Axe 3) : 2497 lignes
SELECT line_ref, hour, ROUND(lat::numeric,4), ROUND(lon::numeric,4),
       bus_delay_sec, traffic_speed_kmh, diagnosis
FROM gold.mv_bus_traffic_spatial WHERE diagnosis='infra' LIMIT 3;
-- Résultat : 3 zones infra retournées (bus retard + trafic < 25 km/h) ✅

-- fn_network_health_score (Axe 5) : score 0-100 + diagnosis
SELECT score, diagnosis FROM gold.fn_network_health_score();
-- Résultat : 43.90 / degraded (réseau sous pression actuellement) ✅

-- mv_line_kpis_live charge_pct (BUG-01 fix)
SELECT MAX(charge_pct), MIN(charge_pct), AVG(charge_pct)::numeric(5,2)
FROM gold.mv_line_kpis_live;
-- Résultat : MAX=100, MIN=100, AVG=100 ⚠️
```

⚠️ **`charge_pct = 100% pour TOUTES les lignes** : la formule `SUM(n_observations) / COUNT(*) * 100`
arithmétiquement sature à 100. À raffiner dans une migration ultérieure — pas critique pour
Sprint 15+ (les widgets affichent 100% au lieu de 675%/1800%, donc **progrès**).

### 7.5 Dette ouverte / Actions pour Patrice

| # | Sujet | Impact | Action proposée |
|---|-------|--------|-----------------|
| 1 | **TomTom `bronze.tomtom_traffic` manquant** (existe `bronze.tomtom_flow` avec schéma différent) | Migration 14 reste partiellement appliquée. Widget Pro_TCL "Cohérence sources" continue d'afficher "Aucune paire". DAG `collect_tomtom_traffic` peut être en erreur silencieuse. | Sprint dédié : soit **renommer** `bronze.tomtom_flow` → `bronze.tomtom_traffic` + adapter le schéma, soit **rejouer** `create_tomtom_traffic.sql` après avoir droppé `bronze.tomtom_flow`, soit **adapter** migration 14 + DAG pour utiliser `bronze.tomtom_flow`. |
| 2 | **Migration 19 patchée localement** (`precipitation`→`rain_mm`, `temperature_2m`→`temperature_c`) | Aucune en prod (déjà patché en live), mais le repo local a une version divergente de la migration originelle | Commit + push par Patrice : `git diff scripts/sql/migration_019_network_health.sql` |
| 3 | **Doublons `gold.tarifs_modes`** (clé UNIQUE ajoutée tardivement) | 17 → 30 lignes, mais ~7 doublons TCL/Vélov | Sprint suivant : `DELETE FROM gold.tarifs_modes WHERE id IN (SELECT MAX(id) FROM gold.tarifs_modes GROUP BY mode, produit, age_min, age_max HAVING COUNT(*) > 1)` |
| 4 | **charge_pct = 100% partout** (formule sature) | Widgets affichent "charge max" partout | Réviser formule : utiliser `n_observations / NULLIF(target_freq_per_hour, 0)` où `target_freq_per_hour` est la fréquence de passage planifiée par ligne |
| 5 | **Backup full DB non fait** (CRON interrompu) | Si rollback complet nécessaire, on n'a pas la DB à 100% — seulement schéma + tables impactées | Rejouer `scripts/backup.sh` après les migrations, hors fenêtre de production |
| 6 | **v_tomtom_gl_drift manquant** | Conséquence du #1 | Résolu automatiquement quand #1 sera traité |

### 7.6 Fichiers de backup

```
/opt/lyonflow/backups/pre_migrations_20260619_1245/
├── schema.dump         (218 KB, schema-only complet)
└── data_targeted.dump  (62 MB, data des tables impactées)
```

Rétention : locale uniquement (Sprint VPS-2 : offsite via rclone à programmer si Patrice
veut un backup distant). Nettoyage après 7 jours par le script backup.sh standard.
