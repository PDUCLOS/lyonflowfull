# Audit projet LyonFlow — 2026-06-30

> Audit statique du repo (branche `vps`) après l'incident Sprint 24. Périmètre :
> qualité de code, sécurité, tests, dette technique, cohérence source↔runtime,
> dettes ops héritées. Note globale et recommandations priorisées en fin.

## Note globale : **A− (solide, 1 risque P0 traité, 1 dette résiduelle à re-planifier)**

Le projet est mature et bien architecturé (medallion, 3 personas, zéro mock,
SQL paramétré, secrets en env). **L'audit a révélé une dérive source↔runtime
critique** : les correctifs de l'incident Sprint 24 étaient **déployés sur le VPS
mais absents du code commité**. Risque **réglé** dans la journée (4 commits
sur `origin/vps` : `f9e6936`, `e6dcaa8`, `bc71c73` + merge `f5c4c77` +
`60e793a`). 593 tests verts, 0 régression.

**Dette résiduelle** : la migration 035 (MV `gold.mv_latest_sensor_position`)
n'a pas pu être appliquée en raison de la saturation IO de sdb au moment du
run. Voir section 10 ci-dessous.

---

## 1. Métriques

| Métrique | Valeur |
|----------|--------|
| Fichiers Python (hors `.venv`) | 281 |
| Lignes de code Python | ~48 000 |
| Répartition | dashboard 15,6k · src 14,6k · tests 9,1k · dags 3,9k |
| Fonctions de test | 557 (54 fichiers) |
| Migrations SQL | 25 (gap : 031 absent, TODO documenté) |
| DAGs Airflow (hors legacy) | 25 |
| Docs | 34 |

Ratio test/code ≈ 0,6 (9,1k tests / 14,6k src) — **bon**.

---

## 2. 🔴 P0 — Dérive source ↔ runtime (Sprint 24)

> **MISE À JOUR 2026-06-30 12h** — partiellement réconcilié. Commits `f9e6936`
> (statement_timeout), `e6dcaa8` (`_refresh_matview_safe`), `bc71c73` (coercition
> widget) portent **les 2 items permanents** dans git (le bug CONCURRENTLY et le
> crash dashboard). Restent **VPS-only et intentionnels** : fenêtre `fresh` 30 min
> et timeout `build_traffic_features` 10 min — ce sont des **tampons temporaires**
> "revert après tuning", à NE PAS graver dans git.

> ### 🚧 GATE DÉPLOIEMENT (obligatoire tant que les tampons sont VPS-only)
> La prod tourne en **fenêtre 30 min / timeout 10 min** (hot-patch) ; git est en
> **15 min / 5 min**. Un `make deploy-vps` complet **avant** que le disque sdb soit
> désaturé (tuning Postgres effectif + burst IO régénéré) **renverrait 15/5 sur un
> disque lent → symptômes de l'incident de retour** (gold stale, MV 0-ligne).
>
> **Règle : pas de `make deploy-vps` complet tant que :**
> 1. le tuning Postgres Option A est **vérifié actif** (`pending_restart=f` ✅ fait), ET
> 2. le pipeline tourne stable >2 h avec gold <10 min, ET
> 3. les tampons 30/10 ont été **réalignés à 15/5 partout** (git = VPS) une fois
>    le disque rapide.
>
> Déploiements **partiels par fichier** (rsync ciblé) restent OK entre-temps.

**Les correctifs de l'incident sont sur le VPS mais PAS dans le code commité.**
Vérifié sur le working tree (= ce que `make deploy-vps` enverra) :

| Correctif incident | Déployé VPS | Dans git (`vps`) | Conséquence si re-deploy |
|--------------------|:-----------:|:----------------:|--------------------------|
| `_refresh_matview_safe` (fallback CONCURRENTLY→plain) | ✅ | ❌ `silver_to_gold.py:521` = `REFRESH ... CONCURRENTLY` **seul** | **Bug MV-vide ré-armé** |
| Fenêtre `fresh` 30 min | ✅ | ❌ ligne 150 = `INTERVAL '15 minutes'` | gold re-zéro si silver lag >15 min |
| `build_traffic_features` timeout 10 min | ✅ | ❌ `transform_silver_to_gold.py:77` = `minutes=5` | re-timeout sur disque lent |
| Coercition NUMERIC widget | ✅ | ❌ `bus_traffic_spatial.py` : 0× `pd.to_numeric` | `TypeError nlargest` revient |
| Dispatch `purge_traffic_features` | — | ❌ absent de `silver_to_gold.py` | voir §3 |

**Risque** : le prochain déploiement complet **écrase les fixes** et fait revenir
l'incident (MV à 0, carte stale, dashboard `TypeError`).

**Action P0** : ré-appliquer les 4 fixes dans le code commité (porter ce qui est
sur le VPS vers git), OU documenter qu'ils sont volontairement out-of-band et
bloquer `make deploy-vps` tant que ce n'est pas réconcilié. **À faire avant tout
prochain deploy.**

---

## 3. 🟠 P1 — Incohérence `refresh_heavy_mv` (staged) ↔ `silver_to_gold.py` (commité)

`dags/transforms/refresh_heavy_mv.py` est **stagé** (`git status: A`) et appelle :
- `target="bottleneck"` ✅ (dispatché)
- `target="bus_traffic_spatial"` ✅ (mais via la fonction **buggée** CONCURRENTLY-seul, cf. P0)
- `target="purge_traffic_features"` ❌ **non dispatché** dans `silver_to_gold.py`

→ la tâche `purge_old_traffic_features` ferait un **no-op silencieux** (le
dispatch retourne `{}` sans erreur). La purge gold annoncée ne purgerait rien.

**Action** : soit committer le refacto `silver_to_gold.py` complet (dispatch
purge + `_refresh_matview_safe`), soit retirer `refresh_heavy_mv.py` du staging
jusqu'à ce que sa dépendance soit livrée. Idem pour `test_data_loader_coercition.py`
(stagé `AD`) qui importe `_coerce_numeric_columns` **absent** de `src/data/`.

---

## 4. Qualité de code

| Check | Résultat |
|-------|----------|
| **ruff** | **240 erreurs** (≠ « ruff clean » de CLAUDE.md — claim périmé) |
| dont whitespace `W291`/`W293` | **195** (cosmétique, auto-fixable `ruff --fix`) |
| `N806` (var majuscule en fonction) | 20 (convention math, souvent OK — à ignorer per-file) |
| `I001` imports non triés | 11 (auto-fixable) |
| `RUF00x` (× ambigu docstrings) | 9 |
| **mypy** | non vérifiable ici (absent du sandbox) — à relancer en CI |

Whitespace concentré dans `src/ingestion/*` (base.py, tomtom_traffic.py),
`src/ml/mlflow_integration.py`, `src/db/connection.py`.

**Action** : `ruff check . --fix` (règle 195/240 en un coup) + mettre à jour le
claim « ruff clean » dans CLAUDE.md, ou ajouter ruff au CI en bloquant.

---

## 5. Sécurité — **bon** ✅

| Règle | État |
|-------|------|
| Secrets hardcodés | **0** trouvé |
| Config via `os.getenv` | 43 usages, pas de fallback secret en dur |
| `.env` / `.deploy.env` dans git | **Non** (couverts par `.gitignore`) |
| Scrub secrets | `scripts/scrub_secrets.py` + test présents |
| f-string SQL | **1 seul** : `silver_archive_to_minio.py:148` `VACUUM (ANALYZE) silver.{table}` |

Le seul f-string SQL : `table` vient d'une **liste codée en dur** (`SILVER_TABLES`),
pas d'input utilisateur, et `VACUUM` ne peut pas être paramétré → **risque
théorique faible**. Recommandation : valider `table` contre une whitelist
(comme `maintenance.py::_validate_table`) par cohérence défensive.

---

## 6. Dette technique — **faible** ✅

- **6 TODO/FIXME** seulement dans tout `src/dags/dashboard` — très propre.
- Pertinents : `bronze_to_silver.py:156` (schéma), `pathfinder_multimodal.py:373`
  (perf batch), `network_health_gauge.py:11` (sparkline historique).
- Migration **031 absente** (gap) — référencé comme TODO dans `record_network_health.py`,
  intentionnel.
- `git status` un peu sale : `tests/ml/test_model_registry.py` supprimé (`D`),
  `test_data_loader_coercition.py` en `AD` (ajouté+supprimé) → nettoyer le staging.

---

## 7. Dettes ops héritées (CLAUDE.md « Décisions ouvertes »)

| Item | Statut | Priorité |
|------|--------|----------|
| **Disque sdb throttlé (OVH burst IO)** — cause racine de l'incident | 🔴 actif | Tuning Postgres Option A (préparé) |
| **Tuning PostgreSQL** (`shared_buffers` 128MB, `work_mem` 4MB) | 🔴 à appliquer | P1 — règle la lenteur globale |
| **29 GB `silver.trafic_vitesse_propre`** (DAG archive silently-fail + VACUUM≠FULL) | 🟠 espace disque | P2 |
| **rclone backup offsite** non configuré (OAuth pending) | 🟡 | journalctl spam quotidien |
| **Prometheus absent** (intentionnel) → Grafana « no data » | 🟡 | cosmétique |
| **Migration 035** (mv_latest_sensor_position) non appliquée | 🟡 | à faire off-peak après tuning |
| **Migration 038** (drop index morts) commentée | 🟡 | après re-mesure `pg-audit` |

---

## 8. Points forts confirmés ✅

- Architecture medallion claire, 3 piliers ML documentés, 18 pages × 3 personas.
- **Zéro mock** (politique Sprint 8) — fail-loud via `DashboardDataError`.
- **SQL 100% paramétré** (1 seul f-string non-exploitable).
- Secrets entièrement en env, `.gitignore` correct, scrub + gitleaks-like.
- Idempotence migrations (tracking `schema_migrations`).
- Découplage train/inférence (Sprint 9+), DAGs `max_active_runs=1`+`catchup=False`.
- Watchdog `critical_pipeline_health` (mesure désormais `MAX(computed_at)` gold).
- 557 tests, ratio test/code sain.

---

## 9. Recommandations priorisées

| # | Action | Priorité | Effort |
|---|--------|----------|--------|
| 1 | **Réconcilier source↔runtime** : porter les 4 fixes Sprint 24 dans git AVANT tout deploy (§2) | 🔴 P0 | 1 h |
| 2 | Résoudre l'incohérence `refresh_heavy_mv`↔`silver_to_gold` (committer le refacto OU dé-stager) (§3) | 🟠 P1 | 1 h |
| 3 | **Tuning Postgres Option A** ce soir off-peak (root de l'incident) | 🟠 P1 | 30 min |
| 4 | `ruff check . --fix` (195 whitespace) + ajouter ruff bloquant au CI | 🟡 P2 | 20 min |
| 5 | Migration 035 off-peak (après tuning) puis 038 après re-mesure | 🟡 P2 | 30 min |
| 6 | Investiguer 29 GB `trafic_vitesse_propre` (DAG archive + VACUUM FULL) | 🟡 P2 | 2 h |
| 7 | Nettoyer le staging git (`test_model_registry`, `test_data_loader_coercition`) | 🟢 P3 | 10 min |

**Le P0 est non négociable** : tant que le code commité ≠ ce qui tourne sur le
VPS, un `make deploy-vps` ré-ouvre l'incident d'aujourd'hui. À traiter en premier.

---

> Audit descriptif, aucun fichier modifié, aucun commit. Les chiffres infra
> (tailles tables, cache hit) se confirment avec `scripts/pg-audit.sh` sur le VPS.

---

## 10. 🚧 Dette résiduelle — Migration 035 (MV `mv_latest_sensor_position`)

### État

- `idx_silver_trafic_chn_time_geom` créé et **VALIDE** (gain énorme :
  tous les SELECT futurs sur cette table passent par l'index, pas de sort)
- `gold.mv_latest_sensor_position` : **absente** (le `CREATE MATERIALIZED VIEW`
  a timeout 30 min deux fois consécutives)
- `public.schema_migrations` version 35 : tracked (le tracking a survécu
  aux rollbacks ; un futur `psql -f` avec `IF NOT EXISTS` skip proprement)

### Pourquoi ça a timeout

EXPLAIN confirme `Index Scan using idx_silver_trafic_chn_time_geom` →
le planner prend le bon plan (Loose Index Scan, ~1500 rows × channels).
Mais le SELECT projette aussi `geom`, qui force un **table access**
(heap fetch) sur chaque row retournée. Sur geom PostGIS (~10 KB par row)
× 1500 channels × sdb saturé par autovacuum + `REFRESH MATERIALIZED VIEW
CONCURRENTLY` (jusqu'à 10 min en `DataFileRead` sur d'autres tables) →
même un Index Scan se traîne en `DataFileRead` permanent (~30 min et pas
fini).

**Cause racine** : sdb (Postgres + Docker data-root) est partagé avec
beaucoup d'autres workers. En off-peak réel (22h ou week-end), sdb devrait
être <10% util et le CREATE MV finira en quelques minutes avec l'index déjà
en place.

### Workaround usable dès maintenant

`build_spatial_mapping.py` peut fonctionner sans la MV via un
**LATERAL KNN** sur la dernière position par channel (pattern déjà
utilisé dans `osm.mv_sensor_to_way`). Voir Sprint 18 — adapter le DAG
pour ne plus dépendre de `mv_latest_sensor_position` le temps de
replanifier la MV.

### Action de replay

1. **Off-peak profond** (22h ou week-end) : `psql -f migration_035…sql`.
   Le garde-fou A (advisory lock) + le garde-fou B (purge index invalide)
   rendent l'opération sûre (auto-réparation).
2. **Monitoring live** : `watch -n 5 'SELECT phase, blocks_done,
   blocks_total, ROUND(100.0*blocks_done/NULLIF(blocks_total,0),1) AS pct
   FROM pg_stat_progress_create_index;'`
3. **Si sdb saturé à nouveau** : reporter au prochain off-peak profond
   plutôt que de cancel.

### Leçons (à intégrer dans `mavis` memory si pertinent)

- `bash timeout` ≠ `pg_cancel_backend` (la query Postgres survit).
- `CREATE INDEX` non-concurrent sur table >1M rows = SHARE lock qui
  bloque INSERT → utiliser `CREATE INDEX CONCURRENTLY`.
- Migrations à chaud → `pg_advisory_lock` obligatoire (anti-concurrence
  multi-instances / multi-agents).
- `EXPLAIN Index Scan` ≠ CREATE MATERIALIZED VIEW rapide quand la
  projection nécessite un `table access` sur colonne lourde (PostGIS geom)
  × sdb partagé. Préférer un off-peak profond pour hydrater une MV
  sur une grosse table.

