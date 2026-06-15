# Plan de correction P3 + P4 — LyonFlowFull

**Date** : 2026-06-14
**Origine** : `AUDIT_INTEGRATION_LIVE.md` (backlog)
**Mode** : P0 (5) + P1 (6) + P2 (6) terminés. P3 = dette schéma + UX, P4 = tests + doc + git.

## P3 — Backlog dette schéma + UX

### P3.1 — Vues Gold manquantes (mv_kpis_12_months, mv_otp_heatmap, etc.)
**Constat** : `db_query.py` référence 4 vues/tables qui n'existent pas :
- `gold.mv_kpis_12_months` (utilisé par `get_kpis_12_months`, persona Élu)
- `gold.mv_otp_heatmap` (utilisé par `get_otp_heatmap`, persona Pro)
- `gold.fact_correlation_matrix` (utilisé par `get_correlation_matrix`, persona Pro)
- `gold.amenagements_history` (utilisé par `get_amenagements_passes`, persona Élu)

Le lyonflow-project memory note (Sprint 11) que `mv_kpis_12_months` a déjà
été créée avec succès sur le VPS, mais pas commitée dans alembic ni dans
`init-db.sql`. Idem pour les autres.

**Action** : migration alembic 0007 qui crée les 4 vues/tables (vides ou
pré-peuplées avec saisonnalité Lyon comme Sprint 11).

**Pourquoi d'abord** : le plus gros bloc de dette schéma. Bloque les
dashboards Élu/Pro en mode prod sans DB bien seedée.

**Risque** : modéré — les vues matérialisées nécessitent des queries
sous-jacentes correctes. Je m'aligne sur les colonnes déjà consommées
par les widgets.

### P3.2 — Aligner `init-db.sql`
**Constat** : `init-db.sql` (le `pg_dump` initial) ne contient pas
`velov_features`, `bus_delay_segments`, `infrastructure_bottlenecks` —
3 tables créées runtime par le DAG gold. Si quelqu'un bootstrap avec
`init-db.sql` seul (sans alembic), ça casse.

**Action** : ajouter les 3 `CREATE TABLE` à `init-db.sql` (cohérent avec
ce que font les DAGs runtime). Ne pas casser le dump existant.

**Pourquoi en 2e** : dette schéma. Si Patrice re-bootstrap un jour, ça
marchera direct.

**Risque** : faible — `CREATE TABLE IF NOT EXISTS` partout.

### P3.3 — Script seed `gold.app_users` (admin initial)
**Constat** : la table existe (P1.5) mais vide. Sans utilisateur, le login
API est inutilisable.

**Action** : créer `scripts/seed_app_users.py` qui :
- génère un user admin avec bcrypt hash
- prompt interactif pour le mdp (sécurité)
- option `--create-default` pour créer un user démo `demo2026` (utile
  pour les tests Jedha)
- idempotent : skip si user existe déjà

**Pourquoi en 3e** : bloque le login en prod, mais nécessite un mot de
passe saisi interactivement — c'est Patrice qui décide.

**Risque** : aucun.

### P3.4 — Bug `velov_widget`: station_id str vs int
**Constat** : `dashboard/components/widgets/usager/velov_widget.py:60` fait
`station_id = str(s.get("station_id", ""))` mais le dict retourné par
`load_velov_stations` (data_loader.py:315) a `id` (int) au lieu de
`station_id` (str). Donc le lookup dans `pred_30.get(station_id)` ne
matche jamais.

**Action** : corriger `load_velov_stations` pour exposer `station_id`
au lieu de `id`, ou corriger le widget pour utiliser `id`.

**Pourquoi en 4e** : bug UI silencieux, mais le matching ne marche
qu'en mock (où les IDs sont alignés).

**Risque** : aucun — cosmétique UI.

### P3.5 — Suppression `legacy_github/dag_pipeline.py`
**Constat** : ce DAG est marqué "legacy" dans le memory. Il n'est plus
utilisé mais il est scanné par Airflow (en mode PAUSED). Pollution UI.

**Action** : déplacer dans `dags/_archive/` (cohérent avec le pattern
P0.1), garder un `.airflowignore` dans `_archive/`.

**Pourquoi en 5e** : dette technique, pas urgent.

**Risque** : aucun.

## P4 — Tests + Doc + Git

### P4.1 — Tests d'intégration Mon Trajet
**Constat** : les 4 stubs P0.2 (lieux × 2, cadence, drift) ne sont couverts
par aucun test. Si quelqu'un casse leur signature, rien ne le détecte.

**Action** : `tests/integration/test_usager_mon_trajet_loaders.py` qui :
- importe les loaders
- vérifie que les stubs retournent les bons types
- vérifie que la signature n'a pas changé

**Pourquoi** : éviter la régression des fixes P0.2.

**Risque** : aucun.

### P4.2 — Mettre à jour `AUDIT_INTEGRATION_LIVE.md`
**Constat** : l'audit original liste les bugs en statut "à corriger".
Maintenant ils sont fixés (P0+P1+P2+P3).

**Action** : ajouter une section "État post-correction (2026-06-14)" qui
liste ce qui a été fixé et les commits. Ne pas effacer l'audit original
(intérêt historique).

**Risque** : aucun.

### P4.3 — Commits séparés par fix
**Constat** : tous les fixes sont actuellement uncommitted. Risque de
"big bang commit" difficile à review.

**Action** : commit par Sprint (P0, P1, P2, P3) avec message clair.
Patrice push lui-même (il a la clé write, moi j'ai pas l'autorisation
sur son remote).

**Pourquoi** : propreté git. Patrice décide s'il veut merger.

**Risque** : aucun pour moi (je ne push pas).

## Règles pendant les fixes

1. Un fix à la fois, vérif immédiate.
2. Documentation inline (P0/P1/P2/P3 audit refs) sur chaque fix.
3. Smoke tests à la fin de chaque sprint.

## État d'avancement

- [x] P0 (5 fixes) — terminé
- [x] P1 (6 fixes) — terminé
- [x] P2 (6 fixes) — terminé
- [ ] P3.1 4 vues Gold
- [ ] P3.2 init-db.sql alignement
- [ ] P3.3 seed app_users
- [ ] P3.4 velov_widget bug
- [ ] P3.5 legacy_github archive
- [ ] P4.1 test Mon Trajet
- [ ] P4.2 doc update
- [ ] P4.3 git commits
- [ ] Vérification finale
