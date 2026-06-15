# Plan de correction P1 — LyonFlowFull

**Date** : 2026-06-14
**Origine** : `AUDIT_INTEGRATION_LIVE.md` (sections "P1")
**Mode** : P0 terminé (validé 6/6 smoke tests). On enchaîne sur P1.

## Ordre d'attaque P1 (par criticité, sans interférence mutuelle)

### P1.1 — Schéma Vélov : `xgboost_velov.py` aligné sur Gold réel
**Constat** : `FEATURE_COLS` liste `station_id_encoded, bikes_lag_1/2/3,
rolling_mean_3h, hour_sin/cos, temperature_c, rain_mm, is_vacances, is_ferie`.
Mais `gold.velov_features` n'est pas dans l'init SQL — la table n'existe pas
sous ce nom. Sprint 9 a renommé la couche.

**Action** : aligner `FEATURE_COLS` sur le schéma Sprint 9+
(`station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos,
temperature_2m, precipitation, is_vacances, is_ferie`) et garder la même
logique.

**Pourquoi d'abord** : c'est ce qui empêche le retrain Vélov de fonctionner.
Tant que ça crash, le modèle H+30min n'est jamais (ré)entraîné.

**Risque de régression** : modéré — le code actuel plante, donc tout alignement
est une amélioration. Mais changer `temperature_c` → `temperature_2m` peut
casser un modèle déjà entraîné sur l'ancien schéma (joblib.pkl). On documente
clairement.

### P1.2 — `db_query.get_traffic_for_node` aligné sur schéma réel
**Constat** : requiert `node_idx, measurement_time, speed_lag_1, speed_lag_2,
speed_delta_1, rolling_mean_5min, hour_sin, hour_cos, temperature_c, rain_mm`
qui n'existent pas dans `gold.traffic_features_live` (qui a
`channel_id, computed_at, lag_1, lag_2, lag_3, delta_1, rolling_mean_3,
sin_hour, cos_hour, temperature_2m, precipitation`).

**Action** : réécrire la query pour matcher le schéma réel.

**Pourquoi en 2e** : même problème que P1.1 mais côté trafic. Indépendant.

**Risque de régression** : faible — la fonction retourne actuellement un DF
vide silencieux (attrapé par `_df_from_query`). Aligner = afficher de vraies
données.

### P1.3 — Flag `LYONFLOW_DEMO_AUTH_HELPER_VISIBLE` (cacher mdp en prod)
**Constat** : `auth.py:133` affiche le mdp démo en clair dans l'UI.

**Action** : 
1. Wrapper l'affichage de l'expander "Aide démo" derrière un flag env
   `LYONFLOW_DEMO_AUTH_HELPER_VISIBLE` (défaut `1`).
2. Documenter dans le `Makefile` (target `check-deploy-env` doit valider
   `LYONFLOW_DEMO_AUTH_HELPER_VISIBLE=0` en prod).

**Pourquoi en 3e** : c'est de la sécu, pas de la logique. Indépendant.

**Risque de régression** : zéro — ajout de garde, comportement par défaut
préservé en dev.

### P1.4 — TTL sur `_buckets` du rate-limit
**Constat** : `defaultdict` grossit infiniment en mémoire.

**Action** : ajouter un compteur de "dernier accès" par IP, et purger
périodiquement les clés non vues depuis > 1h. Faire ça en lazy cleanup
(dans la branche `dispatch` à chaque requête, pas en thread séparé) pour
ne pas introduire de complexité de threading.

**Pourquoi en 4e** : DoS real mais pas urgent (12 GB RAM sur VPS, le
problème se voit sur le long terme).

**Risque de régression** : faible — la logique de rate-limit reste
inchangée, on ajoute juste un nettoyage.

### P1.5 — Table `gold.app_users` (alembic migration)
**Constat** : `main.py:528` query `gold.app_users` mais la table n'existe
pas dans `init-db.sql`. L'endpoint `/api/v1/auth/login` plante en 500.

**Action** : créer une migration alembic 0003 qui crée la table avec
colonnes minimales + un CHECK constraint sur `persona_id`.

**Pourquoi en 5e** : touche à la DB schéma. Indépendant.

**Risque de régression** : zéro si la table n'existe pas. Si elle existe
déjà avec un autre nom (à vérifier avec Patrice), il faudra adapter.

### P1.6 — Câbler `reset_lieux_cache` dans `clear_all_caches`
**Constat** : `data_cache.py:211 clear_all_caches()` ne purge que
`st.cache_data`, pas le cache lieux (implémenté en TTL manuel dans
`data_loader.py:884`).

**Action** : ajouter l'appel à `reset_lieux_cache()` dans
`clear_all_caches()`.

**Pourquoi en 6e** : cosmetic, facile.

**Risque de régression** : zéro.

## Règles pendant les fixes

1. Un fix à la fois, vérif immédiate après.
2. Pas de modif hors scope.
3. Documentation inline (P0/P1 audit refs) sur chaque fix.

## État d'avancement

- [x] P0 (5 fixes) — terminé 2026-06-14
- [ ] P1.1 Vélov schéma
- [ ] P1.2 get_traffic_for_node
- [ ] P1.3 Flag mdp démo
- [ ] P1.4 TTL rate-limit
- [ ] P1.5 gold.app_users
- [ ] P1.6 reset_lieux_cache
- [ ] Vérification finale P1
