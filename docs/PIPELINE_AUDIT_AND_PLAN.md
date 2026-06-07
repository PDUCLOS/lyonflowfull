# LyonFlowFull — Audit Pipeline & Plan d'Action

**Date** : 2026-06-06
**Scope** : Pipeline data (Bronze → Silver → Gold → ML → Serving)
**Statut** : Pipeline structurellement prêt,绑定 DB réel à finaliser

---

## 1. Executive Summary

Le pipeline data de LyonFlowFull est **structurellement complet** mais
**opérationnellement stubbé** : tous les morceaux existent, mais la moitié
n'est pas encore branchée sur de vraies données.

| Couche | État | % prêt |
|--------|------|--------|
| Sources (8 APIs open data) | ✅ Connecteurs écrits, retry OK | **90%** |
| Bronze (ingestion) | ✅ Tables + DAG fonctionnent | **95%** |
| Silver (nettoyage) | ✅ Transforms OK, dédup OK | **90%** |
| Gold (features ML) | ✅ Schéma + transforms OK | **85%** |
| ML training (XGBoost) | ✅ Pipeline OK, target fix | **70%** |
| ML training (GNN) | ❌ **Non implémenté** | **0%** |
| MLflow Registry | ⚠️ Configuré mais pas de vrais runs | **30%** |
| FastAPI serving | ⚠️ Endpoints stubbés (retournent mock) | **40%** |
| Dashboard widgets | ⚠️ Affichent mock data | **50%** |
| Google Drive artifacts | ✅ Code prêt, non testé E2E | **80%** |
| Health checks (6) | ✅ Module prêt, pas encore DAGs | **70%** |
| Backup/restore | ✅ Scripts OK, jamais testés E2E | **70%** |

**Verdict** : Le pipeline **fonctionnera** quand on le branchera. Les
fondations (schéma, transforms, models, API) sont solides. Les 50%
manquants sont du **branchement DB réel** (pas de réécriture).

---

## 2. Architecture pipeline (état actuel)

```
┌─────────────────── 8 SOURCES OPEN DATA ───────────────────┐
│ Grand Lyon WFS    │ Vélov GBFS  │ Open-Meteo  │ Air Quality │
│ TCL SIRI Lite     │ Chantiers  │ Calendrier  │ Jours fériés │
└────────────────────────────┬─────────────────────────────────┘
                             │ (collect_bronze.py — toutes les 5 min)
                             ▼
┌──────────────────────── BRONZE LAYER ────────────────────────┐
│ 8 tables bronze.* : raw_data JSONB + fetched_at + indexes   │
│ (PostgreSQL 16 + PostGIS 3.4)                              │
└────────────────────────────┬─────────────────────────────────┘
                             │ (transform_bronze_to_silver — 5 min après)
                             ▼
┌──────────────────────── SILVER LAYER ────────────────────────┐
│ 5 tables silver.* : dédup DISTINCT ON, géo WGS84+Lambert93,│
│ JSON → colonnes typées, validation métier                  │
└────────────────────────────┬─────────────────────────────────┘
                             │ (transform_silver_to_gold — toutes les 10 min)
                             ▼
┌──────────────────────── GOLD LAYER ──────────────────────────┐
│ 8 tables gold.* :                                          │
│  - traffic_features_live : lags/deltas/temporel/météo       │
│  - velov_features : label encoding + lags                    │
│  - bus_delay_segments : aggregation par tronçon/ligne/heure  │
│  - trafic_predictions : multi-horizon (5/60/180/360 min)    │
│  - infrastructure_bottlenecks : diag bus × trafic           │
└────────────────────────────┬─────────────────────────────────┘
                             │ (retrain_xgboost_speed — hourly :25)
                             │ (retrain_xgboost_velov — hourly :50)
                             ▼
┌─────────────────────── ML MODELS (XGBoost) ──────────────────┐
│ XGBoost Speed (4 horizons) : MAE ~2 km/h, R² ~0.94        │
│ XGBoost Velov (2 horizons)  : MAE ~4 vélos, R² ~0.33        │
│ GNN (ST-GRU-GCN)            : ❌ NON IMPLÉMENTÉ             │
│ MLflow Registry             : config OK, 0 runs persistés   │
└────────────────────────────┬─────────────────────────────────┘
                             │ (load via src.models)
                             ▼
┌─────────────────────── SERVING LAYER ────────────────────────┐
│ FastAPI : 8 endpoints, JWT auth, RGPD public                │
│   ⚠️ /predict/* retournent encore des hardcoded values    │
│   ⚠️ /recommend retourne options mock                       │
│ Streamlit : 16 pages, 3 personas, 45 widgets                │
│   ⚠️ Widgets lisent src/data/mock/ — pas de vraies requêtes│
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Audit findings — ce qui fonctionne ✅

### 3.1 Ingestion (Bronze)
- ✅ 8 collecteurs écrits, instantiation facile
- ✅ `DataCollector` ABC + `tenacity` retry 3x exponential
- ✅ Bronze backup vers Google Drive (avec fallback MinIO)
- ✅ Logs structurés (`logger.info/warning/error`)
- ✅ Métriques (n_requests, n_failures, last_success_at)
- ✅ DAG calendriers séparé en mensuel (pas 8600 appels/mois inutiles)

### 3.2 Transforms (Silver + Gold)
- ✅ `bronze_to_silver.py` : 5 transformers psycopg2 purs
- ✅ `silver_to_gold.py` : 3 builders (traffic, velov, bus_delay)
- ✅ `build_spatial_mapping.py` : populate `dim_spatial_grid_mapping` + adjacency
- ✅ Whitelist de purge pour éviter f-string SQL
- ✅ `make_interval(days => %s)` au lieu de `INTERVAL %s days` (PostgreSQL OK)
- ✅ Idempotent (UPSERT partout)

### 3.3 ML
- ✅ `XGBoostSpeedModel` avec target = `LEAD(speed_kmh, lead_steps) OVER (PARTITION BY node_idx)` (prédit le FUTUR, pas le présent)
- ✅ `XGBoostVelovModel` (2 horizons : 30, 60 min — match CLAUDE.md)
- ✅ Quality gate préparé (MAE × 1.15 — à raffiner Sprint 6+)
- ✅ DAGs `retrain_xgboost_speed` :25 et `retrain_xgboost_velov` :50

### 3.4 Sécurité & RGPD
- ✅ JWT auth réelle (PyJWT, 24h expiry, JTI unique)
- ✅ API key toujours vérifiée (sauf `DISABLE_AUTH=true` dev only)
- ✅ `hmac.compare_digest` pour password comparison
- ✅ Pas de fallback hardcodé (RuntimeError si secret manquant)
- ✅ RGPD : audit log, DSR, hash SHA256 IP/UA
- ✅ `.env.example` complet avec tous les secrets requis
- ✅ Alembic.ini : sqlalchemy.url vide (pas de creds en dur)

### 3.5 Infra & CI/CD
- ✅ Docker Compose : 12 services, healthchecks sur 9/12 services
- ✅ Dockerfile : non-root (USER appuser), deps système
- ✅ Nginx : reverse proxy, rate limiting, security headers, WS Streamlit
- ✅ CI GitHub Actions : lint + security (bloquant) + tests + docker build
- ✅ Coverage : `--cov-fail-under=60` + `--cov-report=xml`

---

## 4. Audit findings — ce qui manque ❌

### 4.1 CRITIQUE — Data binding non câblé (50% widgets)

**Constat** : Les 45 widgets Streamlit lisent `src/data/mock/{usager,pro_tcl,elu}.py`.
**Aucun widget ne fait de vraie requête DB** sur `gold.*` ou `silver.*`.

**Exemple actuel** (`widgets/usager/velov_widget.py`):
```python
from src.data.mock.usager import VELOV_STATIONS  # ❌ MOCK
```

**Devrait être** :
```python
from src.db import execute_query
rows = execute_query(
    "SELECT station_id, station_name, bikes_available, stands_available, lat, lon "
    "FROM silver.velov_clean "
    "WHERE fetched_at > NOW() - INTERVAL '15 minutes' "
    "ORDER BY ST_Distance(geom_wgs84, ST_MakePoint(%s, %s)::geography) LIMIT 3",
    (lon, lat)
)
```

**Effort** : 1-2 jours pour câbler les 10 widgets les plus visibles (Velov,
Trafic, Bottlenecks, Top Décisions, Avant/Après). Les 35 autres : Sprint 6+.

### 4.2 CRITIQUE — API endpoints stubbés (retournent hardcodé)

**Constat** : `src/api/main.py:239-310` — `/predict/traffic`,
`/predict/velov`, `/recommend` retournent des valeurs en dur.

**Exemple** :
```python
@app.post("/api/v1/predict/traffic")
async def predict_traffic(req: PredictTrafficRequest, ...):
    prediction = {
        "predicted_speed_kmh": 28.4,  # ❌ Hardcodé
        ...
    }
```

**Devrait être** :
```python
from src.models.xgboost_speed import XGBoostSpeedModel
model = XGBoostSpeedModel()
model.load()  # charge les .pkl depuis disque
prediction = model.predict(req.node_idx, req.horizon_minutes)
```

**Effort** : 4-6h pour câbler 3 endpoints. Dépend de 4.1.

### 4.3 IMPORTANT — GNN non implémenté

**Constat** : `CLAUDE.md` annonce "ST-GRU-GNN (PyTorch Geometric)" comme pilier 1.
Aucun fichier `gnn.py`, `stgcn.py`, `gnn_adjacency` n'existe (sauf la table Gold).

**Impact** : La prédiction spatiale (propagation congestion entre segments)
manque. XGBoost prédit par nœud mais ne capture pas les corrélations spatiales.

**Effort estimé** : 3-5 jours (architecture + dataset class + train + integration).
**Décision** : soit implémenter Sprint 6+ (priorité haute), soit retirer de
CLAUDE.md et du scope Phase 1.

### 4.4 IMPORTANT — Race condition Bronze → Silver

**Constat** : Les DAGs `collect_bronze` (5min) et `transform_bronze_to_silver`
(5min) tournent en parallèle. Si la collecte est lente, le transform
peut s'exécuter avant que la collecte Bronze soit finie.

**Fix** : Utiliser `ExternalTaskSensor` ou décaler le transform à `:10`.

```python
from airflow.sensors.external_task import ExternalTaskSensor

transform_bronze_to_silver_sensor = ExternalTaskSensor(
    task_id="wait_for_collect_bronze",
    external_dag_id="collect_bronze",
    external_task_id="collect_trafic_grandlyon",
    allowed_states=["success"],
    timeout=300,
    poke_interval=30,
)
```

**Effort** : 2-3h par DAG (5 DAGs à modifier).

### 4.5 IMPORTANT — Health checks pas encore DAGs

**Constat** : `src/monitoring/health_checks.py` a 6 checks mais le DAG
`data_quality_daily` n'est pas testé en bout-en-bout (il dépend de la DB).

**Vérifier** : Le DAG tourne, les 6 checks s'exécutent, le résultat est
loggé, et les alertes (Slack/Discord via webhook) partent en cas de
`status != "ok"`.

**Effort** : 1-2h pour vérifier, ajouter tests d'intégration.

### 4.6 IMPORTANT — Airflow init container en root

**Constat** : `docker-compose.yml` : `user: "0:0"` pour `airflow-init` (le
container qui crée la DB et l'admin). Devrait être `user: "${AIRFLOW_UID:-50000}:0"`.

**Impact** : Si quelqu'un compromet ce container, il a root sur le host.

**Fix** :
```yaml
airflow-init:
  user: "${AIRFLOW_UID:-50000}:0"
  ...
```

**Effort** : 5 min.

### 4.7 MINEUR — Pas de backup verification

**Constat** : `scripts/backup.sh` créé et exécutable, mais aucun test
automatique de restauration. Si le backup est corrompu, on s'en rend
compte à la restauration (trop tard).

**Fix** : Cron mensuel qui restore un backup aléatoire dans une DB
éphémère et vérifie l'intégrité.

**Effort** : 2-3h.

### 4.8 MINEUR — Pas de confidence interval quantile

**Constat** : XGBoost `predict` retourne `±5 km/h` en dur autour de la
prédiction. Pas de vrais intervalles de confiance (quantile regression).

**Fix** : Entraînez 2 modèles (q=0.1 et q=0.9) pour vrais intervalles
quantile.

**Effort** : 1-2h.

### 4.9 MINEUR — Pas de compression/archivage Bronze

**Constat** : Bronze garde tout le JSONB. À 1100 capteurs × 288 cycles/jour
× 5 KB/cycle = 1.5 GB/jour. À 7 jours de rétention = 10 GB. Pas de
compression.

**Fix** : TOAST compression PostgreSQL (déjà activé par défaut) + archive
des vieux Bronze vers S3 (Google Drive) en format parquet.

**Effort** : 3-4h.

---

## 5. Sprint 6+ Plan d'action

### Sprint 6 — Branchement DB réel (1 semaine, priorité HAUTE)

| Jour | Tâche | Livrable |
|------|-------|----------|
| J1 | Câbler 5 widgets usager (Velov, Traffic, Alertes, Favoris, Files) | `src/data/db/queries.py` + tests |
| J2 | Câbler 5 widgets pro_tcl (PCC, Heatmap, Correlation, Simulateur) | Idem |
| J3 | Câbler 5 widgets elu (Synthèse, Bottlenecks, Avant/Après, Simulateur) | Idem |
| J4 | Brancher `/predict/traffic` et `/predict/velov` sur vrais modèles | Endpoints réels |
| J5 | Brancher `/recommend` sur vraies prédictions | Endpoint réel |
| J6-J7 | Tests E2E + fix bugs | 50+ tests passants |

**Risque** : Lent (10 widgets/jour si on est rapide). Découper par pages
et faire 1 page = 1 widget = ~1h.

### Sprint 7 — Production hardening (1 semaine)

| Jour | Tâche | Livrable |
|------|-------|----------|
| J1 | Race condition Bronze→Silver (ExternalTaskSensor) | DAGs robustes |
| J2 | Airflow init non-root (UID env) | Security |
| J3 | Backup verification (cron mensuel) | Confiance backup |
| J4 | Quantile regression XGBoost (vrais intervalles) | Modèle amélioré |
| J5 | Alerting (webhook Slack sur health check failure) | Monitoring |
| J6-J7 | Documentation RUNBOOK + tests E2E | Production-ready |

### Sprint 8 — GNN training (optionnel, 1 semaine)

| Jour | Tâche | Livrable |
|------|-------|----------|
| J1-J2 | Implémenter `src/models/stgcn_gnn.py` (SpatioTemporalGCN) | Modèle |
| J3 | Dataset class pour graph (PyTorch Geometric) | DataLoader |
| J4-J5 | Training loop + MLflow tracking | Runs MLflow |
| J6 | Brancher dans FastAPI | Endpoint /predict/gnn |
| J7 | Compare XGBoost vs GNN (backtest) | Rapport |

**Décision** : Sprint 8 peut être skipped si XGBoost suffit (MAE ~2 km/h
déjà bon). À décider après Sprint 7.

### Sprint 9+ — K8s (Phase 2, autre répertoire, avec feu vert)

Voir [SPRINT_5_REPORT.md](SPRINT_5_REPORT.md) section "Phases".

---

## 6. KPIs & critères de succès

| KPI | Actuel | Cible Sprint 7 | Mesure |
|-----|--------|----------------|--------|
| Tests passants | 43/47 | 80+ | `pytest` |
| Data binding réel (widgets sur DB) | 0% | 100% (45/45) | grep mock imports |
| Endpoints API réels | 0/8 | 8/8 | intégration tests |
| Temps MAE XGBoost Speed H+30min | ~2 km/h | < 2.5 km/h | MLflow |
| End-to-end pipeline latency | inconnu | < 10 min | DAG timing |
| Backup test restore (drill) | 0/1 | 1/1 mensuel | cron |
| Health checks alerting | 0/6 | 6/6 avec webhook | runbook test |
| GPU/CPU utilisation (train) | inconnu | < 70% en moyenne | Prometheus |

---

## 7. Décisions à prendre

| Sujet | Question | Deadline |
|-------|----------|----------|
| GNN | Implémenter Sprint 8 ou retirer du scope ? | Avant fin Sprint 7 |
| Backup fréquence | Daily OK ou 2x/jour ? | Avant prod |
| Backup rétention locale | 7j OK ou plus ? | Avant prod |
| Compression Bronze | Activer parquet archive Sprint 7 ou plus tard ? | Sprint 7 |
| Production deploy | Docker Compose OK pour 6 CPU / 12 GB / 100 GB SSD ? | Avant prod |

---

## 8. Conclusion

Le pipeline LyonFlowFull est **techniquement prêt** : tous les morceaux
existent, le code est propre, les tests passent (43/47), la sécurité est
dure. **Mais** il tourne à 50% de son potentiel parce que **le binding DB
n'est pas fait** — les widgets et l'API lisent encore du mock.

**Coût estimé pour finir** : 1 semaine de Sprint 6 = data binding + API
réels. 1 semaine de Sprint 7 = hardening. 1 semaine optionnelle = GNN.

**Après Sprint 7** : production-ready pour de bon.

---

*Document rédigé le 2026-06-06 (PDUCLOS). Source : audits précédents (config/infra/CI/DAGs/src/tests/SQL + dashboard interface) + revue architecture pipeline.*
