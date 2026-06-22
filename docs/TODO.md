# TODO — LyonFlowFull

> **Date** : 2026-06-22 · **Branche** : `vps` · **615 tests verts, ruff clean** · **v0.11.0**

---

## P1 — Quick wins ~~(2h)~~ ✅ DONE

### ~~P1.1 Axe A finition : 10 widgets DB sans loading_wrapper~~ ✅

32/32 widgets DB-hitting wrappés `loading_wrapper()`. Les 18 restants sont UI-pure (pas de DB call).

### ~~P1.2 Axe D finition : 14 st.error bruts → show_error()~~ ✅

16 widgets migrés vers `show_error()`. Pattern uniforme dans tout le dashboard.

---

## P2 — Moyen effort (1.5j, amélioration visible)

### P2.1 Axe C : Pro_3 en tabs (~0.5j)

**Quoi** : Pro_3_Correlation.py = 33 renders linéaires. Restructurer en tabs pour navigation.

**Structure cible** :
```python
render_line_selector()  # Toujours visible

tab1, tab2, tab3, tab4 = st.tabs([
    "Bus × Trafic",     # correlation_matrix + segment_table + cause_analysis
    "Spatial & TomTom",  # bus_traffic_spatial + coherence_scatter
    "Multimodal",        # multimodal_heatmap + meteo_impact + modal_shift_alert
    "Propagation",       # propagation_map
])
```

**Risque** : moyen. Les `deferred_render` session_state keys doivent rester uniques. **Tester visuellement.**

### P2.2 Elu_1 + Usager_1 sections collapsibles (~0.5j)

3 badges bandeau + executive_summary + kpi_cards → toujours visibles. Widgets lourds (carte, trend, PDF) → `st.expander(expanded=False)`. Net gain RAM ~20%.

### ~~P2.3 Axe F : 5 tooltips aide~~ ✅

5 `st.popover()` ajoutés (Granger, z-score, PSI, MAE/MAPE, TomTom vs GL).

### P2.4 VPS : index pgRouting (~15min SSH)

Cold start routing 10-21s. Index recommandé :
```sql
CREATE INDEX IF NOT EXISTS idx_ways_source_target ON osm.ways (source, target)
    WHERE cost > 0;
```
**Décision** : si cold start > 15s en usage réel → ajouter. Sinon skip (cache Streamlit 30s suffit).

---

## P3 — Gros effort (2j, valeur portfolio RNCP)

### ~~P3.1 Axe E : Accessibilité RGAA/WCAG 2.1 AA~~ ✅

`a11y.py` livré : `plotly_with_alt()`, `sr_only()`, 18 alt texts. CSS `.sr-only`, skip link, `lang="fr"`.

### P3.2 Tests Sprint 16 : vérifier couverture (~30min)

`tests/persona/test_source_health.py` + `tests/persona/test_dq_badge.py` existent et couvrent les cas. Pas de doublon `tests/monitoring/` nécessaire.

~~Sprint 21 cleanup : `tests/ml/test_drift_detector.py` mergé dans `tests/monitoring/test_drift_detector.py`.~~

### ~~P3.3 Backup offsite~~ ✅

`scripts/backup-template.sh` livré (pg_dump structuré). Config `OFFSITE_HOST` à faire sur VPS.

---

## P4 — Backlog (pas urgent)

### TODOs dans le code

| TODO | Fichier:ligne | Effort | Statut |
|------|--------------|--------|--------|
| JWT auth API | `src/api/main.py:580` | 2h | ⏸ Avant d'exposer l'API publiquement |
| ~~Quantile regression XGBoost~~ | ~~`src/models/xgboost_speed.py:328`~~ | ~~1j~~ | ✅ `XGBoostQuantileModel` P10/P50/P90, migration 029 |
| Batcher Vélov smart lookup | `src/routing/pathfinder_multimodal.py:373` | 2h | ⏸ Si perf Vélov problème |
| ~~Sparkline 24h gauge~~ | ~~`elu/network_health_gauge.py:252`~~ | ~~0.5j~~ | ✅ `sparkline.py` + migration 030 |
| 3 templates HTML rapport | `elu/template_selector.py:13,17,21` | 1j | ⏸ Quand l'Élu en a besoin |
| Modifier schéma bronze→silver | `src/transformation/bronze_to_silver.py:144` | 0.5j | ⏸ Prochaine migration |

### Infra

| Item | Contexte | Action |
|------|----------|--------|
| DNS `lyonflowfull.fr` | NXDOMAIN | Renouveler chez registrar ou abandonner (accès IP suffit RNCP) |
| Cert TLS Let's Encrypt | Expiré (DNS mort) | Si DNS renouvelé → `certbot renew`. Sinon self-signed |
| Axe 2 propagation UI | Code livré Sprint 17 | Ajouter `propagation_map` à page Élu si demandé |
| Axe 4 report modal UI | Code livré Sprint 17 | Ajouter `modal_shift_alert` à page Élu si demandé |

---

## Arbre de décision rapide

```
Tu as 2h ?
  → P2.1 tabs Pro_3 (le plus visible UX restant)

Tu as 1 jour ?
  → P2.1 tabs + P2.2 sections collapsibles + P2.4 index pgRouting

Tu as 2-3 jours ?
  → P2 complet + P3.2 couverture tests Sprint 16

Tu veux juste closer ?
  → Tag v0.11.0. Deploy VPS. Reste = Sprint 22.
```
