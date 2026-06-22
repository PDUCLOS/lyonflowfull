# Bugs Pro TCL — Audit VPS v0.6.6 (2026-06-19)

> Constaté sur `51.83.159.224` (v0.6.6). Classé par sévérité.
> Certains bugs seront résolus par le déploiement de v0.7.0 (commit `70678b0`).

---

## CRITIQUE — Bugs de calcul / données

### BUG-01 : `charge_pct` > 100% (valeurs aberrantes : 675%, 1800%, 3951%)

**Pages** : Pro_1_PCC_Live, Pro_2_Heatmap_OTP (tableau comparaison)
**Cause** : `create_mv_line_kpis_otp.sql:59` — formule `ROUND((SUM(n_observations) / COUNT(*)) * 100.0, 1)`. `n_observations` est un comptage de véhicules par snapshot (souvent > 1), divisé par le nombre de lignes puis ×100 → résultat dépasse 100%.
**Fix** : Revoir la formule. Options :
- `LEAST(SUM(n_observations) * 100.0 / NULLIF(MAX_expected, 0), 100.0)` (cap à 100)
- Ou ne pas multiplier par 100 si la métrique est déjà un ratio

### BUG-02 : 163 lignes dans KPI table (explosion `_hNN`)

**Pages** : Pro_1, Pro_2 (heatmap Y-axis)
**Cause** : MV `gold.mv_line_kpis_live` agrège par `line_ref` brut incluant suffixe horaire `_h20`, `_h13`, etc. Chaque heure crée une "ligne" séparée.
**Fix** : ✅ Code fait (migration 15 — `SPLIT_PART` dans `create_mv_line_kpis_otp.sql`). **Appliquer sur VPS** : `psql -f scripts/sql/migration_15_aggregate_line_ref.sql`

### BUG-03 : `build_spatial_mapping` DAG failed (15954s = 4.4h timeout)

**Page** : Pro_6_Pipeline_Mgmt
**Impact** : Pas de mise à jour de `dim_spatial_grid_mapping` + `dim_gnn_adjacency`
**Fix** : Investiguer le timeout — probablement query trop lourde ou deadlock

### BUG-04 : `maintenance_backfill_dim_spatial_lat_lon` bloqué "running" depuis 2026-06-12

**Page** : Pro_6_Pipeline_Mgmt
**Impact** : DAG fantôme monopolise un slot Airflow
**Fix** : Clear la task stuck via Airflow UI ou `airflow tasks clear`

### BUG-05 : `purge_bronze` DAG failed

**Page** : Pro_6_Pipeline_Mgmt
**Fix** : Vérifier logs Airflow pour la cause d'erreur

### BUG-06 : XGB H+60min DISPO = ❌ / GNN H+60min DISPO = ❌

**Page** : Pro_7_Model_Monitoring
**Impact** : Aucune prédiction H+1h disponible pour les 2 modèles. Carte trafic et recommandations dégradées.
**Fix** : Vérifier que `dag_inference_xgboost` et `dag_daily_speed_train` alimentent `gold.trafic_predictions`

### BUG-07 : "Aucune prédiction Vélo'v dans `gold.velov_predictions`"

**Page** : Pro_7_Model_Monitoring
**Impact** : Section Vélo'v entièrement vide
**Fix** : Lancer DAGs `retrain_velov` puis `predict_velov`

---

## MAJEUR — Rendu HTML cassé

### BUG-08 : HTML brut affiché dans Drift Detection (Pro_7)

**Page** : Pro_7_Model_Monitoring — section "Drift Detection"
**Visible** : `<div style="font-size:0.8rem;margin-top:0.4rem;color:var(--status-critical);">→ Drift dataset détecté` + `</div></div>` en texte brut
**Cause** : `model_monitoring.py:547-570` — le template HTML f-string utilise `unsafe_allow_html=True` mais le contenu injecté (`per_column_html`, `action_text`) contient probablement des caractères qui cassent le parsing HTML de Streamlit (ex: quotes non-échappées dans noms de colonnes, ou CSS variables non résolues).
**Fix** : Échapper les valeurs injectées avec `html.escape()` sur les données dynamiques, ou migrer vers `st.container()` + `st.write()` natifs

### BUG-09 : `</div>` affiché dans les health check cards (Pro_6)

**Page** : Pro_6_Pipeline_Mgmt — section "Santé Pipeline"
**Visible** : Tags `</div>` en texte brut dans les cards health check
**Cause** : `pipeline_management.py:239` — `{r.get("details", "")}` injecte du texte qui peut contenir `<` ou `>` (messages d'erreur PostgreSQL comme "to add explicit type casts") → casse le HTML template
**Fix** : `html.escape(r.get("details", ""))` avant injection dans le template

### BUG-10 : `**Action prioritaire :**` non rendu dans cause_analysis (Pro_3)

**Page** : Pro_3_Correlation — section "Analyse causale"
**Visible** : `**Action prioritaire :**` affiché en texte brut au lieu de gras
**Cause** : `cause_analysis.py:68-71` — markdown `**...**` injecté dans un template HTML (`unsafe_allow_html=True`). Markdown n'est PAS interprété dans un bloc HTML.
**Fix** : Remplacer `**texte**` par `<b>texte</b>` dans `recommendation`. Remplacer `\n- ` par `<br/>• `.

### BUG-11 : "to add explicit type casts" erreur PostgreSQL visible (Pro_6)

**Page** : Pro_6_Pipeline_Mgmt — health check cards
**Visible** : Message d'erreur PostgreSQL brut affiché à l'utilisateur
**Fix** : Attraper l'erreur et afficher un message utilisateur propre

---

## MODÉRÉ — Identifiants bruts / Labels

### BUG-12 : Identifiants SYTRAL bruts dans tableau comparaison (Pro_2)

**Page** : Pro_2_Heatmap_OTP — tableau de comparaison
**Visible** : `ActIV:Line::10E:SYTRAL`, `ActIV:Line::1EX:SYTRAL` au lieu de `L10E`, `L1EX`
**Fix** : ✅ Corrigé dans v0.7.0 (commit `70678b0`) — `clean_line_label()` appliqué dans 5 widgets. **Déployer v0.7.0.**

### BUG-13 : `L66 ; 20h` — point-virgules dans libellés bottlenecks (Pro_1)

**Page** : Pro_1_PCC_Live — section bottlenecks
**Visible** : `L66 ; 20h`, `L2080 ; 13h`
**Fix** : ✅ Corrigé par migration 15 (BUG-02). Après application SQL, `clean_line_label('ActIV:Line::66:SYTRAL')` → `L66` (sans heure)

### BUG-14 : États en anglais `delayed` / `jammed` dans correlation_matrix (Pro_3)

**Page** : Pro_3_Correlation — matrice + segment_table
**Visible** : "delayed", "jammed" au lieu de "En retard", "Congestionné"
**Fix** : ✅ Partiellement corrigé dans v0.7.0 (`segment_table.py` traduit). Reste `correlation_matrix.py` — statuts bus/trafic à traduire dans la matrice elle-même.

### BUG-15 : Drift = "None → None" (valeurs manquantes)

**Page** : Pro_7_Model_Monitoring — Drift Detection
**Visible** : `Réf: None → None · Current: None → None`
**Cause** : `model_monitoring.py:508-513` — `report.get("ref_from", "—")` retourne `None` (Python) quand la clé existe avec valeur `None`, au lieu du fallback `"—"`.
**Fix** : `report.get("ref_from") or "—"` (utiliser `or` au lieu de valeur par défaut)

### BUG-16 : `collect_tomtom_traffic` statut "unknown"

**Page** : Pro_6_Pipeline_Mgmt
**Visible** : Pastille grise "unknown", jamais exécuté (— / 0s)
**Cause** : Description dit "[DÉSACTIVÉ Sprint 8]" mais le Sprint 13+ l'a réactivé. La description est stale.
**Fix** : Mettre à jour la description DAG + configurer `TOMTOM_API_KEY` sur VPS

---

## MINEUR — UX / Cosmétique

### BUG-17 : 6 décimales dans tableau comparaison (Pro_2)

**Page** : Pro_2_Heatmap_OTP — tableau de comparaison
**Visible** : `86.500000` au lieu de `86.5`
**Fix** : Appliquer `.round(1)` ou `f"{val:.1f}"` sur les colonnes numériques du dataframe avant `st.dataframe()`

### BUG-18 : Colonne index (0, 1, 2...) visible dans tableau comparaison (Pro_2)

**Page** : Pro_2_Heatmap_OTP — tableau de comparaison
**Visible** : Colonne d'index numérique à gauche
**Fix** : `st.dataframe(df, hide_index=True)` ou `df.reset_index(drop=True)` + hide_index

### BUG-19 : "Vue cartes (legacy)" encore affichée (Pro_1)

**Page** : Pro_1_PCC_Live
**Fix** : ✅ Corrigé dans v0.7.0 (bloc legacy supprimé dans `line_kpis.py`). **Déployer.**

### BUG-20 : GNN retrain = OFF / paused

**Page** : Pro_7_Model_Monitoring
**Impact** : Normal si décision volontaire (GNN lourd). Documenter le statut.

### BUG-21 : Drift score 56.5% features drifteées — stale depuis 2026-06-06

**Page** : Pro_7_Model_Monitoring
**Impact** : Drift détecté il y a 13 jours, aucune action visible. Le drift monitoring ne tourne peut-être plus.
**Fix** : Relancer le DAG drift monitoring, investiguer la cause du drift

---

## ACTION — Page à supprimer

### BUG-22 : Pro_5_Export = page stub non fonctionnelle

**Page** : Pro_5_Export
**Visible** : Builder de rapport + bouton "Générer le rapport" qui ne produit rien (WeasyPrint stub)
**Fix** : **SUPPRIMER LA PAGE** du sidebar et de la navigation (décision utilisateur 2026-06-19)

---

## Résumé par priorité d'action

| Prio | Action | Bugs résolus |
|------|--------|--------------|
| 1 | **Déployer v0.7.0** sur VPS | BUG-12, 13, 14, 19 |
| 2 | **Appliquer migration 15** SQL | BUG-02, 13 |
| 3 | **Fix `charge_pct`** formule SQL | BUG-01 |
| 4 | **Fix HTML rendering** (escape + md→html) | BUG-08, 09, 10, 11 |
| 5 | **Fix `None` fallback** model_monitoring | BUG-15 |
| 6 | **Fix formatting** tableau OTP | BUG-17, 18 |
| 7 | **Clear DAGs stuck/failed** Airflow | BUG-03, 04, 05 |
| 8 | **Relancer modèles** (XGB, GNN, Vélov) | BUG-06, 07, 20, 21 |
| 9 | **Supprimer Pro_5_Export** | BUG-22 |
| 10 | **TomTom config** VPS | BUG-16 |
