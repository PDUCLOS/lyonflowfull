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
└── misc/         # Documents divers annulés ou contextuels
```

## Contenu détaillé

### `sprints/` (9 rapports)

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
| `SPRINT_11_REPORT.md` | Sprint 11+ (libellés TCL lisibles + OOM-kill SIRI fix + reorg docs) — **dernier sprint** |

### `audits/` (12 rapports)

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

### `analysis/` (4 docs)

| Fichier | Sujet |
|---------|-------|
| `analysis_finalprojet.md` | Analyse repo `caroheymes/Architect-IA-final-project` (GNN, dataset) |
| `analysis_lyonflow.md` | Analyse repo `PDUCLOS/LyonFlow` (DAGs, ingestion, routing) |
| `analysis_trafficlyon.md` | Analyse repo `PDUCLOS/lyontraffic` (Medallion, dashboard) |
| `etude_marche_ui.md` | Étude de marché UI (3 personas, wireframes) |

### `misc/` (1 doc)

| Fichier | Sujet |
|---------|-------|
| `B4_CANCELLED.md` | Bloc 4 Jedha annulé (détails décision) |

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
  `REPO_STRUCTURE.md`, `GIT_STRUCTURE.md`, `PROJECT_STATUS_AND_GOALS.md`,
  `PLAN_NO_MOCK_VPS.md`, `CONTROLE_VPS_VS_CLOUD_DEMO.md`
- `docs/ADR/` — Architecture Decision Records (référencés depuis CLAUDE.md)