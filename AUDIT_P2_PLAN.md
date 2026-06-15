# Plan de correction P2 — LyonFlowFull

**Date** : 2026-06-14
**Origine** : `AUDIT_INTEGRATION_LIVE.md` (sections "P2")
**Mode** : P0 (5 fixes) + P1 (6 fixes) terminés. P2 = optimisations + dette schéma.

## Ordre d'attaque P2 (par criticité)

### P2.1 — Réduire horizons XGBoost (1 par modèle)
**Constat** : `dags/ml/retrain_xgboost.py` entraîne 4 horizons speed (5/60/180/360)
et 2 horizons velov (30/60). CLAUDE.md dit "H+1h focus" + "H+30min Vélov uniquement".
C'est du gaspillage CPU/RAM sur le VPS.

**Action** :
- speed : `[60]` uniquement (1 modèle)
- velov : `[30]` uniquement (1 modèle)

**Pourquoi d'abord** : c'est purement du tuning, pas de risque de régression
fonctionnelle (les modèles entraînés sont moins nombreux mais équivalents).

**Risque** : modéré — les modèles déjà entraînés (`.pkl` files) restent
utilisables, mais les anciens `.pkl` H+5min/H+3h/H+6h ne seront plus mis à
jour (ok, c'est le but). Les callers de `predict(horizon_minutes=...)` avec
d'autres valeurs retournent le fallback (déjà géré).

### P2.2 — Géocoder dynamiquement les bottlenecks carte Élu
**Constat** : `dashboard/components/widgets/elu/bottleneck_map.py:20-31` hardcode
10 zones (lat/lon fixes). Les bottlenecks réels (DB) sont silencieusement
ignorés s'ils ne sont pas dans la liste.

**Action** : utiliser directement `lat`/`lon` de `gold.infrastructure_bottlenecks`
(la table est créée par le DAG gold). Garder le fallback hardcodé pour le mode
démo.

**Pourquoi en 2e** : UX cassée silencieusement. La migration 0005 (P2.5) crée
la table `infrastructure_bottlenecks` au bootstrap — donc on a besoin de
l'alignement avant ou en même temps.

**Risque** : faible — la logique hardcodée reste en fallback démo.

### P2.3 — Idempotence INSERT `trafic_predictions`
**Constat** : `dags/ml/dag_live_speed_retrain.py:174-189` INSERT sans
`ON CONFLICT`. Si un retry arrive avec le même `calculated_at`, ça crash
(PK violation) au lieu de skip.

**Action** : ajouter `ON CONFLICT (axis_key, horizon_h, calculated_at) DO NOTHING`
sur l'INSERT.

**Pourquoi en 3e** : amélioration de robustesse, pas de crash actuel. Mais c'est
quick fix et c'est la bonne pratique.

**Risque** : aucun — `DO NOTHING` est strict subset du comportement actuel
(succès si pas de conflit, no-op sinon au lieu de crash).

### P2.4 — Audit rate-limit async (sampling)
**Constat** : `src/api/middleware/rate_limit.py:62-69` appelle `log_audit`
(de manière synchrone) à chaque rate-limit exceeded. Sous attaque = saturation DB.

**Action** : sampler (1 audit sur 10) + queue optionnelle. Pour P2 je fais
juste le sampling — la queue nécessite un worker.

**Pourquoi en 4e** : nice-to-have, l'impact réel est faible en prod normale.

**Risque** : aucun — on perd juste de l'audit fin en cas d'attaque.

### P2.5 — Migrations alembic pour `bus_delay_segments` + `infrastructure_bottlenecks`
**Constat** : ces 2 tables sont créées runtime par `silver_to_gold.py:285,411`
mais absentes du bootstrap `init-db.sql`. Conséquence : un bootstrap frais +
alembic + DAG gold jamais lancé = crash des widgets qui lisent ces tables.

**Action** : 2 migrations alembic (0005 + 0006) pour aligner le bootstrap.

**Pourquoi en 5e** : dette schéma à fort impact (P0.4 widgets Élu).

**Risque** : aucun.

### P2.6 — Migrations `mv_line_kpis_live` + `referentiel_lieux` + autres vues
**Constat** : les stubs P0.2 + la query P0.4 ciblent des tables/vues qui
n'existent pas (`gold.mv_line_kpis_live`, `referentiel.lieux_lyon`,
`referentiel.lieux_transports`, `referentiel.lieux_calendrier`,
`gold.amenagements_history`, `gold.fact_correlation_matrix`,
`gold.mv_kpis_12_months`, `gold.mv_otp_heatmap`, `gold.xgb_training_set`).

**Action** : créer les vues/tables critiques via migrations alembic.
- `gold.mv_line_kpis_live` (vue matérialisée — widgets Pro/Élu)
- `referentiel.lieux_lyon` (table — autocomplete, markers)
- `referentiel.lieux_transports` (table — itinerary)
- `referentiel.lieux_calendrier` (table — cadence)
- `gold.xgb_training_set` (table — XGBoost speed)

Pour les autres (`amenagements`, `correlation_matrix`, `mv_kpis_12_months`,
`mv_otp_heatmap`) — c'est du nice-to-have, je laisse en commentaire dans
le rapport final.

**Pourquoi en 6e** : grosse dette schéma. C'est le plus gros morceau de P2
mais sans risque.

**Risque** : modéré — créer une vue matérialisée nécessite de définir
correctement la query sous-jacente. Je m'aligne sur les queries existantes
des callers.

## Règles pendant les fixes

1. Un fix à la fois, vérif immédiate.
2. Pas de modif hors scope.
3. Documentation inline (P0/P1/P2 audit refs) sur chaque fix.

## État d'avancement

- [x] P0 (5 fixes) — terminé 2026-06-14
- [x] P1 (6 fixes) — terminé 2026-06-14
- [ ] P2.1 horizons XGBoost
- [ ] P2.2 géocoder bottlenecks
- [ ] P2.3 idempotence INSERT
- [ ] P2.4 audit sampling
- [ ] P2.5 bus_delay + infra_bottlenecks
- [ ] P2.6 mv_line_kpis + referentiel_lieux
- [ ] Vérification finale P2
