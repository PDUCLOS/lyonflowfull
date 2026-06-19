# TODO — Corrections Pro TCL (2026-06-19)

> Dérivé de l'audit VPS v0.6.6. Ordonné par impact.

---

## 1. Déployer v0.7.0 sur VPS

- [ ] `make deploy-vps` (commit `70678b0`)
- [ ] Vérifier sidebar : `v0.7.0` affiché

> Résout : identifiants SYTRAL bruts (5 widgets), legacy cards, traductions FR segment_table

---

## 2. Appliquer migration 15 SQL

- [ ] `psql -f scripts/sql/migration_15_aggregate_line_ref.sql`
- [ ] Vérifier : `SELECT COUNT(*) FROM gold.mv_line_kpis_live;` → ~40 (pas 163)
- [ ] Vérifier : plus de `_hNN` dans `line_ref`

> Résout : explosion 163 lignes, point-virgules `L66 ; 20h`

---

## 3. Fix `charge_pct` > 100% (formule SQL)

**Fichier** : `scripts/sql/create_mv_line_kpis_otp.sql:59`

Formule actuelle cassée :
```sql
ROUND((SUM(n_observations)::numeric / NULLIF(COUNT(*), 0)) * 100.0, 1)
```

- [ ] Corriger la formule (cap à 100 ou revoir le dénominateur)
- [ ] Recréer la MV
- [ ] Vérifier : aucune valeur > 100%

---

## 4. Fix HTML brut dans 3 widgets

### 4a. `model_monitoring.py` — Drift Detection (lignes 508-570)

- [ ] Ligne 508-513 : `report.get("ref_from") or "—"` (fix `None` affiché)
- [ ] Ligne 529 : `html.escape(col)` pour noms de colonnes
- [ ] Ligne 536-544 : vérifier que `action_text` HTML ne casse pas le template parent
- [ ] Ajouter `import html` en haut du fichier

### 4b. `pipeline_management.py` — Health check cards (ligne 239)

- [ ] `html.escape(str(r.get("details", "")))` avant injection
- [ ] Supprime le leak `</div>` + message PostgreSQL brut

### 4c. `cause_analysis.py` — Markdown dans HTML (lignes 28-51)

- [ ] Remplacer `**Action prioritaire :**` → `<b>Action prioritaire :</b>`
- [ ] Remplacer `\n- ` → `<br/>• ` dans les recommandations
- [ ] Tester rendu des 3 cas (infra, operations, bus_lane_ok)

---

## 5. Fix tableau comparaison OTP (Pro_2)

**Fichier** : `dashboard/pages/Pro_2_Heatmap_OTP.py` (ou widget qui rend le tableau)

- [ ] Arrondir colonnes numériques à 1 décimale (`.round(1)`)
- [ ] Masquer index : `st.dataframe(df, hide_index=True)`

---

## 6. Supprimer Pro_5_Export

- [ ] Supprimer `dashboard/pages/Pro_5_Export.py`
- [ ] Supprimer `dashboard/components/widgets/pro_tcl/saeiv_export.py`
- [ ] Supprimer `dashboard/components/widgets/pro_tcl/export_button.py`
- [ ] Retirer des imports dans `dashboard/components/widgets/pro_tcl/__init__.py`
- [ ] Retirer des tests dans `tests/persona/test_pro_tcl_widgets.py`

---

## 7. Clear DAGs Airflow bloqués/failed

- [ ] `maintenance_backfill_dim_spatial_lat_lon` : clear task stuck (running depuis 7 jours)
- [ ] `purge_bronze` : investiguer échec, relancer
- [ ] `build_spatial_mapping` : investiguer timeout 4.4h, optimiser query
- [ ] `collect_tomtom_traffic` : configurer `TOMTOM_API_KEY` ou mettre à jour description

---

## 8. Relancer modèles ML

- [ ] Vérifier `dag_inference_xgboost` alimente `gold.trafic_predictions`
- [ ] Lancer `retrain_velov` + `predict_velov`
- [ ] Investiguer drift 56.5% stale depuis 2026-06-06
- [ ] Décider GNN : relancer ou documenter comme "paused volontairement"

---

## 9. Traductions restantes

- [ ] `correlation_matrix.py` : traduire statuts `delayed`→`En retard`, `jammed`→`Congestionné` dans la matrice (pas seulement segment_table)

---

## Résumé

| # | Tâche | Effort | Bugs résolus |
|---|-------|--------|-------------|
| 1 | Deploy v0.7.0 | 5 min | 4 bugs |
| 2 | Migration 15 SQL | 2 min | 2 bugs |
| 3 | Fix charge_pct | 15 min | 1 bug critique |
| 4 | Fix HTML rendering | 20 min | 4 bugs |
| 5 | Fix tableau OTP | 10 min | 2 bugs |
| 6 | Supprimer Pro_5 | 10 min | 1 bug |
| 7 | Clear DAGs | 15 min | 4 bugs |
| 8 | Relancer modèles | 20 min | 4 bugs |
| 9 | Traductions | 5 min | 1 bug |
| | **Total** | **~100 min** | **22 bugs** |
