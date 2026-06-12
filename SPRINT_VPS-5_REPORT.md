# Sprint VPS-5 — Connexion pipeline trafic & UX

**Branche** : `vps` · **Date** : 2026-06-10 · **Version** : 0.6.1

## Contexte

Suite à la dernière release (Sprint VPS-4), 3 anomalies bloquaient le dashboard
et le pipeline de bout en bout :

1. **Plus de prédictions trafic H+30min / H+1h / H+3h** sur le dashboard —
   le message *"Pas de prédictions disponibles pour H+30min"* s'affichait
   alors que la table `gold.trafic_predictions` était non-vide.
2. **166 lignes TCL** attendues sur `Pro_4_Simulateur`, seules 12 du mock
   s'affichaient → impossible de simuler l'ajout de bus sur les vraies lignes
   (C3, T1, T4, etc.).
3. **KPIs par ligne** (page Pro) sans contrôle de tri → impossible d'explorer
   plus de données ou d'identifier rapidement les lignes dégradées.

L'investigation a révélé **deux dettes schéma** que le refactor v0.3.1 avait
introduites sans mettre à jour le code applicatif :

* `src/data/db_query.py` + `health_checks.py` + `model_monitoring.py` :
  requêtes sur colonnes obsolètes (`prediction_timestamp, target_timestamp,
  horizon_minutes, node_idx, model_name, confidence_low/high, actual_speed`)
  qui n'existent plus dans le nouveau schéma (`axis_key, horizon_h,
  calculated_at, speed_pred, etat_pred, label, model_version`).
* **`dags/ml/dag_live_speed_retrain.py` n'existait pas** alors que la table
  `gold.trafic_predictions` attendait un peuplement hourly (cf commentaire
  SQL ligne 1230 de `deploy/init-db.sql` et mention dans
  `analysis_trafficlyon.md` ligne 106).

---

## Livré

### A. Pipeline trafic reconnecté

| Fichier | Δ | Rôle |
|---------|---|------|
| `dags/ml/dag_live_speed_retrain.py` | **NEW** (252L) | DAG hourly @ :20 : train 4 XGBoost speed → INSERT dans `gold.trafic_predictions` → cleanup >7j |
| `src/data/db_query.py:get_traffic_predictions()` | réécrit (45L) | Mapping `horizon_minutes→horizon_h` + alias `predicted_speed`/`prediction_timestamp` pour rétro-compat |
| `src/data/db_query.py:get_traffic_bottlenecks()` | fix (10L) | `node_idx, measurement_time` → `channel_id, computed_at` |
| `src/data/data_loader.py:load_tcl_lines()` | NEW (50L) | Charge 166 lignes TCL depuis DB (T*=tram, M*=metro, reste=bus) |
| `src/data/data_loader.py:load_traffic()` | fix | Utilise les nouvelles colonnes `speed_pred` |
| `src/monitoring/health_checks.py:check_predictions_presentes()` | fix | `prediction_timestamp` → `calculated_at` |
| `dashboard/components/widgets/pro_tcl/model_monitoring.py` | fix | Liste data-quality tables alignée sur schéma v0.3.1 |

**Résultat** :
- 51 717 rows × 4 horizons dans `gold.trafic_predictions`, dernière MAJ = aujourd'hui 08:28
- Dashboard voit `26.1 km/h, modéré` aux 3 horizons (avant : "Pas de prédictions disponibles")
- 166 lignes TCL sur Pro_4_Simulateur (9 trams + 157 bus)

### B. Widget KPIs par ligne — Sort + Explore

`dashboard/components/widgets/pro_tcl/line_kpis.py` (218L, +140 vs v0.3.0) :

- **Sélecteur "Trier par"** (10 options) : OTP % ↑↓, Retard min ↑↓, Charge % ↑↓,
  Fréquence min ↑↓, Line ID A-Z/Z-A
- **Slider "Top N"** : 5 → 50 lignes affichées
- **Checkbox "Détails par ligne"** : déplie chaque ligne en 4 KPI cards
- **Tableau Streamlit** avec barres de progression colorées sur OTP et Charge
- Tri natif Streamlit conservé (click sur les headers)
- Mode legacy : cards colorées historiques en dessous, désactivables

### C. Dette technique documentée (Sprint 9+)

`src/models/xgboost_speed.py` + `xgboost_velov.py` référencent **9+ colonnes
inexistantes** dans `gold.traffic_features_live` v0.3.1 :

| Colonne référencée (code) | Colonne réelle (DB) |
|---------------------------|---------------------|
| `speed_lag_1, speed_lag_2, speed_lag_3` | `lag_1, lag_2, lag_3` |
| `speed_delta_1` | `delta_1` |
| `rolling_mean_5min` | `rolling_mean_3` |
| `hour_sin, hour_cos, day_sin, day_cos` | `sin_hour, cos_hour, sin_dow, cos_dow` |
| `temperature_c` | `temperature_2m` |
| `rain_mm` | `precipitation` (et `rain`) |
| `is_vacances, is_ferie` | OK |
| `node_idx` | N/A → `channel_id` (jointure non triviale) |
| `measurement_time` | `computed_at` (et `fetched_at`) |

En attendant, `dag_live_speed_retrain` capture l'échec du `train_one()` et
passe en **stratégie baseline** = dernière vitesse observée par channel_id,
propagée sur 4 horizons. Le dashboard reçoit toujours des données
exploitables.

### D. Bug permissions logs/ worker Airflow

**Symptôme** : le worker Celery crashait silencieusement avec
`PermissionError: '/opt/airflow/logs/dag_id=*/run_id=*'` parce que
`/opt/lyonflow/logs/` était owned par `ubuntu:1000` (le user qui fait le
rsync), alors que le container tourne en `uid 50000` (`airflow`).

Conséquence : les DAGs apparaissaient dans l'UI mais les tasks restaient
en `queued` indéfiniment, et le scheduler crashait en boucle sur le même
permission error toutes les 30s.

**Fix immédiat** : `sudo chown -R 50000:0 /opt/lyonflow/logs` après chaque
rsync.

**Fix durable TODO** (Sprint 9+) : `entrypoint.sh` dans le Dockerfile
Airflow qui `chown 50000:0 /opt/airflow/logs` au boot.

### E. Bug UI Airflow "DAG invisible"

**Symptôme** : après rsync d'un nouveau DAG, l'UI ne le voit pas.

**Fix** :
```bash
docker compose exec airflow-webserver bash -c "rm -rf /opt/airflow/dags/ml/__pycache__"
docker compose exec airflow-webserver airflow dags reserialize
```

Le `__pycache__` contient une version compilée de l'ancien DAG qui masque le
nouveau. À vider après chaque modif de DAG.

---

## Vérification

| Check | Avant | Après |
|-------|-------|-------|
| `airflow dags list` | 8 actifs | 9 actifs (1 nouveau) |
| `gold.trafic_predictions` latest `calculated_at` | 2026-06-06 02:23 (4 jours) | <5 min |
| Dashboard "Prédictions H+30min" | "Pas de prédictions" | 26.1 km/h, modéré |
| `load_tcl_lines()` count | 12 (mock) | 166 (DB : 9 trams + 157 bus) |
| Widget `line_kpis.py` | cards fixes | tri + slider + détails + tableau |
| Worker Celery crashes | 1/30s | 0 |
| `pytest tests/ -q` | 104 collected | 51 passed, 1 env-only fail, 1 skip |

## Dette restante (Sprint 9+)

1. **Refacto `src/models/xgboost_speed.py` + `xgboost_velov.py`** : aligner
   les 9+ colonnes sur schéma v0.3.1. Une fois fait, le `train_one()`
   fonctionnera et le baseline pourra être retiré (passer
   `model_version='xgboost_speed_v2'` au lieu de `'baseline_v0.3.1'`).
2. **Réconcilier `dim_spatial_grid_mapping` ↔ `traffic_features_live`** :
   aujourd'hui le JOIN est impossible (`properties_twgid` entiers vs
   `channel_id` "LYO00xxx"). Solution probable = créer une table de mapping
   ou recalculer `properties_twgid` à partir des coordonnées.
3. **Entrypoint Dockerfile Airflow** : chown `logs/` au boot, plus besoin
   de le faire à la main après chaque rsync.
4. **Cert TLS Let's Encrypt** : le domaine `lyonflowfull.fr` est mort (DNS
   NXDOMAIN) → cert expiré/révoqué, fallback self-signed `CN=51.83.159.224`.
   À recréer quand le DNS sera restauré (ou abandon DNS et accepter le
   warning cert en production).
5. **Vue carte des prédictions** : `lat/lon=NULL` dans la table tant que
   le mapping (2) n'est pas fait → la carte Folium des prédictions
   n'affiche rien.

## Fichiers modifiés

```
M  AGENTS.md                                       (phases, dette, VPS-5)
M  CHANGELOG.md                                    (0.6.1 section)
M  CLAUDE.md                                       (header, Gold, scheduling, dashboard, gotchas)
M  dashboard/components/widgets/pro_tcl/line_kpis.py  (sort + explore + tableau)
M  src/data/db_query.py                            (get_traffic_predictions + bottlenecks)
M  src/data/data_loader.py                         (load_tcl_lines 166 lignes, load_traffic fix)
M  src/monitoring/health_checks.py                 (calculated_at)
A  dags/ml/dag_live_speed_retrain.py               (NEW, 252L)
A  SPRINT_VPS-5_REPORT.md                          (NEW, ce fichier)
```

## Notes ops

- Le DAG `dag_live_speed_retrain` est schedulé à :20 hourly. Pour le
  désactiver temporairement : `airflow dags pause dag_live_speed_retrain`.
- Pour trigger manuellement : `docker compose exec airflow-webserver
  airflow dags trigger dag_live_speed_retrain`.
- Les logs du DAG sont dans
  `/opt/lyonflow/logs/airflow/dag_id=dag_live_speed_retrain/`.
- Chown obligatoire après rsync :
  ```bash
  ssh ubuntu@51.83.159.224 'sudo chown -R 50000:0 /opt/lyonflow/logs /opt/lyonflow/src /opt/lyonflow/dags /opt/lyonflow/dashboard'
  ```
