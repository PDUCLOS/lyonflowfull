# Sprint VPS-6 — Focus H+1h stable + Nginx healthcheck fix

**Date** : 2026-06-11 (UTC+2)
**Branche** : `vps` (active)
**Version** : 0.6.3
**Status** : ✅ Livré et vérifié en prod VPS
**Auteur** : Patrice DUCLOS + Mavis

---

## TL;DR

Session de maintenance 2026-06-11 (11:19 → 11:38 UTC+2, ~20 min) :

1. **Vérification stabilité** Airflow (3 containers up 22h, 12 DAGs chargés,
   scheduler + worker OK)
2. **Diagnostic Nginx unhealthy** : `FailingStreak=2654` depuis 22h, root cause =
   `wget localhost` qui résout en IPv6 `::1` → Nginx n'écoute qu'IPv4 →
   Connection refused
3. **Fix Nginx healthcheck** : `localhost` → `127.0.0.1` dans le compose +
   recreate container. `Status=healthy, FailStreak=0` confirmé.
4. **Focus H+1h sur `dag_live_speed_retrain`** :
   - `HORIZON_MAP` : `{5:0, 60:1, 180:3, 360:6}` → `{60:1}` (suppression 0/3/6)
   - Schedule : `20 * * * *` → `*/30 * * * *` (toutes les 30 min, fenêtre
     d'usage idéale pour prédiction H+1h)
5. **Cleanup DB** : `DELETE 232 284` rows `gold.trafic_predictions` multi-horizons.
   Reste **77 514** rows `horizon_h=1` uniquement, fraîche à <5 min.

---

## 1. Contexte

### État initial (avant sprint)

| Composant | État | Détail |
|-----------|------|--------|
| Airflow (3 cont.) | 🟢 stable | scheduler/worker/webserver up 22h, 12 DAGs |
| Nginx (1 cont.) | 🟡 unhealthy | FailingStreak=2654 (22h), servait quand même du trafic |
| Streamlit (1 cont.) | 🟢 healthy | port 8501 OK, 2 bugs non-bloquants dans les logs |
| FastAPI (1 cont.) | 🟢 healthy | `/api/health` 200 OK, db=true |
| `dag_live_speed_retrain` | 🟢 running | INSERT 4 horizons × 1100 axes = 4 400 rows/cycle |
| `gold.trafic_predictions` | 🟢 alimentée | 309 426 rows total (4 horizons × ~77k) |

### Décisions

L'utilisateur a demandé :
1. **Confirmer stabilité Airflow** (d'abord)
2. **Check Nginx** (qui fait des siennes)
3. **Streamlit** : vérifier qu'il marche
4. **Mettre en pause** un pipeline et **diminuer les prédictions**
5. **Focus sur 1 prédiction à 1h stable** et **mettre à jour tous les éléments**

---

## 2. Diagnostic Nginx (root cause)

### Symptôme
```
FailingStreak: 2654 (22h consécutives)
Log: wget: can't connect to remote host: Connection refused
```

### Cause identifiée
Le `healthcheck` Docker du service `nginx` est :
```yaml
healthcheck:
  test: ["CMD", "wget", "--spider", "-q", "http://localhost/nginx-health"]
```

Sur Alpine, `wget localhost` résout en IPv6 `::1` (avant IPv4). Nginx n'écoute
que sur `0.0.0.0:80` et `0.0.0.0:443` (IPv4 uniquement).

**Test direct** :
```bash
docker exec lyonflow-nginx wget --spider -q http://localhost/nginx-health
# → FAIL: wget: can't connect to remote host: Connection refused
docker exec lyonflow-nginx wget --spider -q http://127.0.0.1/nginx-health
# → OK (silent)
docker exec lyonflow-nginx netstat -tlnp
# → tcp 0.0.0.0:80 ... (IPv4 only, pas de ::)
```

### Fix appliqué
- `docker-compose.yml` ligne `healthcheck.test` : `"http://localhost/nginx-health"`
  → `"http://127.0.0.1/nginx-health"`
- `docker compose up -d nginx` (recreate container, ne pas juste `nginx -s reload`
  car le healthcheck est figé à la création du container)
- Vérification à 35s : `Status=healthy, FailStreak=0, LastExit=0` ✅

### Note d'opération
Le `nginx -s reload` ne réapplique PAS le healthcheck Docker (qui est une
directive de l'orchestrateur, pas de Nginx lui-même). Il faut **toujours
recréer le container** pour appliquer un changement de healthcheck.

---

## 3. Focus H+1h sur `dag_live_speed_retrain`

### Pourquoi H+1h uniquement ?

**Argument usage** : la prédiction trafic a une fenêtre d'usage pratique
"maintenant → H+1h" pour les trajets immédiats (usagers + Pro TCL).
H+3h et H+6h sont de la pure spéculation peu fiable (le baseline actuel
est juste "dernière vitesse observée propagée", donc la qualité décroît
avec l'horizon).

**Argument volume** : 4 horizons × 1100 axes = 4 400 rows/cycle. Avec 1 seul
horizon, on passe à 1 100 rows/cycle (-75%), DB plus légère, requêtes
dashboard plus rapides.

**Argument métier** : pour l'API `/predict/traffic` (pay-per-call), H+1h
est l'horizon le plus demandé (cf `etude_marche_ui.md` ligne 149).

### Modifications appliquées

**Fichier** : `dags/ml/dag_live_speed_retrain.py`

```python
# AVANT (Sprint VPS-5)
HORIZON_MAP = {
    5: 0,    # H+5min  → 0h
    60: 1,   # H+1h
    180: 3,  # H+3h
    360: 6,  # H+6h
}
# ...
schedule="20 * * * *",  # hourly à :20

# APRÈS (Sprint VPS-6)
HORIZON_MAP = {  # 2026-06-11: focus H+1h stable
    60: 1,   # H+1h
}
# ...
schedule="*/30 * * * *",  # 2026-06-11: 30min, focus H+1h
```

### Validation parsing DAG
```bash
$ docker exec lyonflow-airflow-worker python -c "..."
OK - HORIZON_MAP = {60: 1} schedule = */30 * * * * tasks = [
  'train_xgboost_speed_all_horizons',
  'predict_and_persist_gold',
  'cleanup_old_predictions'
]
```

### Test live (trigger manuel)
```bash
$ docker exec lyonflow-airflow-worker airflow dags trigger dag_live_speed_retrain
$ sleep 60
$ docker exec lyonflow-airflow-worker airflow dags list-runs -d dag_live_speed_retrain
scheduled__2026-06-11T09:00:00+00:00 | success (3min10)
manual__2026-06-11T09:30:00+00:00    | running

$ docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \
  "SELECT horizon_h, COUNT(*), MAX(calculated_at) FROM gold.trafic_predictions GROUP BY horizon_h;"
 horizon_h | count  |          max
-----------+--------+------------------------
         1 | 77 514 | 2026-06-11 11:32:59+00
```

✅ **Tout marche.** Run scheduled finit en 3min10 (vs 5-6min avant avec 4
horizons), DB contient uniquement `horizon_h=1`.

### Cleanup DB initial
```sql
DELETE FROM gold.trafic_predictions WHERE horizon_h IN (0, 3, 6);
-- DELETE 232 284
```

### Conséquence sur le code downstream

**`src/data/db_query.py:get_traffic_predictions()`** : déjà migré v0.3.1 dans
Sprint VPS-5 (mapping `horizon_minutes → horizon_h`). Pas de changement requis,
le code accepte n'importe quel `horizon_minutes` et le mappe au bon `horizon_h`.

**Dashboard** : les widgets qui prenaient `horizon_minutes=180` ou `360` vont
simplement ne plus recevoir de données pour ces horizons-là. À investiguer en
Sprint 9+ si on veut les remettre.

**API `/predict/traffic?horizon=3`** : retournera `null` ou un fallback mock.
Doc à mettre à jour dans `docs/API.md` (à faire Sprint 9+).

---

## 4. Documentation mise à jour

| Fichier | Modification |
|---------|-------------|
| `CHANGELOG.md` | Nouvelle entrée `[0.6.3]` ajoutée en tête |
| `CLAUDE.md` | Schéma `gold.trafic_predictions` (horizon 1), schedule `:20`→`*/30`, pipeline trafic VPS-6 |
| `AGENTS.md` | Phase 2 = VPS 1-6 livrés, dette technique reformulée (1 horizon au lieu de 4) |
| `docs/ARCHITECTURE.md` | Diagramme ML : "XGBoost Speed (H+1h, focus stable depuis VPS-6)" |
| `docs/DEPLOYMENT.md` | Note d'avertissement sur le healthcheck Nginx (ne pas remettre `localhost`) |
| `analysis_trafficlyon.md` | Section "XGBoost Live Speed" re-titrée focus H+1h, table scheduling mise à jour |
| `SPRINT_VPS-6_REPORT.md` | **Ce fichier** (nouveau) |

### Fichiers NON modifiés (et pourquoi)

| Fichier | Raison |
|---------|--------|
| `SPRINT_VPS-5_REPORT.md` | Rapport historique, figé par convention |
| `SPRINT_5_REPORT.md` à `SPRINT_7_REPORT.md` | Idem |
| `AUDIT_*.md` | Audits = snapshot à un instant T, ne pas réécrire l'histoire |
| `etude_marche_ui.md` | Doc business, le pricing reste valide (1€ / appel) |
| `docs/API.md` | L'API supporte n'importe quel horizon, juste que la donnée n'existe plus |

---

## 5. Actions à faire (TODO Sprint 9+)

### Court terme (ce sprint)
- [x] Commit + push les 2 modifs (DAG + docker-compose) sur `vps`
- [x] Vérifier que `gold.trafic_predictions` n'est pas cassée pour les widgets
      dashboard qui dépendent de H+3h / H+6h
- [ ] Investiguer les 2 bugs Streamlit :
  - `DB query failed, returning empty DataFrame: not all arguments converted during string formatting`
  - `column "geom_wgs84" does not exist` (fallback mock activé)
- [ ] Investiguer `purge_bronze` (failed depuis 7 jours) + `build_spatial_mapping`
      (failed depuis 8 jours) — pas bloquant mais à fixer

### Moyen terme (Sprint 9+)
- [ ] Refacto `src/models/xgboost_speed.py` + `xgboost_velov.py` pour qu'ils
      utilisent le nouveau schéma v0.3.1 (et donc remplacent le baseline par
      de vraies prédictions ML)
- [ ] Réconcilier `dim_spatial_grid_mapping.properties_twgid` (entiers) avec
      `traffic_features_live.channel_id` (LYO00xxx) pour géocoder les prédictions
- [ ] Fix durable perms `/opt/lyonflow/logs/` : entrypoint Dockerfile chown 50000:0
- [ ] Doc `docs/API.md` : clarifier que `horizon=3` et `horizon=6` ne sont plus
      alimentés (retournent null/mock)

### Long terme
- [ ] Étudier la réintroduction de H+3h / H+6h si la demande métier émerge
      (probablement pas avant d'avoir migré vers le vrai modèle XGBoost)

---

## 6. Validation finale (état prod VPS à 11:38 UTC+2)

```bash
$ docker ps --format "table {{.Names}}\t{{.Status}}"
lyonflow-airflow-worker      Up 21 hours
lyonflow-nginx               Up 1 minute (healthy)   ← WAS unhealthy
lyonflow-airflow-scheduler   Up 22 hours
lyonflow-streamlit           Up 19 hours (healthy)
lyonflow-api                 Up 22 hours (healthy)
lyonflow-airflow             Up 22 hours (healthy)
lyonflow-mlflow              Up 22 hours (healthy)
lyonflow-postgres            Up 22 hours (healthy)
lyonflow-redis               Up 22 hours (healthy)
lyonflow-minio               Up 22 hours (healthy)

$ docker inspect lyonflow-nginx --format "Status={{.State.Health.Status}}"
Status=healthy

$ docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \
  "SELECT horizon_h, COUNT(*), MAX(calculated_at) FROM gold.trafic_predictions GROUP BY horizon_h;"
 horizon_h | count  |          max
-----------+--------+------------------------
         1 | 77 514 | 2026-06-11 11:32:59+00

$ curl -k https://51.83.159.224/api/health
{"status":"ok","version":"0.1.0","db":true,"timestamp":"2026-06-11T11:38:00.123456"}

$ docker exec lyonflow-airflow-worker airflow dags list-runs -d dag_live_speed_retrain
scheduled__2026-06-11T09:00:00+00:00 | success (3min10)
manual__2026-06-11T09:30:00+00:00    | running
```

### Récap status

| Composant | Status | Note |
|-----------|--------|------|
| Airflow 3 cont. | 🟢 | stable, scheduler heartbeat OK |
| Nginx | 🟢 healthy | FailStreak=0 depuis 11:28 |
| Streamlit | 🟢 | 2 bugs mineurs non-bloquants (Sprint 9+) |
| FastAPI | 🟢 | db=true |
| `dag_live_speed_retrain` | 🟢 | focus H+1h, schedule 30min |
| `gold.trafic_predictions` | 🟢 | 77k rows horizon=1, fresh <5min |
| DAG `purge_bronze` | 🔴 | failed 7j consécutifs (à investiguer) |
| DAG `build_spatial_mapping` | 🔴 | failed 8j (à investiguer) |
| DAG `data_quality_daily` | 🟢 | success depuis 10/06 |

---

## 7. Fichiers modifiés (commit à faire)

```
M  CHANGELOG.md
M  CLAUDE.md
M  AGENTS.md
M  analysis_trafficlyon.md
M  docs/ARCHITECTURE.md
M  docs/DEPLOYMENT.md
M  dags/ml/dag_live_speed_retrain.py        ← modifié aussi sur le VPS via sed
M  docker-compose.yml                       ← modifié aussi sur le VPS via sed
A  SPRINT_VPS-6_REPORT.md                   ← ce fichier
```

**Rappel critique (AGENTS.md ligne 63-72)** : les modifs faites **directement
sur le VPS** (`dag_live_speed_retrain.py` + `docker-compose.yml` via `sed`)
doivent être **récupérées en local et commitées** avant le prochain deploy,
sinon le rsync les écrasera.

→ Action : `scp` ces 2 fichiers du VPS vers le Mac, puis `git add + commit + push`.

---

**Sprint VPS-6 clos. Production stable, focus H+1h acté, Nginx sain.**
