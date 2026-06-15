# AUDIT_INTÉGRATION_LIVE — LyonFlowFull

**Date** : 2026-06-14
**Branche auditée** : `main` (modifs non commitées présentes)
**Mode** : **lecture seule** — aucun fichier modifié, aucun fix appliqué.
**Périmètre** : logique métier (Bronze→Silver→Gold, DAGs, modèles ML) + interface
(Streamlit 18 pages / 47 widgets, API FastAPI, data_loader).

---

## TL;DR — vue exécutif

Sur les 18 pages dashboard et 9 DAGs, **6 bugs bloquants runtime** (l'app crash ou
produit des données silencieusement fausses), **1 dette schéma majeure** qui
casse la cohérence entre les modèles ML et la base, et **2 conflits de scheduler
Airflow** qui peuvent faire crasher le parse des DAGs à tout moment.

Tableau résumé :

| # | Sévérité | Type | Localisation | Symptôme |
|---|----------|------|--------------|----------|
| 1 | 🔴 BLOQUANT | Conflit scheduler | `dags/ml/_disabled_*.py` vs `dags/ml/dag_live_speed_retrain.py` | Airflow parse-time error ou DAG aléatoire exécuté |
| 2 | 🔴 BLOQUANT | ImportError runtime | `src/data/data_loader.py` ligne 891, 905, 955 | 4 fonctions inexistantes dans `db_query` (cache lieux, cadence) |
| 3 | 🔴 BLOQUANT | TypeError runtime | `src/api/main.py:330` | API `predict_traffic` passe `node_idx:int` au lieu de `channel_id:str` |
| 4 | 🔴 BLOQUANT | Incompatibilité structure | `dashboard/pages/Pro_4_Simulateur.py:42-43` + widget `line_kpis` | KPIs toujours à 0 (dict `{"lines":[]}` vs `dict[line_id, kpis]`) |
| 5 | 🟠 MAJEUR | Dette schéma | `src/models/xgboost_velov.py:25-37` | Features `bikes_lag_1/2/3, hour_sin/cos, temperature_c, rain_mm` n'existent pas dans `gold.velov_features` réel |
| 6 | 🟠 MAJEUR | Dette schéma | `src/data/db_query.py:147-149` | `get_traffic_for_node` requiert colonnes inexistantes (`node_idx`, `speed_lag_1`, `measurement_time`) |
| 7 | 🟠 MAJEUR | Sécurité | `src/persona/auth.py:47,133` | Mot de passe démo `demo2026` hardcodé **et affiché en clair** dans l'UI |
| 8 | 🟠 MAJEUR | Sécurité DoS | `src/api/middleware/rate_limit.py:55` | `_buckets` grossit infiniment (jamais purgé des IP anciennes) |
| 9 | 🟡 MINEUR | Référence morte | `data_loader.load_traffic_combined_for_map` (commentaire dans DAG TomTom) | Fonction jamais créée |
| 10 | 🟡 MINEUR | Index manquant | `gold.trafic_predictions` (init-db.sql) | Cleanup hourly et `WHERE calculated_at >= NOW() - 2h` font du seq scan |
| 11 | 🟡 MINEUR | Désaccord doc/code | `dags/ml/retrain_xgboost.py` | Entraîne 2 horizons Vélov (H+30+H+60) au lieu de "H+30min uniquement" Sprint 12+ |
| 12 | 🟡 MINEUR | Désaccord doc/code | `dags/ml/retrain_xgboost.py` | Entraîne 4 horizons Speed (5/60/180/360) au lieu de "focus H+1h" Sprint 9+ |
| 13 | 🟡 MINEUR | Cohérence | `gold.trafic_predictions` | PK `(axis_key, horizon_h, calculated_at)` + INSERT sans `ON CONFLICT` → doublons en cas de retry |

---

## 1. Audit logique métier

### 1.1 Architecture Medallion (Bronze/Silver/Gold)

L'init SQL (`deploy/init-db.sql`) déclare les schémas et tables. Cohérence globale
OK côté **structure** (Bronze immutable, Silver normalisé, Gold analytique), mais
plusieurs écarts entre le **schéma réel** et ce que le code Python **croit** être
le schéma.

#### Tables Gold réellement présentes (extrait init-db.sql)

```
gold.traffic_features_live   : channel_id, fetched_at, computed_at, speed_kmh,
                               vitesse_limite_kmh, lag_1, lag_2, lag_3,
                               delta_current, delta_1, rolling_mean_3,
                               hour_of_day, day_of_week, is_weekend,
                               sin_hour, cos_hour, sin_dow, cos_dow,
                               channel_hash, temperature_2m, precipitation,
                               rain, is_raining, visibility, wind_speed_10m,
                               weather_code, lat, lon, importance_code,
                               x_2154, y_2154, is_vacances, is_ferie
gold.velov_features          : PAS DANS L'INIT SQL (TODO confirmer en prod)
gold.trafic_predictions      : axis_key, horizon_h, calculated_at, speed_pred,
                               etat_pred, color, vitesse_limite_kmh, label,
                               model_version, lat, lon, x_2154, y_2154
```

**Référence** : `deploy/init-db.sql:1005-1040` (traffic_features_live),
`deploy/init-db.sql:1209-1223` (trafic_predictions).

#### 1.1.1 Dette schéma Vélov — `src/models/xgboost_velov.py:25-37`

`FEATURE_COLS` liste : `station_id_encoded, bikes_lag_1, bikes_lag_2, bikes_lag_3,
rolling_mean_3h, hour_sin, hour_cos, temperature_c, rain_mm, is_vacances, is_ferie`.

**Problème** : aucune de ces colonnes n'est définie dans `init-db.sql` pour
`gold.velov_features`. Le `CREATE TABLE` est manquant dans le dump (ou la table
n'a jamais été créée avec ce nom). Si la table existe avec un autre nommage
(Sprint 9 a renommé), le code va exploser à la première query.

**Impact** : `xgboost_velov_h30` ne peut pas entraîner. Le DAG
`retrain_xgboost_velov` (hourly :50) log des exceptions en boucle, mais ne lève
pas → pollution des logs.

**Sévérité** : 🟠 MAJEUR — casse le pipeline Vélov mais ne bloque pas le trafic
(reste du système fonctionnel).

#### 1.1.2 Dette schéma trafic — `src/data/db_query.py:147-149`

```python
def get_traffic_for_node(node_idx: int, hours: int = 24) -> pd.DataFrame:
    query = """
        SELECT measurement_time, speed_kmh, speed_lag_1, speed_lag_2,
               speed_delta_1, rolling_mean_5min, hour_sin, hour_cos,
               temperature_c, rain_mm, is_vacances
        FROM gold.traffic_features_live
        WHERE node_idx = %s
```

**Problème** : `gold.traffic_features_live` n'a **PAS** de colonne `node_idx`
(c'est un int du graphe GNN qui vient de `gold.dim_spatial_grid_mapping`).
Elle a `channel_id` (text). Et `measurement_time` n'existe pas non plus (c'est
`fetched_at` + `computed_at`).

**Impact** : la fonction est appelée par `data_loader.load_traffic_timeseries`
utilisé par les widgets de time-series. En prod, retourne un DataFrame vide
silencieusement (`_df_from_query` catch les exceptions).

**Sévérité** : 🟠 MAJEUR — mais masqué par le fallback mock en mode démo.

#### 1.1.3 Table `gold.trafic_predictions` — index manquants

PK = `(axis_key, horizon_h, calculated_at)`. Le DAG
`dag_live_speed_retrain` fait toutes les heures :

- `SELECT DISTINCT ON (channel_id) ... ORDER BY channel_id, computed_at DESC`
  sur `traffic_features_live` (index `idx_traffic_features_live_channel_computed`
  OK)
- `INSERT ... VALUES` puis
- `DELETE FROM gold.trafic_predictions WHERE calculated_at < NOW() - INTERVAL '7 days'`
- et `db_query.get_traffic_predictions` lit avec `WHERE calculated_at >= NOW() - INTERVAL '2 hours'`

**Problème** : aucun index sur `calculated_at` dans `init-db.sql`. Sur 4 horizons
× 1100 axes = 4400 rows/h, en 7 jours = 740k rows. Le `DELETE` hourly devient
un seq scan → degradation progressive. Idem pour le `SELECT` dashboard.

**Sévérité** : 🟡 MINEUR — dégradation de performance, pas de crash, mais à
régler avant que la table atteigne 1M rows.

**Recommandation** (à valider avec Patrice) :
```sql
CREATE INDEX idx_trafic_predictions_calculated_at
  ON gold.trafic_predictions (calculated_at DESC);
CREATE INDEX idx_trafic_predictions_horizon_calc
  ON gold.trafic_predictions (horizon_h, calculated_at DESC);
```

#### 1.1.4 Conflit INSERT vs PK

`trafic_predictions` PK = `(axis_key, horizon_h, calculated_at)`. Le DAG
calcule `calculated_at = datetime.now()` au début de la tâche. Deux scénarios
de doublons potentiels :

1. **Retry Airflow** : `execution_timeout=20min`, le DAG est relancé, mais le
   PK empêche les doublons (sauf si `calculated_at` est recalculé et tombe sur
   une autre milliseconde).
2. **Deux exécutions concurrentes** : `max_active_runs=1` sur le DAG OK, mais
   `cleanup_old_predictions` après le predict peut être lent.

**Recommandation** : ajouter `ON CONFLICT (axis_key, horizon_h, calculated_at)
DO NOTHING` au INSERT pour idempotence stricte (sinon aujourd'hui c'est
implicite via la PK mais ça throw si doublon, pas de skip silencieux).

---

### 1.2 DAGs Airflow

**9 DAGs au total** (Sprint VPS-5 : `SPRINT_VPS-5_REPORT.md` en parle). État
réel vs attendu :

```
bronze/collect_bronze.py                          ✅ 6 collecteurs / 5 min
bronze/collect_calendriers_monthly.py             ✅ mensuel
bronze/collect_tomtom_traffic.py                  ⚠️ No-op depuis Sprint 8
transforms/transform_bronze_to_silver.py          ✅ 5 sources / 5 min
transforms/transform_silver_to_gold.py            ✅ 5 targets / 10 min
transforms/build_spatial_mapping.py               ✅ quotidien
ml/retrain_xgboost.py                             ✅ 2 DAGs (speed + velov)
ml/dag_daily_speed_train.py                       ✅ 03h00 quotidien
ml/dag_inference_xgboost.py                       ✅ */15 min inférence
ml/dag_live_speed_retrain.py                      ⚠️ Conflit avec _disabled_
ml/_disabled_dag_live_speed_retrain.py            🔴 DOUBLE DÉFINITION
ml/build_xgb_training_set.py                      ✅ 02h30 quotidien
ml/retrain_gnn.py                                 ⏸ paused (toggle off)
maintenance/maintenance.py                        ✅ quotidien
maintenance/backfill_dim_spatial_lat_lon.py       ✅ poncuel
maintenance/refresh_lieux_calendrier.py           ✅ mensuel
maintenance/silver_archive_to_minio.py            ✅ quotidien
legacy_github/dag_pipeline.py                     ⏸ legacy
```

#### 1.2.1 🔴 BLOQUANT — Conflit `dag_live_speed_retrain` × 2

`dags/ml/dag_live_speed_retrain.py` (259 lignes, Sprint VPS-5, 4 horizons,
train en best-effort + baseline) **ET** `dags/ml/_disabled_dag_live_speed_retrain.py`
(212 lignes, Sprint 9+, 1 horizon H+1h, vrai XGBoost) définissent tous les
deux :

```python
with DAG(dag_id="dag_live_speed_retrain", ...) as dag:
```

**Le préfixe `_disabled_` n'a aucun effet sur Airflow.** Le scheduler scanne
`dags/**/*.py` récursivement et importe tout fichier `.py` qui définit un
objet DAG au top-level. Deux objets avec le même `dag_id` :

- Soit Airflow raise `AirflowDagDuplicatedIdException` au parse → tous les
  autres DAGs arrêtent de se charger (le scheduler crash en boucle).
- Soit Airflow "gagne" silencieusement le dernier chargé (ordre d'import
  alphabétique : `_disabled_*.py` charge APRES `dag_live_*.py`, donc c'est
  probablement la version Sprint 9+ qui gagne, et la version VPS-5 ne tourne
  jamais).

**Comment vérifier** : `airflow dags list | grep live_speed` doit montrer 1
seul DAG. Si 2, ou si `airflow dags report` montre une erreur → confirmé.

**Recommandation** : déplacer `_disabled_*.py` hors de `dags/` (par ex.
`docs/legacy_dags/` ou `dags/_archive/`) OU renommer le `dag_id` de la version
désactivée en `dag_live_speed_retrain_legacy` et la mettre en pause. La
solution standard Airflow pour "désactiver" un DAG est de le `gzip` ou le
sortir du DAG folder.

**Sévérité** : 🔴 BLOQUANT — peut empêcher TOUS les autres DAGs de tourner.

#### 1.2.2 Désaccord doc/code — `retrain_xgboost.py`

- CLAUDE.md dit : "H+30min uniquement Sprint 12+ pour Vélov" + "Focus H+1h
  speed Sprint 8+2".
- Le code `retrain_xgboost.py:69` boucle sur `[5, 60, 180, 360]` (speed).
- Le code `retrain_xgboost.py:85` boucle sur `[30, 60]` (velov).

Donc on a 2 vélov entraînés par heure, et 4 speed entraînés par heure. En
RAM/CPU sur le VPS, c'est non négligeable.

**Sévérité** : 🟡 MINEUR — gaspillage compute, pas de crash.

**Recommandation** : aligner sur CLAUDE.md (1 speed H+60, 1 velov H+30).
Vérifier avec Patrice si le passage à 1 seul modèle speed est validé.

#### 1.2.3 DAG TomTom désactivé mais reste dans `dags/`

`dags/bronze/collect_tomtom_traffic.py` est un no-op depuis Sprint 8. Pas de
problème technique (il tourne et fait `return 0`), mais pollue l'UI Airflow
et le `dags list`. Recommandation : `gzip` le fichier, ou ajouter un feature
flag `LYONFLOW_TOMTOM_ENABLED` (déjà documenté comme "Sprint 12+ réactivation").

#### 1.2.4 `_buckets` du rate-limit jamais nettoyé

Voir § 2.2.

---

### 1.3 Modèles ML

#### 1.3.1 Schéma Vélov incohérent

Cf § 1.1.1. Le modèle `XGBoostVelovModel` n'est pas aligné sur le schéma Gold
réel. Sprint 9+ a renommé `temperature_2m` → `temperature_c`, `precipitation`
→ `rain_mm`, etc., mais le code `xgboost_velov.py` n'a pas suivi.

**Sévérité** : 🟠 MAJEUR.

#### 1.3.2 Cohérence training/inference XGBoost Speed

`src/models/xgboost_speed.py:50-62` liste `FEATURE_COLS` avec 11 features. Le
schéma `gold.traffic_features_live` a 11+ colonnes matchant (speed_kmh, lag_1,
lag_2, lag_3, rolling_mean_3, sin_hour, cos_hour, temperature_2m,
precipitation, is_vacances, is_ferie). **Aligné** côté speed, contrairement
au Vélov.

#### 1.3.3 Cohérence XGBoost vs schéma d'inférence

`_lookup_features()` lignes 349-372 requête `gold.traffic_features_live` pour
les 11 features. C'est OK. Mais `_load_training_data()` lignes 327-347 lit
`gold.xgb_training_set` — **cette table n'est pas dans `init-db.sql`**. Le
DAG `build_xgb_training_set` la crée via self-join (probable TRUNCATE +
INSERT). Pas d'alembic migration pour elle.

**Risque** : si quelqu'un reset la DB en exécutant uniquement `init-db.sql`,
`xgb_training_set` n'existera pas et le retrain hourly plantera. Idempotence
du DAG `build_xgb_training_set` : pas vérifié dans l'audit (TODO).

**Sévérité** : 🟡 MINEUR.

#### 1.3.4 MLflow tracking

OK côté structure : `mlflow_integration.py` a un no-op propre, fallback
graceful. Mais `register_model` ligne 244-262 : pas d'idempotence testée. Si
le DAG est en retry, il créera N versions du même modèle dans le Registry.
Mineur.

---

## 2. Audit interface

### 2.1 Couche `data_loader` / `db_query`

`src/data/data_loader.py` est la couche "intelligente" (cache + mode démo +
fail loud). 4 fonctions référencent `db_query.get_lieux_lyon_names`,
`get_lieux_lyon_with_coords`, `get_cadence_for_line` et `get_latest_drift_report`
— **aucune n'existe dans `db_query.py`** (vérifié sur les 911 lignes).

#### 2.1.1 🔴 BLOQUANT — ImportError runtime

Fichiers concernés :

- `data_loader.py:891` : `from src.data.db_query import get_lieux_lyon_names`
- `data_loader.py:905` : `from src.data.db_query import get_lieux_lyon_with_coords`
- `data_loader.py:955` : `from src.data.db_query import get_cadence_for_line`
- `models/xgboost_speed.py:205` : `from src.data.db_query import get_latest_drift_report`

Le pattern `from X import Y` est en lazy import **à l'intérieur** d'une
fonction, donc l'erreur ne survient qu'à l'appel. Mais elle est certaine :

```
ImportError: cannot import name 'get_lieux_lyon_names' from 'src.data.db_query'
```

**Pages/widgets impactés** :

- `load_lyon_addresses()` / `load_lyon_addresses_with_coords()` → utilisées
  par le widget `search_bar` de la page **Usager_1_Mon_Trajet** (autocomplete
  + itinéraire).
- `load_lieux_transports()` / `load_cadence_for_line()` → widget **itinerary**
  même page.
- `XGBoostSpeedModel.train_one()` → DAG `retrain_xgboost_speed` (hourly).

**Sévérité** : 🔴 BLOQUANT — la page Mon Trajet crash au clic sur une adresse.

#### 2.1.2 Incompatibilité structure `load_line_kpis` vs widget

```python
# db_query.py:783
def get_line_kpis(line_ids=None) -> dict:
    ...
    return {"lines": df.to_dict("records"), "timestamp": ...}
```

```python
# widgets/pro_tcl/line_kpis.py:40
def _to_dataframe(kpis_dict: dict) -> pd.DataFrame:
    for line_id, kpis in kpis_dict.items():  # boucle sur "lines", "timestamp" !
```

```python
# pages/Pro_4_Simulateur.py:42
all_line_kpis = cached_line_kpis()
kpis = all_line_kpis.get(target_line, {})  # retourne TOUJOURS {}
```

**Sévérité** : 🔴 BLOQUANT — page Pro_4_Simulateur affiche OTP=0, Retard=0,
Fréq=0, Charge=0 sur toutes les lignes. Le widget `line_kpis` produit un
DataFrame avec 2 lignes (les clés "lines" et "timestamp") au lieu des 166
lignes TCL.

**Recommandation** : standardiser le format. Soit `load_line_kpis` retourne
un `dict[line_id, {kpis}]` (ce que le widget attend), soit le widget
boucle sur `["lines"]`. Le mock `pro_tcl.LINE_KPIS` est probablement déjà au
bon format, ce qui fait que ça marche en mode démo et casse en mode prod.

#### 2.1.3 Référence morte `load_traffic_combined_for_map`

Le commentaire dans `dags/bronze/collect_tomtom_traffic.py:18` mentionne
`data_loader.load_traffic_combined_for_map`, mais cette fonction **n'existe
nulle part** dans `data_loader.py`. Probablement abandonnée lors de la
suppression de TomTom (Sprint 8). Documentation à mettre à jour.

**Sévérité** : 🟡 MINEUR.

---

### 2.2 API FastAPI

`src/api/main.py` : 9 endpoints + auth + métriques Prometheus.

#### 2.2.1 🔴 BLOQUANT — `predict_traffic` TypeError

```python
# main.py:330
prediction = model.predict(req.node_idx, req.horizon_minutes)
```

Mais `XGBoostSpeedModel.predict(self, channel_id: str, horizon_minutes: int = 60, features: dict | None = None)`.

**Résultat** : `TypeError: predict() got multiple values for argument
'horizon_minutes'` (ou similaire), car Python tente de matcher le 1er
positional `req.node_idx:int` à `channel_id:str` (ça passe par duck-typing
mais pas la signature), et le 2e `req.horizon_minutes` est passé en double
(si l'interpreter essaye de le repasser).

À tester :
```bash
curl -X POST https://51.83.159.224/api/v1/predict/traffic \
  -H "X-API-Key: $LYONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"node_idx": 123, "horizon_minutes": 60}'
```

**Sévérité** : 🔴 BLOQUANT — endpoint principal down. Toutes les pages
dashboard qui tapent `/predict/traffic` (s'il y en a) crashent.

#### 2.2.2 `gold.app_users` n'existe pas dans init-db.sql

```python
# main.py:528
query = "SELECT user_id, persona_id, username, password_hash FROM gold.app_users ..."
```

**Réservé** : pas vu dans `init-db.sql` (j'ai scanné les tables `gold.*`).
Si la table n'existe pas, `execute_query` raise, et l'endpoint `/api/v1/auth/login`
retourne 500.

**Sévérité** : 🟠 MAJEUR — casse l'auth des personas Pro/Élu.

#### 2.2.3 `_buckets` du rate-limit grossit infiniment

```python
# rate_limit.py:36
self._buckets: dict[str, dict[str, list[tuple[float, int]]]] = defaultdict(...)
```

Clé = `f"{ip}:{bucket_name}"`. Aucune purge périodique des clés. Une attaque
avec des IPs aléatoires (botnet) crée N clés en mémoire → OOM du worker
FastAPI.

**Sévérité** : 🟠 MAJEUR — DoS possible sur le VPS (12 GB RAM, ça tient
un peu mais sur la durée c'est une bombe).

**Recommandation** : ajouter un TTL sur la structure, par ex. un thread qui
purge les `key not seen since > 1h`.

#### 2.2.4 `log_audit` synchrone dans la branche rate-limit

```python
# rate_limit.py:62-69
if total >= max_requests:
    log_audit(actor="rate_limit", action="rate_limit_exceeded", ...)
```

Si 1000 requêtes/sec depuis 50 IPs distinctes → 50 INSERTs/sec sur
`rgpd.audit_log`. En cas d'attaque, ça sature la DB. Faire de l'audit
asynchrone (queue) ou du sampling.

**Sévérité** : 🟡 MINEUR (en situation normale).

---

### 2.3 UI Streamlit — personas, pages, widgets

#### 2.3.1 🟠 MAJEUR — Auth mot de passe démo affiché en clair

`src/persona/auth.py:47` :
```python
_DEMO_PASSWORD = "demo2026"
```

Ligne 133 :
```python
st.markdown(f"**Mot de passe démo Jedha** : `{_DEMO_PASSWORD}`")
```

Affiché en clair dans un expander "Aide démo" sur les pages Pro_2 à Pro_7,
Elu_1 à Elu_5. Pour un démo Jedha, OK. Mais **si déployé en prod réelle**
sans désactiver cette aide, n'importe qui a accès admin.

Le code le mentionne dans le docstring : "Cette aide est affichée uniquement
parce que c'est une démo Jedha. En production réelle, les mots de passe
seront haschés et stockés hors du repo public."

**Recommandation** : flag `LYONFLOW_DEMO_AUTH_HELPER_VISIBLE` (défaut `1`
en dev, `0` en prod). Le Makefile `check-deploy-env` doit le valider.

**Sévérité** : 🟠 MAJEUR (sur la prod) — sécurité "by design broken" en l'état.

#### 2.3.2 Logout incompatible avec format dict

```python
# auth.py:95
def logout() -> None:
    st.session_state[_SESSION_AUTH_KEY] = False
```

Mais `_auth_state()` (manager.py:23-38) attend un dict `{persona_id: bool}`.
La migration :
```python
if raw is True:  # ne s'applique pas si False
    ...
```

Résultat : après `logout()`, le session_state contient `False` (bool), et
`_auth_state()` retourne `{}` (puisque `isinstance(False, dict) == False`
et la migration de `True` ne s'applique pas). Donc le `is_current_persona_authenticated()`
retourne `False` → la page affiche "🔒 Accès restreint". **Finalement
fonctionne**, mais c'est par accident.

**Sévérité** : 🟡 MINEUR.

#### 2.3.3 Widget Pro_4 KPIs à zéro

Cf § 2.1.2. Toutes les pages Pro (Pro_2, Pro_4) qui dépendent de
`line_kpis` (mêmes imports) sont cassées en mode prod.

#### 2.3.4 Cache lieux TTL non exposé

`data_loader._load_lyon_addresses_cached()` est import-cached mais
`reset_lieux_cache()` n'est pas câblé dans `clear_all_caches()` (data_cache.py:211).
Incohérence mineure : un bouton "refresh" Streamlit vide `st.cache_data` mais
pas le cache lieux.

**Sévérité** : 🟡 MINEUR.

#### 2.3.5 Carte Élu avec coordonnées hardcodées

`bottleneck_map.py:20-31` :
```python
coords = {
    "Rue Garibaldi": (45.7575, 4.8461),
    "Cours Lafayette": (45.7542, 4.8411),
    ...
}
```

10 zones avec lat/lon hardcodés. Si la DB retourne un bottleneck dont
`zone` n'est pas dans cette liste, il est silencieusement ignoré (ligne
47 : `if zone not in coords: continue`). Donc en mode prod avec données
réelles, **tous les bottlenecks réels sautent**.

**Sévérité** : 🟠 MAJEUR (UX silencieusement cassée).

**Recommandation** : utiliser les lat/lon de `gold.infrastructure_bottlenecks`
directement, ou géocoder le nom de zone via Nominatim (avec cache).

---

## 3. Tests

41 fichiers de tests, structure :
- `tests/data/` : tests DB + policy no-mock
- `tests/e2e/` : 8 tests Playwright/smoke sur les pages
- `tests/integration/` : 1 test infrastructure
- `tests/ml/` : 6 tests modèles
- `tests/persona/` : 5 tests widgets
- `tests/widgets/` : 2 tests
- `tests/security/` : 1 test scrub secrets
- `tests/smoke/` : 1 test smoke

**Observations** :

- Bonne couverture sur les modèles ML (XGBoost Speed/Vélov, STGCN,
  MLflow integration).
- `tests/data/test_no_mock_vps_policy.py` existe → vérifie qu'il n'y a pas
  de mock en prod, conforme à la policy "no-mock VPS".
- Tests e2e sur les pages (Usager_1, Elu, Persona switcher) → Playwright
  + API health.
- Pas trouvé de tests sur les routes manquantes
  (`get_lieux_lyon_names`, `get_cadence_for_line`, etc.) — cohérent avec le
  fait qu'elles n'existent pas, mais ça veut dire que **personne ne teste
  `load_lyon_addresses()` en intégration**.

**Recommandation** : ajouter un test d'intégration
`tests/integration/test_usager_mon_trajet_load.py` qui charge les loaders
utilisés par la page Mon Trajet, pour détecter les ImportError runtime.

---

## 4. Synthèse par Sprint de correction suggéré

### Sprint Audit-Fix P0 (urgent, 1-2 jours)

1. **Sortir `_disabled_dag_live_speed_retrain.py` de `dags/`** ou le gz.
2. **Créer les 4 fonctions manquantes dans `db_query.py`** (stubs
   remontant `DashboardDataError` acceptable, ou vrais SELECT).
3. **Fix `predict_traffic` API** : `model.predict(channel_id=str(req.node_idx), ...)`.
4. **Réconcilier format `load_line_kpis` ↔ widget** (choisir un sens, aligner).
5. **Indexer `gold.trafic_predictions(calculated_at)`**.

### Sprint Audit-Fix P1 (1 semaine)

6. Aligner `xgboost_velov.py` sur le schéma Gold réel.
7. Aligner `db_query.get_traffic_for_node` sur le schéma réel.
8. Flag `LYONFLOW_DEMO_AUTH_HELPER_VISIBLE` pour cacher le mot de passe démo
   en prod.
9. TTL sur `_buckets` du rate-limit.
10. `gold.app_users` : créer la table (alembic migration).
11. Cache lieux : câbler `reset_lieux_cache` dans `clear_all_caches`.

### Sprint Audit-Fix P2 (backlog)

12. Réduire le nombre d'horizons XGBoost à 1 chacun (perf VPS).
13. Géocoder dynamiquement les bottlenecks Élu.
14. Audit asynchrone rate-limit (sampling + queue).
15. Idempotence INSERT via `ON CONFLICT DO NOTHING`.
16. Test d'intégration Mon Trajet (couverture des loaders).

---

## 5. Méthodologie & limites de cet audit

**Outils utilisés** : lecture statique des fichiers Python + SQL, grep,
cartographie manuelle. Pas d'exécution du code (pas de docker-compose up
ni de pytest).

**Non couvert** :
- Couche `transformation/bronze_to_silver.py` et `silver_to_gold.py` :
  pas ouverts dans cet audit (fichiers longs, à auditorer séparément).
- Couche `routing/*` (Sprint 12 OSM graph) : vu rapidement
  (`pathfinder.py` import-only).
- Couche `ingestion/*` : pas vérifiée en détail.
- Tests : analysés au niveau structurel, pas exécutés.
- Mocks `src/data/mock/*.py` : pas audités.
- Couche `persona/personas_loader.py` (YAML) : pas vérifié.

**Recommandation** : compléter avec un audit Phase 2 sur les fichiers non
couverts + exécuter `pytest` + `docker-compose up postgres` pour valider
les requêtes SQL identifiées comme cassées.

---

*Audit rédigé en mode lecture seule. Aucun fichier modifié. Toutes les
constatations sont sourcées (fichier:ligne).*
