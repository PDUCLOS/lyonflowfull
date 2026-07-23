# Archive — Documents historisés

Ce dossier contient les documents Markdown qui ne sont plus utilisés au quotidien
mais qui sont conservés pour traçabilité (audit RNCP 38777, historique projet,
preuves de décisions techniques passées).

**Convention** : déplacer ici, jamais supprimer. Si un fichier doit revenir dans
le cycle actif, faire `mv` vers la racine ou `docs/`.

## Structure

```
archive/
├── sprints/      # Rapports de sprint livrés (sprints 1-9+, VPS-5/6/8)
├── audits/       # Audits ponctuels (qualité, infra, sécurité, dashboards)
├── analysis/     # Analyses des 3 repos sources (pré-fusion, obsolète)
├── dags_disabled/# DAGs Airflow archivés (training/inf séparés, etc.)
├── scripts/      # Scripts one-off (codemods, migrations ponctuelles) déjà appliqués
├── misc/         # Documents divers annulés ou contextuels
├── legacy/       # Composants code archivés (ex: GNN)
└── REPO_STRUCTURE.md  # Snapshot structure repo (June 2026, obsolète depuis GNN archivé + tests 104→620)
```

### `scripts/` (2026-07-03)

Scripts one-off (codemods de refacto + 1 migration schema) déjà exécutés — le
code qu'ils modifient est déjà dans `dashboard/`/`src/`, ils ne servent plus.
Différents des migrations numérotées de `scripts/sql/` (celles-ci restent
actives, gérées par `scripts/apply-migrations.sh`, ne pas y toucher).

| Fichier | Sujet |
|---------|-------|
| `fix_pages_imports.py` / `fix_pages_imports_v2.py` | Codemod imports dashboard/pages |
| `fix_freshness_badge_imports.py` | Codemod imports `freshness_badge` |
| `migrate_error_display.py` | Codemod migration vers `error_display.py` |
| `migrate_folium_to_a11y.py` | Codemod migration cartes Folium → wrapper a11y |
| `migrate_font_size_to_lyf.py` | Codemod tailles police → thème LYF |
| `migrate_freshness_badge.py` | Codemod intégration `freshness_badge` |
| `migrate_loading_states.py` / `migrate_loading_states_v3.py` | Codemod `loading_wrapper` |
| `migrate_plotly_to_a11y.py` | Codemod graphiques Plotly → wrapper a11y |
| `migrate_realign_v0.3.1.sql` | Migration schema one-off v0.3.1 (hors pipeline `apply-migrations.sh`) |

## Contenu détaillé

### `sprints/` (18 rapports/specs)

| Fichier | Sujet |
|---------|-------|
| `SPRINT_1_TO_4_REPORT.md` | Phases 1-4 initiales (production-ready local) |
| `SPRINT_5_REPORT.md` | Pathfinding H3 Dijkstra + focus H+1h (legacy 4 horizons) |
| `SPRINT_6_REPORT.md` | Migration 6 widgets DB + RGPD live + 42 tests |
| `SPRINT_7_REPORT.md` | MV line_kpis_live + heatmap OTP (155 lignes × 4416 triplets) |
| `SPRINT_VPS-5_REPORT.md` | DAG `dag_live_speed_retrain` hourly + 4 horizons XGBoost |
| `SPRINT_VPS-6_REPORT.md` | Référentiel lieux (lieux_lyon/lieux_transports/lieux_calendrier) |
| `SPRINT_VPS-8_REPORT.md` | Sprint 8 (zero mock + focus H+1h + backfill lat/lon) |
| `SPRINT_9_OPTIMISATIONS.md` | Découplage training/inf + GNN données réelles + MinIO sdb2 |
| `SPRINT_11_REPORT.md` | Sprint 11+ (libellés TCL lisibles + OOM-kill SIRI fix + reorg docs) |
| `SPEC_SPRINT_16.md` | Spec Sprint 16 — validation modèle + qualité données + durées réelles |
| `SPEC_COMPARATEUR_MODES_USAGER.md` | Spec Sprint 15+ — comparateur 3 modes (implémenté) |
| `SPEC_PGROUTING_INTEGRATION.md` | Spec Sprint 18 — pgRouting voiture sur OSM (implémenté, en prod) |
| `SPEC_EVIDENTLY_CONFIGURATION.md` | Spec Sprint 16 Axe A — config Evidently/drift detection (implémenté) |
| `MODIFICATIONS_IA_SPRINT22.md` | Résumé Sprint 22+ — optimisations UX/RAM (lazy loading, onglets) |
| `SPEC_SPRINT_20_UX.md` | Spec Sprint 20 — amélioration UX dashboard (implémenté) |
| `SPEC_SPRINT_21.md` | Spec Sprint 21 — quantile regression + sparkline + docs cleanup |
| `SPRINT_21_REPORT.md` | Rapport Sprint 21 — livré v0.11.0 |
| `SPEC_FIX_ELU2_BOTTLENECKS.md` | Spec Sprint 22++ — 9 bugs Elu_2 (implémenté, v0.12.1) |

### `audits/` (18 rapports)

| Fichier | Sujet |
|---------|-------|
| `AUDIT_VPS_RAPPORT_FINAL.md` | Synthèse audit VPS 2026-06-12 |
| `AUDIT_VPS_backup-recovery.md` | Audit backup/recovery VPS |
| `AUDIT_VPS_code-quality.md` | Audit qualité code |
| `AUDIT_VPS_doc-isolation.md` | Audit isolation docs/scripts |
| `AUDIT_VPS_infra.md` | Audit infra (conteneurs, volumes, réseau) |
| `AUDIT_VPS_securite.md` | Audit sécurité (credentials, SSH, firewall) |
| `AUDIT_DASHBOARD_BUGS.md` | Audit bugs dashboard pré-prod |
| `AUDIT_PRE_PROD_FINAL.md` | Audit pré-prod final |
| `AUDIT_DASHBOARDS_2026-06-16.md` | Audit dashboards 2026-06-16 |
| `AUDIT_PIPELINE_2026-06-12.md` | Audit pipeline complet (mock résiduels, schéma v0.3.1) |
| `AUDIT_PRO_TCL_FIXES.md` | Tracker corrections Pro TCL (8/14 faits, 6 cosmétiques restants) |
| `AUDIT_USAGER_FIXES.md` | Tracker corrections Usager (11/16 faits, 5 cosmétiques restants) |
| `AUDIT_CERTIFICATION_2026-07-01.md` | Audit certification RNCP 38777 — snapshot 2026-07-01 (tous items "Corrigé aujourd'hui", photo historique) |
| `RAPPORT_VPS_2026-06-22.md` | Rapport ops cleanup VPS (sda1 88%→47%, backup timer créé) |
| `SPRINT_24_FIX_GOLD_STALE.md` | Incident gold stale (0 lignes TCL, carte indispo) — fix livré |
| `AUDIT_DB_2026-06-30.md` | Audit DB (migrations, tuning, bloat, MV) — snapshot 2026-06-30 |
| `AUDIT_PROJET_2026-06-30.md` | Audit projet (P0 dérive source↔runtime, réconcilié le jour même) |

### `analysis/` (6 docs)

| Fichier | Sujet |
|---------|-------|
| `analysis_finalprojet.md` | Analyse repo `caroheymes/Architect-IA-final-project` (GNN, dataset) |
| `analysis_lyonflow.md` | Analyse repo `PDUCLOS/LyonFlow` (DAGs, ingestion, routing) |
| `analysis_trafficlyon.md` | Analyse repo `PDUCLOS/lyontraffic` (Medallion, dashboard) |
| `etude_marche_ui.md` | Étude de marché UI (3 personas, wireframes) |
| `INVENTAIRE_WIDGETS_2026-06-23.md` | Inventaire exhaustif widgets Streamlit — snapshot 2026-06-23 |
| `INVENTAIRE_WIDGETS_CALCULS_2026-06-23.md` | Inventaire widgets — code/logique/calculs — snapshot 2026-06-23 |

### `misc/` (3 docs)

| Fichier | Sujet |
|---------|-------|
| `B4_CANCELLED.md` | Bloc 4 Jedha annulé (détails décision) |
| `TODO_2026-06-25.md` | Ancien TODO.md (P1/P2/P3 Sprint 20-22, tous DONE) — remplacé par CLAUDE.md §Décisions ouvertes |
| `AUDIT_PIPELINE_DATA_2026-06-20.docx` | Audit pipeline data (Word, format legacy) — snapshot 2026-06-20 |
| `deploy-sprint24.sh` | Script de déploiement ciblé Sprint 24 (one-off, déjà exécuté), référençait déjà `gnn_map.py` (mort) avant même le nettoyage GNN |

## Pourquoi ne pas supprimer ?

- **Audit RNCP 38777** : les sprint reports + audits sont les preuves formelles
  du travail effectué pour la certification Jedha "Architecte en IA".
- **Traçabilité décisions** : `SPRINT_11_REPORT.md` documente les 3 fronts
  Sprint 11+ (libellés TCL, OOM-kill SIRI, reorg docs). `SPRINT_VPS-8_REPORT.md`
  documente les 3 dettes critiques résolues (zero mock, focus H+1h,
  ingestion Bronze stable). C'est l'historique technique du projet.
- **Contexte merges** : `analysis_*` peut servir si on doit re-merger ou
  comparer avec une nouvelle source.

## Cycle actif (ne PAS archiver)

Les documents suivants restent à la racine ou dans `docs/` :

- `CLAUDE.md`, `AGENTS.md` — mémoire projet active (chargée dans l'agent)
- `README.md` — entry point
- `CHANGELOG.md` — changelog versionné
- `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `NOTICE` — fichiers standard
- `docs/ARCHITECTURE.md`, `API.md`, `DEPLOYMENT.md`, `RUNBOOK.md`, `MONITORING.md`,
  `VPS_HARDENING.md`, `DASHBOARD_PAGES.md`, `DATA_GOVERNANCE.md`,
  `GIT_STRUCTURE.md`, `CONTROLE_VPS_VS_CLOUD_DEMO.md`,
  `POSTGRES_DATABASE_REFERENCE.md`, `POSTGRES_TUNING_PROD.md`,
  `DICTIONNAIRE_COLONNES.md`, `WIDGETS_CALCULS_PAR_PERSONA.md`,
  `AUDIT_AIRFLOW_POSTGRES_SPRINT24.md` (actionable — plan D pas complet),
  `SPEC_OPTIMISATION_INTERDEPENDANCES.md` (actionable — axes 2/4/6/7 restants)
- `docs/ADR/` — Architecture Decision Records (référencés depuis CLAUDE.md)
- `docs/RCA/` — Root Cause Analysis (post-mortems incidents, historique vivant)