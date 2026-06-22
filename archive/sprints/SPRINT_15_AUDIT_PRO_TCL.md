# Sprint 15 — Audit Pro TCL : Plan d'action

> Audit réalisé 2026-06-19. Persona Pro TCL : 7 pages, 24 widgets.
> Mise à jour 2026-06-19 : état réel après implémentation partielle.

---

## A. Bug structurel — Explosion lignes `_hNN` + point-virgule (CRITIQUE)

**Cause racine** : `gold.bus_delay_segments` stocke `line_ref` brut avec suffixe horaire SYTRAL (`ActIV:Line::66:SYTRAL_h20`). La vue `mv_line_kpis_live` fait un `GROUP BY line_ref` → chaque bucket horaire = une "ligne" distincte. `clean_line_label()` transforme en `L66 ; 20h` — d'où les point-virgules visibles.

**Impact** :
- Heatmap OTP : même ligne apparaît ~24 fois en Y (l'heure est déjà en X = double-encodage)
- KPI table : lignes dupliquées avec ` ; 16h`, ` ; 20h`...
- Dropdown sélecteur : pollué par N entrées par ligne physique
- Comparaison : compare les mêmes véhicules à des heures différentes

### TODO

- [x] **Modifier `scripts/sql/create_mv_line_kpis_otp.sql`** : `SPLIT_PART(line_ref, ':SYTRAL', 1) || ':SYTRAL'` retire le `_hNN`
- [x] **Même fix sur `mv_otp_heatmap`** : agréger au niveau ligne physique
- [x] **Migration `scripts/sql/migration_15_aggregate_line_ref.sql`** : script forward-only pour VPS
- [ ] **Appliquer sur VPS** : `psql -f scripts/sql/migration_15_aggregate_line_ref.sql`
- [ ] **Vérifier** que le format "L66" (sans ` ; XXh`) s'affiche correctement post-migration

---

## B. Identifiants bruts SYTRAL dans 5 widgets

`get_line_kpis()` calcule `line_label` via `clean_line_label()` depuis Sprint 11+. Mais 5 widgets utilisaient encore la clé brute.

### TODO

- [x] **`line_comparison.py:33`** — `k.get("line_label") or lid`
- [x] **`segment_table.py:62`** — `clean_line_label(s["line_id"])` + import
- [x] **`correlation_matrix.py:112`** — `clean_line_label(s["line_id"])` + import
- [x] **`network_map.py:79`** — `df["line_id"].apply(clean_line_label)` (tooltip + fallback)
- [x] **`saeiv_export.py`** — preview lisible + payload brut conservé

---

## C. Surinformation / Lisibilité

### C1. Double affichage `line_kpis.py` (dataframe + legacy cards)

- [x] **Bloc legacy supprimé** (-55 lignes) — tout passe par `st.dataframe` + mode détails dépliables

### C2. Heatmap OTP illisible (155+ lignes sur Y)

- [ ] **Ajouter slider "Top N lignes"** (défaut 20, max 50) dans `otp_heatmap.py`
- [ ] **Ajouter filtre par mode** (selectbox : Tous / Bus / Tram / Métro)
- [x] Fix A résout le gros du problème (~40 lignes physiques au lieu de ~155)

**Effort restant** : 15 min

### C3. Model Monitoring = scroll infini (790 lignes, 8 sections)

- [ ] **Convertir en `st.tabs()`** : 1 tab par section (MLflow, GNN carte, Drift, Métriques, Logs)

**Effort** : 20 min

### C4. Colorscale OTP mal alignée

- [x] **Breakpoints alignés** sur seuils SQL : `[0.0, 0.395, 0.789, 1.0]` → 75% = "bon", 90% = "excellent"

---

## D. Bugs logiques

### D1. Filtres OTP non connectés (mensonge UX)

`otp_filters.py` affiche `day_type` + `weather` dans l'UI de Pro_2. Mais les valeurs ne sont PAS passées à `cached_otp_heatmap_data()`. Filtres purement cosmétiques.

- [ ] **Option 1** (recommandé) : câbler les filtres → ajouter params `day_type`/`weather` à `get_otp_heatmap_data()` + filtrer en SQL
- [ ] **Option 2** : retirer les filtres de l'UI (si pas le temps)

**Effort** : 20 min (option 1) / 2 min (option 2)

### D2. Cause analysis = données d'exemple hardcodées

- [x] **Remplacé par** `st.info("Sélectionnez un segment pour voir l'analyse causale.")`

### D3. États en anglais dans segment_table

- [x] **Traduit** : `"En retard" / "À l'heure"` et `"Congestionné" / "Fluide"`

### D4. Code dupliqué `_bottlenecks_to_segments()`

Même logique (~30 lignes) dans `correlation_matrix.py` ET `segment_table.py`.

- [ ] **Extraire dans** `dashboard/components/widgets/pro_tcl/_helpers.py`
- [ ] Importer depuis les deux widgets

**Effort** : 10 min

---

## E. Code mort / Stubs / Tests

- [ ] **`export_button.py`** : `render_export_button()` = stub jamais utilisé. Supprimer ou implémenter.
- [ ] **`Pro_5_Export.py`** : export PDF = stub WeasyPrint. Documenter comme "futur Sprint" ou implémenter.
- [ ] **`test_pro_tcl_widgets.py:37`** : `test_pro_tcl_pages_exist` ne teste que Pro_1→Pro_5. Ajouter Pro_6 + Pro_7.

**Effort** : 15 min

---

## Résumé

| Prio | Item | Statut | Reste |
|------|------|--------|-------|
| 1 | A — Agrégation SQL `_hNN` | ✅ Code fait | Appliquer sur VPS |
| 2 | B — `clean_line_label` dans 5 widgets | ✅ Fait | — |
| 3 | C1 — Supprimer legacy cards | ✅ Fait | — |
| 4 | D3 — Traductions FR | ✅ Fait | — |
| 5 | C4 — Colorscale alignée | ✅ Fait | — |
| 6 | D2 — Retirer exemple hardcodé | ✅ Fait | — |
| 7 | C2 — Top-N heatmap | ❌ À faire | 15 min |
| 8 | D1 — Câbler ou retirer filtres OTP | ❌ À faire | 20 min |
| 9 | C3 — Tabs model_monitoring | ❌ À faire | 20 min |
| 10 | D4 — Extraire helper commun | ❌ À faire | 10 min |
| 11 | E — Stubs + tests | ❌ À faire | 15 min |

**Fait** : 6/11 items (A code, B, C1, C4, D2, D3). **Reste** : ~80 min pour 5 items restants.
**Tests** : 251 passed, 4 skipped, 0 régression. **Ruff** : clean sur fichiers modifiés.
