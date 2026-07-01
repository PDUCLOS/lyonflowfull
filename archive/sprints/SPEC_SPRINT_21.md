# SPEC Sprint 21 — Bonus UX (Quantile + Sparkline + Docs cleanup)

> **Date** : 2026-06-22
> **Version cible** : v0.11.0
> **Branche** : `vps`
> **Prérequis** : Sprints 1-20 déployés (incl. Sprint 20 UX unifiée)
> **Effort** : ~3 jours (delivered)
> **Statut** : ✅ **Livré** (commit `c5c7f1e` + `c67a90e` + `20232e0`)

---

## 1. Contexte

Le Sprint 20 (UX unifiée) a livré 5 axes transversaux (loading, theme, error display, freshness, a11y).
Le Sprint 21 capitalise sur cette base avec 3 bonus quick wins + un cleanup documentaire.

## 2. P1 — Quantile regression XGBoost (bandes d'incertitude)

**Valeur** : montrer une **fourchette** P10/P50/P90 sur la carte trafic, au lieu d'une valeur unique.

### 2.1. Implémentation
- `src/models/xgboost_quantile.py` — classe `XGBoostQuantileModel` (3 quantiles alpha=[0.1, 0.5, 0.9])
- Migration 029 : `gold.trafic_predictions_quantile(axis_key, horizon_h, p10_speed, p50_speed, p90_speed, calculated_at)`
- DAG update : `dag_inference_xgboost` peuple les 3 quantiles
- Widget Plotly : bande d'incertitude entre P10 et P90, médiane en P50

### 2.2. Fichiers
- `src/models/xgboost_quantile.py` (NEW)
- `scripts/sql/migration_029_*.sql` (NEW)
- `dashboard/components/widgets/pro_tcl/trafic_quantile_map.py` (NEW)

## 3. P2 — Sparkline 24h network health (Élu)

**Valeur** : bandeau santé réseau Élu affiche maintenant **sparkline 24h** au lieu d'un gauge statique.

### 3.1. Implémentation
- `dashboard/components/sparkline.py` — widget sparkline Plotly minimal (64px height, axe X masqué)
- Migration 030 : `gold.mv_network_health_history` (table historique 24h × 96 buckets de 15min)
- DAG `record_network_health` (P4.3 fin) : insère le score toutes les 15 min
- Câblage dans `network_health_gauge.py` (Élu)

### 3.2. Fichiers
- `dashboard/components/sparkline.py` (NEW)
- `scripts/sql/migration_030_network_health_history.sql` (NEW)
- `dags/maintenance/record_network_health.py` (NEW, `*/15 min`)

## 4. P3 — Backup template + offsite config

**Valeur** : standardiser le pattern backup (pg_dump structuré + retention + offsite).

### 4.1. Implémentation
- `scripts/backup-template.sh` (NEW) — template pg_dump structuré (schemas/tables séparés)
- `scripts/backup-offsite.sh` (déjà existant Sprint VPS-2, juste affiné)
- **Systemd timer + service créés 2026-06-22** (Sprint 22 ops cleanup)

## 5. P4 — Polish final

- **P4.1** : JWT cleanup (`src/api/auth.py`) — retrait tokens expirés > 30j
- **P4.2** : 3 templates HTML rapports (Pro, Usager, Élu) avec a11y alt texts pré-écrits
- **P4.3** : DAG `record_network_health` (cf. P2 ci-dessus)

## 6. Documentation cleanup (Sprint 21)

| Action | Résultat |
|--------|----------|
| 13 docs archivées | `archive/{sprints,audits,misc}/` |
| Merge doublon `tests/ml/test_drift_detector.py` | → `tests/monitoring/test_drift_detector.py` |
| `SECURITY.md` version bump | 0.1.x → 0.11.x |
| `DASHBOARD_PAGES.md` section "mode démo" | Supprimée |
| `TODO.md` items done | Marqués, -213 lignes |

## 7. Fichiers livrés

```
src/models/xgboost_quantile.py                       (NEW)
dashboard/components/sparkline.py                     (NEW)
dashboard/components/widgets/pro_tcl/trafic_quantile_map.py  (NEW)
dags/maintenance/record_network_health.py             (NEW)
scripts/backup-template.sh                            (NEW)
scripts/sql/migration_029_*.sql                       (NEW)
scripts/sql/migration_030_network_health_history.sql  (NEW)
```

## 8. Tests

- +12 tests quantile regression
- +7 tests sparkline
- +4 tests network_health DAG
- **615 tests verts** au moment du merge

## 9. Critères de succès (tous ✅)

- [x] Quantile regression déployée en prod, P10/P50/P90 visibles sur carte Pro TCL
- [x] Sparkline 24h affichée dans le bandeau Élu santé réseau
- [x] Backup template scripté et documenté
- [x] DAG record_network_health tourne */15 min sans erreur
- [x] Documentation cleanup complet (13 docs archivées)
- [x] Tests verts (615 / 0 rouge)

## 10. Notes / Limitations

- Les quantiles P10/P90 sont des estimations, pas des intervalles de confiance statistiques
  au sens fréquentiste. Pour du formel, basculer vers un Bayesian credible interval (futur).
- Sparkline 24h = 96 points × 5 min granularity (P1 pourrait descendre à 1 min si besoin).
- Backup-offsite systemd timer créé mais rclone config à faire côté user (5 min, OAuth).
