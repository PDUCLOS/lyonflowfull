# RCA — 2026-06-29 — gold.lag monotone croissant (cassé par timeout, pas 0-ligne)

**Statut** : résolu (2 tampons temporaires en place)
**Sévérité** : haute (gold 58.6min et en hausse, toutes les prédictions trafic stale)
**Détecté** : 2026-06-29 ~17:50 Paris (Patrice signale "rien ne bouge")
**Résolu** : 2026-06-29 ~18:14 Paris

## TL;DR

`gold.traffic_features_live` montait de 6 min/cycle (27 → 30 → 58.6 min). Le diagnostic
envisagé en premier lieu était le timeout Airflow 5 min sur `build_traffic_features`
pendant les cycles à disque throttlé. C'était le bon diagnostic. Une seconde hypothèse
(« fenêtre fresh 15min → 0 ligne insérée quand silver > 15min ») a été envisagée puis
écartée par les faits : les succès 16:00 et 16:10 UTC insèrent 3 126 lignes en 290s et
182s (sous le 5min timeout) — donc la fenêtre n'était pas le problème.

## Cascade observée

| Layer | age_min (avant) | Verdict |
|-------|-----------------|---------|
| bronze | 1.9 → 3.7 | frais |
| silver | 9.2 → 12.4 → 17.2 | lagged (transform_bronze_to_silver rame aussi) |
| gold | 27.3 → 30.4 → 58.6 | stale monotone croissant |

## Diagnostic

### Hypothèse 1 — Timeout Airflow (5 min) confirmé

`task_instance` du 26-28 juin : 5+ runs `build_traffic_features` failed avec
durée 329–1117 s (5.5–18.6 min) — toutes au-dessus du timeout 5 min. Le disque
throttlé (sdb2 sur VPS, I/O saturation par refresh_heavy_mv + purges) étire
le DELETE+INSERT au-delà du timeout, le task est tué.

### Hypothèse 2 — Fenêtre fresh 15 min → 0 ligne écartée

Présence de `refresh_mv_multimodal_grid` en cours dans `pg_stat_activity`
multimodal dépend de `[traffic, velov, tcl_realtime]` avec trigger
`all_success` → multimodal ne démarre que si traffic a réussi. Donc
le bottleneck n'était PAS un 0-ligne silencieuse. Confirmé par les 2
succès 16:00 (290s) et 16:10 (182s) sous le 5min timeout.

## Fix appliqué (2 tampons, **temporaires**)

| # | Fichier | Ligne | Changement |
|---|---------|-------|------------|
| 1 | `dags/transforms/transform_silver_to_gold.py` | ~85 | `execution_timeout=timedelta(minutes=10)` (était 5) |
| 2 | `src/transformation/silver_to_gold.py` | ~169 | `_TRAFFIC_SQL`: `INTERVAL '30 minutes'` (était '15 minutes') |

**Pourquoi safe** :
- (1) couvre les cycles disque-throttled sans casser les cycles rapides (les tasks finissent toujours avant 10min).
- (2) safe grâce à `ON CONFLICT (channel_id, fetched_at) DO UPDATE` (ligne ~225) → upsert idempotent, zéro doublon même si la fenêtre chevauche des rows déjà insérées.

## Reste à froid — REVERTS après tuning Postgres Option A

**3 valeurs temporaires à revert** une fois `docs/POSTGRES_TUNING_PROD.md` appliqué et cascade revenue rapide :

- [ ] (1) `dags/transforms/transform_silver_to_gold.py` ligne ~85 : `execution_timeout=timedelta(minutes=10)` → `minutes=5`
- [ ] (2) `src/transformation/silver_to_gold.py` ligne ~169 : `INTERVAL '30 minutes'` → `INTERVAL '15 minutes'`
- [ ] (3) **PAS de revert** : `refresh_heavy_mv` reste **découplé** (`max_active_runs=1` séparé de `transform_silver_to_gold`). Le tuning fixera la root, pas le découplage.

Le découplage `refresh_heavy_mv` ↔ `transform_silver_to_gold` doit rester — c'est la bonne archi. Seul le tuning disque/SQL change.

## Vrai root cause

**Disque sdb2 throttlé sur VPS** (6 CPU, 12 Go RAM, 2×100 Go SSD en soft RAID). Le
tuning Postgres Option A (`work_mem`, `shared_buffers`, `effective_io_concurrency`)
doit ramener silver et gold à < 5min dans leurs fenêtres nominales.

## Surveillance mise en place

- Cron `cascade-watch` toutes les 10 min : alerte si silver > 25 min (signe qu'il faut bumperc `transform_bronze_to_silver` timeout aussi) ou gold > 30 min (fenêtre fresh atteinte).
- Cron `tuning-postgres-22h` quotidien 22h Paris : rappel tuning + checklist revert.
- **Action manuelle possible** : si silver dépasse 25 min avant le tuning, bumper
  `transform_bronze_to_silver` timeout de la même façon que `build_traffic_features`
  (5 → 10 min, REVERT après tuning).

## Diagnostic credit

Patrice (humain) a identifié le plot-twist multimodal → traffic via `all_success`
trigger, ce qui a permis d'écarter l'hypothèse fenêtre 15min en 1 observation.
Le fix était prêt en quelques minutes grâce à cette analyse.

## Métriques

- Avant : gold en hausse monotone 6 min/cycle (27 → 58.6 min en ~30 min)
- Après : gold à 2.2 min en 1 cycle post-deploy
- Tests : inchangés (fix purement runtime, zéro changement de schéma ni de logique)
- Lignes insérées en post-fix : 3 126 rows en 30 min (preuve flux rétabli)