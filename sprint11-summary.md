# Sprint 11 — mv_kpis_12_months + Dashboard Élu câblé

**Date** : 2026-06-12
**Branches** : `sprint11-mvkpi` / `sprint11-eludashboard`
**VPS** : `51.83.159.224`

---

## Livrable 1 : `gold.mv_kpis_12_months`

### Problème résolu
Le dashboard Élu utilisait des mocks pour les KPIs 12 mois. La chaîne `cached_elu_kpis_dict() → get_kpis_12_months() → db_query.py` attendait un schéma avec `kpi_key, month, value, delta_pct, target_value`, mais la MV initiale avait `channel_id, total_trips, avg_speed_kmh, ...`.

### Schéma SQL final

```sql
CREATE MATERIALIZED VIEW gold.mv_kpis_12_months AS
-- Colonnes : kpi_key, month, value, delta_pct, target_value
-- 4 KPIs : total_trips, avg_speed_kmh, prediction_accuracy, congestion_index
-- 2 mois de données (mai-juin 2026)
-- delta_pct : variation month-over-month
-- target_value : cibles ville (500k trips, 25 km/h, 10% accuracy, 2.0 congestion)
CREATE UNIQUE INDEX ON gold.mv_kpis_12_months (kpi_key, month);
```

### Données réelles

| kpi_key | month | value | delta_pct | target |
|---------|-------|-------|-----------|--------|
| total_trips | 2026-06 | 385 791 | +158% | 500 000 |
| avg_speed_kmh | 2026-06 | 24.16 | -2.34% | 25.0 |
| prediction_accuracy | 2026-06 | 16.47% | +4.28% | 10.0 |
| congestion_index | 2026-06 | 6.0 | 0% | 2.0 |

### Commits
- `dee1f733` — première version (schéma channel_id)
- `6154ae59` — deuxième version
- `7343bb6` — schéma corrigé pour db_query.py (kpi_key/month/value)

---

## Livrable 2 : Dashboard Élu avec sparklines + évolution mensuelle

### Fichiers modifiés
- `dashboard/components/widgets/elu/kpi_cards.py` — sparklines Altair 12 mois sous chaque card
- `dashboard/components/widgets/elu/monthly_evolution_chart.py` (163 lignes) — tabs par KPI + vue agrégée
- `dashboard/pages/Elu_1_Synthese.py` — câblage render_monthly_evolution()
- `dashboard/components/widgets/elu/__init__.py` — export render_monthly_evolution

### Architecture
- `cached_elu_kpis_dict()` → `get_kpis_12_months()` → `gold.mv_kpis_12_months`
- Fallback mock via `_is_demo_mode()` si MV vide (pas encore en prod après un deploy)
- Pas de dépendance directe sur la branche sprint11-mvkpi (MV existe déjà sur toutes les branches)

### Commit
- `b158c946` — sparklines + monthly evolution charts

---

## Bugs détectés et corrigés

| Bug | Impact | Fix |
|-----|--------|-----|
| Schema MV incohérent avec db_query.py | Dashboard cassé | Reschema MV (kpi_key/month/value/delta_pct/target_value) |
| Selecteurs e2e obsolètes (sprint10 sidebar refactor) | 4 tests cassés | Mise à jour vers text links |
| AF_INET typo dans conftest.py | Tests ne marchaient pas | Fix typo |

---

## Tests e2e API : 7/7 PASS

Exécutés depuis le container API :
```
docker compose exec -T api python -m pytest tests/e2e/test_api_health.py tests/e2e/test_api_itinerary_endpoint.py -v
```

Les tests playwright (Streamlit) nécessitent chromium dans le container.

---

## Recommandations Sprint 12

1. **GTFS Overpass API** — remplacer le graphe H3 sparse par un vrai graphe OSM
2. **DAG quotidien** — refresh du graphe routier
3. **Tests e2e Streamlit** — installer chromium dans le container avant de les exécuter

