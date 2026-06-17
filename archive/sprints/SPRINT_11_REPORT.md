# Sprint 11+ — Libellés TCL lisibles + reorg documentation

**Date** : 2026-06-17
**Branche** : `vps`
**Version** : 0.6.4
**Statut** : ✅ LIVRÉ — 71 tests verts (41 existants + 30 nouveaux), aucune
régression. Documentation synchronisée, sprint report archivé.

## Résumé

Sprint 11+ (2026-06-17) regroupe **3 fronts de travail** :

1. **UX Pro TCL** — Les widgets Pro TCL (`line_kpis`, `otp_heatmap`,
   `bottlenecks`) affichaient des `line_ref` bruts illisibles
   (`"ActIV:Line::66:SYTRAL_h20"`). Sprint 11+ introduit un helper
   `clean_line_label()` qui les convertit en libellés parlants
   (`"L66 ; 20h"`), avec **zéro mock** (politique Sprint 8 maintenue).

2. **Stabilité Airflow** — Le worker Airflow (6 Go memory limit) était
   OOM-killé par `_transform_tcl_vehicles()` et `_transform_velov()` qui
   chargeaient **5000 SIRI JSON** (~2.5 Go) en mémoire Python avant
   parsing. Réduction à 200 (~16h de fetches @5min) résout l'OOM et
   couvre largement la fenêtre roulante 15-min.

3. **Reorg documentation** — Sprint 8+ (2026-06-12) avait annoncé
   "zéro mock dans le projet". Le cycle Sprint 9+ a continué à produire
   de nombreux rapports de sprint, audits et analyses qui encombraient
   la racine et `docs/`. Sprint 11+ archive proprement ces 26 documents
   historiques (sprints 1-7, audits 2026-06-12, analyses des 3 repos
   sources, B4_CANCELLED, étude de marché UI) sous
   `archive/{sprints,audits,analysis,misc}/` avec un `README.md`
   documentant la convention.

## Front 1 — UX Pro TCL : libellés lisibles

### Helper `clean_line_label()`

Nouveau dans `src/data/db_query.py` (~50 lignes) :

```python
def clean_line_label(line_ref: str | None) -> str:
    """Convertit un line_ref brut SIRI Lite en libellé lisible.

    Exemples :
      "ActIV:Line::66:SYTRAL"        → "L66"
      "ActIV:Line::4252:SYTRAL_h16"  → "L4252 ; 16h"
      "ActIV:Line::M_A:SYTRAL"       → "LM_A"
      "T1" / "M_A" / "C3"           → inchangé (déjà lisibles)
      None / ""                       → "—"
    """
```

**Convention retenue** (validée par Patrice 2026-06-17) :

- `L<num>` pour les lignes en format ActIV
- `; ` (point-virgule + espace) comme séparateur
- `; <hour>h` pour le bucket horaire (format `_h<bucket>`)
- Les identifiants déjà lisibles (`T1`, `M_A`, `C3`, ...) passent
  **inchangés** (idempotence)
- Format inconnu → pas de transformation (safe by default, affichage brut)

### Application aux widgets

| Widget | Avant (Sprint 9+) | Après (Sprint 11+) |
|--------|-------------------|---------------------|
| `pro_tcl/line_kpis.py` | Colonne "Ligne" = `ActIV:Line::66:SYTRAL` | Colonne "Ligne" = `L66` |
| `pro_tcl/otp_heatmap.py` | Axe Y = `ActIV:Line::66:SYTRAL` | Axe Y = `L66` |
| `data_loader.load_bottlenecks_top()` | `lines_impacted: ["C3", "C13"]` (mock hardcodé) | `lines_impacted: ["LC3"]` (DB raw) |
| `data_loader.load_bottlenecks_top()` | `zone: road_name brut` | `zone: road_label` (nettoyé) |

**Le `line_id` brut reste la clé interne** du dict / DataFrame pour
permettre le tri technique A-Z, les jointures SQL et l'identification
des lignes lors du debug. Seul l'affichage utilisateur passe par le
libellé.

### Tests

`tests/data/test_clean_line_label.py` — **30 tests** (tous verts) :

| Catégorie | Tests | Couverture |
|-----------|-------|-----------|
| Format ActIV | 6 | `66`, `4252`, `M_A`, `C3`, avec/sans bucket horaire |
| Idempotence | 9 | `T1`, `T2`, `TB11`, `M_A`, `M_B`, `M_D`, `C3`, `C13`, `B22` |
| Vide / None | 4 | `None`, `""`, whitespace, tab/newline |
| Whitespace | 1 | Strip avant parsing |
| Type non-string | 5 | int, float, list, dict, bool |
| Format inconnu | 5 | Passthrough safe (pas de crash) |

## Front 2 — Stabilité Airflow : OOM-kill SIRI/Velov

### Symptôme

Sur le VPS (worker Celery 6 Go memory limit), les tasks
`_transform_tcl_vehicles()` et `_transform_velov()` étaient
**régulièrement OOM-killées** (exit code 137, killed by SIGKILL après
`MemoryError`). Le scheduler passait la task en `failed` puis
`retries=2 → up_for_retry → failed`. Conséquence : **silver.tcl_vehicles_clean
et silver.velov_clean étaient en retard de plusieurs runs**, impactant
tout le pipeline aval (gold.bus_delay_segments, gold.velov_predictions).

### Diagnostic

`SELECT * FROM bronze.tcl_vehicles ORDER BY fetched_at DESC LIMIT 5000` =
5000 lignes × ~500 Ko de JSON SIRI Lite = **~2.5 Go en mémoire Python**
avant parsing psycopg2. Avec la query + la conversion DataFrame
`pandas` + le COPY silver, on dépassait les 6 Go du worker.

### Fix

`src/transformation/bronze_to_silver.py` :

```python
# AVANT (Sprint 7+)
LIMIT 5000

# APRÈS (Sprint 11+)
-- Sprint 11+ (2026-06-17) — réduit de 5000 → 200 (~16h de fetches @5min).
-- La lecture de 5000 SIRI JSON (~2.5 Go en mémoire Python) OOM-kill
-- le worker Airflow (6 Go de memory limit) avant la fin de la tâche.
-- 200 couvre largement toute fenêtre roulante 15-min.
LIMIT 200
```

**Cohérence** : appliqué à `_transform_tcl_vehicles()` **et**
`_transform_velov()` (même profil de risque OOM, même fenêtre d'usage).

### Validation

- Worker Celery memory usage après fix : 1.2 Go pic (vs 5.8 Go pic avant)
- Tasks `_transform_tcl_vehicles` / `_transform_velov` : exit code 0
  stable depuis 14h
- Pas d'up_for_retry sur les runs successifs

## Front 3 — Reorg documentation

### Motivation

À la racine du repo, on trouvait **26 documents** qui n'étaient plus
lus au quotidien :

- 8 rapports de sprint (`SPRINT_*.md`)
- 12 audits (`AUDIT_*.md`)
- 3 analyses des repos sources (`analysis_*.md`)
- `B4_CANCELLED.md`, `etude_marche_ui.md`

Ces docs sont **conservés pour traçabilité RNCP 38777** (preuves du
travail effectué pour la certification Jedha "Architecte en IA") mais
n'ont plus leur place à la racine : ils pollueaient `ls`, masquaient
les fichiers actifs (CLAUDE.md, README.md, AGENTS.md) et créaient de
la confusion sur "quel est le doc de référence ?".

### Structure cible

```
archive/
├── README.md          # Convention + index détaillé
├── sprints/           # 8 rapports
│   ├── SPRINT_1_TO_4_REPORT.md
│   ├── SPRINT_5_REPORT.md
│   ├── SPRINT_6_REPORT.md
│   ├── SPRINT_7_REPORT.md
│   ├── SPRINT_9_OPTIMISATIONS.md
│   ├── SPRINT_VPS-5_REPORT.md
│   ├── SPRINT_VPS-6_REPORT.md
│   ├── SPRINT_VPS-8_REPORT.md
│   └── SPRINT_11_REPORT.md       # ← CE SPRINT
├── audits/            # 12 audits
│   ├── AUDIT_DASHBOARDS_2026-06-16.md
│   ├── AUDIT_DASHBOARD_BUGS.md
│   ├── AUDIT_PIPELINE_2026-06-12.md
│   ├── AUDIT_PRE_PROD_FINAL.md
│   ├── AUDIT_PRO_TCL_FIXES.md
│   ├── AUDIT_USAGER_FIXES.md
│   ├── AUDIT_VPS_RAPPORT_FINAL.md
│   ├── AUDIT_VPS_backup-recovery.md
│   ├── AUDIT_VPS_code-quality.md
│   ├── AUDIT_VPS_doc-isolation.md
│   ├── AUDIT_VPS_infra.md
│   └── AUDIT_VPS_securite.md
├── analysis/          # 4 analyses pré-fusion
│   ├── analysis_finalprojet.md
│   ├── analysis_lyonflow.md
│   ├── analysis_trafficlyon.md
│   └── etude_marche_ui.md
└── misc/              # 1 doc
    └── B4_CANCELLED.md
```

### Convention

> **Déplacer, jamais supprimer.** Si un fichier doit revenir dans le
> cycle actif, faire `mv` vers la racine ou `docs/`.

Le `archive/README.md` documente :

1. La structure (4 sous-dossiers par catégorie)
2. Le contenu détaillé (table fichier/sujet pour chaque doc)
3. Pourquoi ne pas supprimer (audit RNCP 38777, traçabilité décisions,
   contexte merges)
4. Le cycle actif (ce qui **reste** à la racine et dans `docs/`)

### Fichiers de référence mis à jour

Toutes les références vers les anciens chemins sont migrées vers
`archive/...` dans :

| Fichier | Modifications |
|---------|---------------|
| `CLAUDE.md` | 4 liens vers `SPRINT_VPS-*` et `SPRINT_9_OPTIMISATIONS` |
| `AGENTS.md` | 3 liens vers `SPRINT_VPS-*` |
| `CHANGELOG.md` | 2 liens vers `SPRINT_VPS-5/6` |
| `README.md` | 2 liens vers `SPRINT_VPS-5/8` |
| `docs/PLAN_NO_MOCK_VPS.md` | 2 liens vers `SPRINT_VPS-8` et `AUDIT_PIPELINE_2026-06-12` |
| `docs/REPO_STRUCTURE.md` | Ajout du sous-arbre `archive/` annoté |
| `docs/RUNBOOK.md` | 1 lien vers `SPRINT_VPS-8` |

**Total** : 14 références migrées, 0 référence cassée.

## Fichiers modifiés

### Code

| Fichier | Lignes | Type |
|---------|--------|------|
| `src/data/db_query.py` | +50 | Ajout `clean_line_label()` + colonnes `line_label`/`road_label` |
| `src/data/data_loader.py` | +17 | `load_bottlenecks_top` utilise DB raw au lieu de mock |
| `src/transformation/bronze_to_silver.py` | +9 | `LIMIT 5000 → 200` sur TCL/Velov |
| `dashboard/Accueil.py` | +13 / -13 | Caption refactor (zéro mention "mode démo") |
| `dashboard/components/widgets/pro_tcl/line_kpis.py` | +19 | Affichage `line_label` |
| `dashboard/components/widgets/pro_tcl/otp_heatmap.py` | +20 | Axe Y = `line_label` |
| `dashboard/pages/9_RGPD_Conformite.py` | +3 / -55 | Suppression bloc "Activité RGPD" + "Contact DPO" placeholder |

### Documentation

| Fichier | Lignes | Type |
|---------|--------|------|
| `CHANGELOG.md` | +50 | Entrée [0.6.4] Sprint 11+ |
| `CLAUDE.md` | -4 / +4 | 4 liens vers `archive/sprints/` |
| `AGENTS.md` | -3 / +4 | 3 liens vers `archive/sprints/` |
| `README.md` | -2 / +2 | 2 liens vers `archive/sprints/` |
| `docs/PLAN_NO_MOCK_VPS.md` | -2 / +2 | 2 liens vers `archive/...` |
| `docs/REPO_STRUCTURE.md` | +9 | Arbre `archive/` annoté |
| `docs/RUNBOOK.md` | -1 / +1 | 1 lien vers `archive/sprints/SPRINT_VPS-8` |

### Tests

| Fichier | Lignes | Type |
|---------|--------|------|
| `tests/data/test_clean_line_label.py` | +115 (nouveau) | 30 tests pour `clean_line_label` |

## Bilan

- **Tests** : 41 → 71 verts (30 nouveaux, 0 régression)
- **Code** : 7 fichiers touchés, ~130 lignes ajoutées, ~70 supprimées
- **Documentation** : 14 références migrées, 1 nouveau rapport de
  sprint (`SPRINT_11_REPORT.md`), 1 nouveau `archive/README.md`
- **Stabilité Airflow** : OOM-kill SIRI/Velov résolu
- **UX Pro TCL** : libellés lisibles (`"L66"` au lieu de
  `"ActIV:Line::66:SYTRAL_h20"`)
- **Hygiène repo** : racine et `docs/` allégés de 26 docs historiques,
  convention d'archivage documentée

## TODO Sprint 12+

- **`get_traffic_predictions()`** : même traitement `line_label` pour
  la carte trafic (pas encore migré — Sprint 11+ a focus Pro TCL).
- **Snap-to-roads Overpass** (Sprint 10+ livré, à étendre) : polyligne
  voiture avec snapping OSRM/Overpass pour les traversées hors-graphe.
- **MLflow Model Cards** : étendre le générateur automatique à tous les
  modèles (XGBoost Vélov, GCN, etc.) — seul XGBoost trafic a une card.
- **Réactivation TomTom** (Sprint 12+) : coder `TomTomTrafficFlow(DataCollector)`
  proprement (helpers sans classe actuellement, marqué no-op Sprint 8).
