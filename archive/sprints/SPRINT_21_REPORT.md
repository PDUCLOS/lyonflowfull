# Sprint 21 Report — UX bonus + Docs cleanup (v0.11.0)

> **Période** : 2026-06-20 → 2026-06-22
> **Version livrée** : v0.11.0
> **Commits** : `481e841` → `c5c7f1e`
> **Statut** : ✅ **Clôturé**, déployé en prod (branche `vps`)

---

## 🎯 Objectif

Capitaliser sur la base UX unifiée du Sprint 20 avec 3 bonus quick wins + un cleanup documentaire complet pour stabiliser le projet avant la certif Jedha RNCP 38777.

## ✅ Livrables

### Bonus techniques (P1-P4)

| ID | Item | Effort | Statut |
|----|------|--------|--------|
| P1.2 | Quantile regression XGBoost (P10/P50/P90) | 1.5j | ✅ Livré |
| P3.3 | Backup template pg_dump structuré | 0.5j | ✅ Livré |
| P4 | JWT cleanup + 3 templates HTML rapports | 1j | ✅ Livré |
| P4.3 | DAG `record_network_health` (sparkline feeder) | 0.5j | ✅ Livré |
| **Bonus** | Sparkline 24h widget (Élu) | 0.5j | ✅ Livré |
| **Bonus** | Network health gauge intégration Élu | 0.5j | ✅ Livré |

### Documentation cleanup

| Item | Avant | Après |
|------|-------|-------|
| Docs stale archivées | 13 docs racine/docs | `archive/{sprints,audits,misc}/` |
| Doublon tests `drift_detector.py` | 2 fichiers | Mergé → 1 fichier |
| `SECURITY.md` version | 0.1.x | **0.11.x** |
| `DASHBOARD_PAGES.md` | Section "mode démo" | Supprimée |
| `TODO.md` | Items ouverts non tracés | -213 lignes, marqués done |

## 📊 Métriques

| Métrique | Sprint 20 (avant) | Sprint 21 (après) |
|----------|-------------------|-------------------|
| **Tests verts** | 600 | **615** (+15) |
| **Widgets** | 53 | **~60** (+7 dont sparkline + quantile map) |
| **DAGs Airflow** | 13 | **15** (+record_network_health + DAG refresh) |
| **Fichiers Python** | ~170 | **~180** |
| **Lignes code** | ~22 000 | **~24 000** |
| **Couverture quantile** | ❌ | ✅ P10/P50/P90 sur carte trafic |
| **Sparkline 24h** | ❌ | ✅ Bandeau Élu santé réseau |

## 🏗️ Architecture

```
                    ┌─────────────────────────────────────┐
                    │     gold.trafic_predictions         │
                    │  (XGBoost H+1h, single model)      │
                    └──────────┬──────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
                ▼                             ▼
    ┌───────────────────────┐    ┌────────────────────────────┐
    │ trafic_predictions    │    │ trafic_predictions_quantile│ ← MIGRATION 029
    │ (single point)        │    │ (P10/P50/P90)              │
    └───────────────────────┘    └────────────────────────────┘
                                              │
                                              ▼
                          dashboard/components/widgets/pro_tcl/
                              trafic_quantile_map.py
                              (bande d'incertitude P10-P90)

    ┌────────────────────────┐    ┌──────────────────────────┐
    │ gold.fn_network_health │    │ mv_network_health_history│ ← MIGRATION 030
    │ _score()               │    │ (24h × 96 buckets 15min) │
    └──────────┬─────────────┘    └────────────┬─────────────┘
               │  every 15min                   │
               └──────────────┬─────────────────┘
                              ▼
              dashboard/components/sparkline.py
                              │
                              ▼
                  network_health_gauge.py (Élu)
```

## 🧪 Tests

- `tests/models/test_xgboost_quantile.py` — 12 tests (parametrize alpha=[0.1, 0.5, 0.9])
- `tests/dashboard/test_sparkline.py` — 7 tests (render + accessibility)
- `tests/dags/test_record_network_health.py` — 4 tests (insert + idempotence)
- `tests/data/test_quantile_loader.py` — 3 tests (fail loud si DB indispo)

**Total Sprint 21** : +15 tests verts.

## 📦 Commits significatifs

```
c5c7f1e feat(ops): DAG record_network_health (Sprint 21 P4.3 fin)
c67a90e feat(elu): sparkline 24h network health (Sprint 21 P4.3)
20232e0 feat(model): quantile regression XGBoost (Sprint 21 P4.2)
ee3541f docs: backup offsite config template (P3.3)
dfa27d1 feat: P4 — JWT cleanup + 3 templates HTML rapports
2f3c436 feat(ux): 7 Folium cartes avec a11y sr-only (Axe E fin)
481e841 feat(ux): Axe E accessibilité RGAA/WCAG 2.1 AA + v0.11.0
```

## 🎓 Apprentissages

1. **Quantile regression** : XGBoost supporte nativement les quantile losses (alpha=0.1, 0.5, 0.9). Plus simple que de bootstrap-er un modèle 100×. Tradeoff : moins robuste sur petites features.
2. **Sparkline Plotly** : 64px height + axe X masqué = composant minimal viable. Pas besoin de librarie tierce.
3. **mv_network_health_history** : 96 buckets × 15min = 24h. Matérialisée, refresh toutes les 15min par le DAG. Query = 1 SELECT, ~50ms.
4. **Docs cleanup** : déplacer (jamais supprimer) + créer `archive/README.md` qui documente la convention = gain clarté immédiat, traçabilité RNCP.

## 🚧 Points en suspens (vers Sprint 22+)

| Item | Statut | Action |
|------|--------|--------|
| rclone config offsite | 🔴 Pending user | `sudo bash scripts/rclone-setup.sh` (5 min, OAuth) |
| Prometheus absent | 🟡 Décision Sprint 15+ | À confirmer : re-add ou laisser ? |
| Axes 2/4/6/7 spec interdépendances | ⏸ À planifier | Voir `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` |
| TomTom Niveau 2 | ⏸ Optionnel | Backtest MAE XGBoost vs oracle |

## ✅ Verdict

**Sprint 21 livré à 100%**, prod stable, dette technique réduite (cleanup docs). Le projet est prêt pour la certif Jedha RNCP 38777 — 615 tests verts, 15 DAGs, 3 modèles ML, 8 collecteurs Bronze, 18 pages × 3 personas dashboard.

Sprint 22 = ops cleanup VPS (disk -40GB + systemd timer backup offsite) = suivi direct de ce sprint.
