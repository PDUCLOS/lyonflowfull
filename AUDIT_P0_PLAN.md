# Plan de correction P0 — LyonFlowFull

**Date** : 2026-06-14
**Origine** : `AUDIT_INTEGRATION_LIVE.md`
**Mode** : modifications progressives, ordre strict, vérif à chaque étape.

## Ordre d'attaque (par criticité, sans interférence mutuelle)

### P0.1 — Conflit scheduler Airflow
**Constat** : `dags/ml/_disabled_dag_live_speed_retrain.py` et
`dags/ml/dag_live_speed_retrain.py` définissent le même `dag_id="dag_live_speed_retrain"`.
Le préfixe `_disabled_` ne change rien pour Airflow → conflit au parse.

**Action** : déplacer `_disabled_dag_live_speed_retrain.py` hors de `dags/`
vers `dags/_archive/` puis ajouter un `__init__.py` qui en fait un package
Python vide (pour qu'Airflow ne le scanne plus).

**Pourquoi d'abord** : c'est le seul qui peut faire crasher le scheduler
ENTIÈREMENT (et donc empêcher tous les autres DAGs de tourner). Il faut le
fixer avant que le reste n'ait le temps de mal tourner.

**Risque de régression** : aucun — on déplace un fichier uniquement.

**Vérif après** : `python -c "import ast; ast.parse(open('dags/ml/dag_live_speed_retrain.py').read())"`
et confirmer qu'un seul `DAG(dag_id="dag_live_speed_retrain"` existe.

### P0.2 — 4 fonctions manquantes dans `db_query.py`
**Fonctions** : `get_lieux_lyon_names`, `get_lieux_lyon_with_coords`,
`get_cadence_for_line`, `get_latest_drift_report`.

**Action** : créer 4 stubs propres dans `db_query.py` qui retournent :
- `get_lieux_lyon_names()` → `list[str]` vide (DB indispo ou table absente)
- `get_lieux_lyon_with_coords()` → `list[dict]` vide
- `get_cadence_for_line(...)` → `list[dict]` vide
- `get_latest_drift_report()` → `None`

Les callers existants (data_loader + xgboost_speed) sont **déjà** protégés
par des try/except (data_loader) ou sont non-bloquants (xgboost_speed dans
un try: log warning). Donc des stubs qui retournent vide sont sans danger et
donnent un comportement fail-soft acceptable pour le P0 (les pages
afficheront "Aucun lieu disponible" plutôt que de crasher).

**Pourquoi en 2e** : pas de dépendance sur P0.1, et c'est ce qui crash la page
Mon Trajet dès qu'on clique sur une adresse.

**Risque de régression** : minimal — on ajoute des fonctions, on ne modifie
aucun comportement existant.

**Vérif après** : import-test des 4 fonctions.

### P0.3 — `predict_traffic` API : TypeError runtime
**Constat** : `src/api/main.py:330` appelle
`model.predict(req.node_idx, req.horizon_minutes)` mais la signature est
`predict(self, channel_id: str, horizon_minutes: int = 60, features: dict = None)`.

**Action** : passer `str(req.node_idx)` (ou accepter que l'API prenne un
channel_id string directement dans le request body).

**Choix** : je modifie juste l'appel (cast en str) pour rester backward-compat
avec le Pydantic model qui demande `node_idx: int`. Le modèle XGBoost
acceptera un int casté en str, qui matchera `channel_id` (format "LYO00xxx"
avec zfill). Le client n'a pas besoin de changer.

**Pourquoi en 3e** : touche à l'API. Indépendant des autres fixes.

**Risque de régression** : faible — le Pydantic model reste inchangé, juste
le cast au call site.

**Vérif après** : lire la signature complète et confirmer qu'aucun autre
caller ne dépend du comportement "int → crash".

### P0.4 — Format `line_kpis` incompatible
**Constat** : `db_query.get_line_kpis()` retourne `{"lines": [...], "timestamp": "..."}`,
mais le widget `widgets/pro_tcl/line_kpis.py` (et la page `Pro_4_Simulateur.py:42`)
boucle en s'attendant à un `dict[line_id, kpis]`.

**Action** : modifier `db_query.get_line_kpis` pour retourner le format
attendu par le widget. C'est le plus petit changement qui aligne le contrat
sur l'usage réel.

**Nouveau format** : `dict[str, dict]` où chaque clé est un `line_id` et la
valeur est `{otp_pct, avg_delay_min, frequency_min, load_pct, trend, trend_delta, date}`.

**Pourquoi en 4e** : touche à la couche data_loader, mais reste localisé
(un seul fichier, fonction unique).

**Risque de régression** : modéré — il faut aussi vérifier les autres
callers de `get_line_kpis` (cherche dans le repo) pour confirmer qu'aucun
n'utilise le format `{"lines": []}`.

**Vérif après** : grep tous les usages de `get_line_kpis` et `cached_line_kpis`.

### P0.5 — Index manquants sur `gold.trafic_predictions`
**Constat** : cleanup hourly `DELETE WHERE calculated_at < NOW() - INTERVAL '7 days'`
et `SELECT WHERE calculated_at >= NOW() - INTERVAL '2 hours'` font du seq scan.

**Action** : créer 2 index via alembic migration (propre) OU via un script
SQL idempotent. Je vais créer une migration alembic pour rester aligné avec
le workflow projet (déjà 1 migration dans `alembic/versions/0001_initial.py`).

**Pourquoi en 5e** : perf, pas de crash. Peut attendre les autres fixes.

**Risque de régression** : aucun — `CREATE INDEX IF NOT EXISTS` est innoffensif.

**Vérif après** : confirmer le contenu de la migration + syntaxe SQL.

## Hors-scope (à traiter plus tard, ne pas faire maintenant)

- P1 : schéma Vélov, mot de passe démo, gold.app_users, rate-limit TTL
- P2 : horizons XGBoost, géocoder bottlenecks, audit async, idempotence INSERT

## Règles pendant les fixes

1. **Un fix à la fois** : pas de lot de plusieurs P0 dans le même edit.
2. **Vérif immédiate après chaque fix** : grep, import-test, lecture du code modifié.
3. **Pas de modif en dehors du scope** du fix.
4. **Commit séparé par fix** (ou en tout cas pas de mix).

## État d'avancement

- [ ] P0.1 Conflit scheduler
- [ ] P0.2 4 fonctions manquantes
- [ ] P0.3 predict_traffic API
- [ ] P0.4 format line_kpis
- [ ] P0.5 index trafic_predictions
- [ ] Vérification finale
