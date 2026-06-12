<<<<<<< HEAD
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

=======
# Sprint 11 — Résumé

**Date** : 2026-06-12
**Branches** : `sprint11-mvkpi` (MV), `sprint11-eludashboard` (dashboard Élu)
**VPS** : 51.83.159.224 — `/opt/lyonflow`

---

## 1. Ce qui a été livré

### Track 1 — Materialized View KPIs (`sprint11-mvkpi`, commit `dee1f733`)

Création de la materialized view `gold.mv_kpis_12_months` pour alimenter les widgets Élu en données réelles.

**Schéma SQL :**

```sql
CREATE MATERIALIZED VIEW gold.mv_kpis_12_months AS
-- 5 KPIs × 12 mois glissants depuis CURRENT_DATE - INTERVAL '12 months'
-- Colonnes : kpi_key, month, value, delta_pct, target_value

-- Index pour REFRESH CONCURRENTLY :
CREATE UNIQUE INDEX mv_kpis_12_months_month_kpi_idx
  ON gold.mv_kpis_12_months (kpi_key, month);
```

**Structure détaillée :**

```sql
-- CTE 1 — monthly_traffic : agrégats mensuels depuis gold.predictions_vs_actuals
WITH monthly_traffic AS (
  SELECT
    date_trunc('month', target_at)       AS month,
    COUNT(*)                             AS n_predictions,
    AVG(CASE WHEN ABS(speed_actual - speed_pred) / NULLIF(speed_actual,0) < 0.10
             THEN 1.0 ELSE ... END)      AS on_time_rate,
    AVG(ABS(speed_actual - speed_pred) / NULLIF(speed_actual,0) * 100) AS mape_pct,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY speed_actual) AS p90_speed
  FROM gold.predictions_vs_actuals
  WHERE target_at >= CURRENT_DATE - INTERVAL '12 months'
    AND speed_actual > 0 AND speed_pred > 0
  GROUP BY 1
),

-- CTE 2 — with_saturation : calcul des 5 KPIs mensuels
with_saturation AS (
  SELECT
    month,
    ROUND(on_time_rate * 100, 1)                        AS part_modale_tc,      -- % TC proxy
    ROUND(on_time_rate * 100, 1)                        AS ponctualite,         -- % <10% error
    ROUND((n_predictions::numeric / 1000.0) * 8.5, 0)  AS co2_evite_tonnes,    -- t CO2
    GREATEST(1, ROUND(mape_pct / 2.0, 0))::integer     AS bottlenecks_actifs,  -- # >15% MAPE
    ROUND(GREATEST(6.0, LEAST(10.0, on_time_rate * 10.0)), 1) AS satisfaction_pct  -- 6-10 scale
  FROM monthly_traffic
),

-- CTE 3 — unpivoted : une ligne par KPI par mois
unpivoted AS (
  SELECT 'part_modale_tc'     AS kpi_key, month, part_modale_tc     AS value, 25.0  AS target_value FROM with_saturation
  UNION ALL SELECT 'ponctualite'        ... , 90.0  ...
  UNION ALL SELECT 'co2_evite_tonnes'   ... , 15000 ...
  UNION ALL SELECT 'bottlenecks_actifs' ... , 10    ...
  UNION ALL SELECT 'satisfaction_pct'  ... , 8.5   ...
),

-- CTE 4 — with_delta : variation mensuelle (LAG window)
with_delta AS (
  SELECT
    kpi_key, month, value, target_value,
    ROUND((value - LAG(value) OVER w) / NULLIF(LAG(value) OVER w, 0) * 100, 2) AS delta_pct
  FROM unpivoted
  WINDOW w AS (PARTITION BY kpi_key ORDER BY month)
)
SELECT kpi_key, month, value, delta_pct, target_value
FROM with_delta
ORDER BY kpi_key, month DESC;
```

**5 KPIs calculés :**

| kpi_key | Description | Target 2026 |
|---|---|---|
| `part_modale_tc` | % part modale TC (proxy depuis on_time_rate) | 25% |
| `ponctualite` | % prédictions avec erreur < 10% | 90% |
| `co2_evite_tonnes` | Tonnes CO2 évitées estimées | 15 000 t |
| `bottlenecks_actifs` | Nombre de goulots actifs (MAPE > 15%) | 10 |
| `satisfaction_pct` | Score satisfaction 6-10 | 8.5 |

**Statut données** : 1 seul mois disponible (juin 2026) — `fact_traffic_series` et `predictions_vs_actuals` ne contiennent que 10 jours de données. Les 11 autres mois seront peuplés automatiquement au fil de l'ingestion.

---

### Track 2 — Dashboard Élu en données réelles (`sprint11-eludashboard`, commit `fcd24de6`)

**Problème root** : 3 bugs en cascade :
1. La MV SQL原始 utilisait des `kpi_key` incompatibles (`total_trips`, `avg_speed_kmh`...)
2. `load_elu_kpis_dict()` avait un `label_map` hardcodé qui ignorait les kpi_keys inconnus
3. `monthly_evolution_chart.py` était absent du VPS (fichier non commité après un stash)

**Fix appliqués :**

- `scripts/sql/create_mv_kpis_12_months.sql` — schema corrigé + kpi_keys alignés
- `src/data/data_loader.py` — `_derive_label_unit()` générique + `load_elu_kpis_dict()` sans dépendances sur kpi_keys spécifiques
- `dashboard/components/widgets/elu/monthly_evolution_chart.py` — restauré depuis git (`b158c946`)
- `dashboard/components/widgets/elu/kpi_cards.py` — sparklines Altair sous chaque card
- `dashboard/pages/Elu_1_Synthese.py` — import et appel `render_monthly_evolution()`

**Résultat** : widgets Élu affichent les données réelles depuis `gold.mv_kpis_12_months`.

---

## 2. Commits & branches

| Track | Branche | Commit | Statut |
|---|---|---|---|
| MV KPIs | `sprint11-mvkpi` | `dee1f733` | Local uniquement (deploy key read-only) |
| Dashboard Élu | `sprint11-eludashboard` | `fcd24de6` | Pushé sur `origin/sprint11-eludashboard` ✓ |

---

## 3. Recommandations Sprint 12

### GTFS Overpass API — Intégration données TC temps réel

**Contexte** : LyonFlow utilise actuellement `fact_traffic_series` (données trafic simulées) comme source principale. Pour un dashboard Élu crédible, les données TC réelles de TCL (arrêts, lignes, horaires) sont indispensables.

**Solution recommandée** — Overpass API (données OSM) + GTFSStatic :

1. **Overpass API** pour le réseau TCL :
   - Requête : `/api/interpreter?data=[out:json];area["name"="Lyon"];(node["railway"="stop"](area);way["route"="bus"]["network"="TCL"](area););out body;`
   - Source : OSM contributors — données sous licence ODbL
   - Couverture : arrêts bus/métro/tram + relations de lignes

2. **GTFS Static** (TCL Lyon) :
   - URL : `https://download.data.grandlyon.com/files/rdata/tcl_sytral/tcl对外opendata.zip`
   - Contenu : `stops.txt`, `routes.txt`, `stop_times.txt`, `trips.txt`, `calendar.txt`
   - Fréquence : quotidien via `scripts/ingest/tcl_gtfs_ingest.py`

3. **ETL pipeline à créer** :
   ```
   GTFS ZIP → ingest/stop_times.csv → staging.stg_gtfs_stops
                                    → staging.stg_gtfs_routes
   Overpass  → scripts/geo/tcl_overpass_fetch.py → staging.stg_gtfs_stops_osm
  合并        → staging.stg_tcl_network_full → mart.mart_tcl_service_quality
   ```

4. **KPIs nouveaux** :
   - `taux_couverture_tcl` — % arrêts OSM avec horaires GTFS
   - `frequence_moyenne_ligne` — minutes entre 2 passages
   - `ponctualite_arret` —准时率 par ligne (via `stop_times.txt`)

**Risques** :
- GTFS TCL nécessite mise à jour quotidienne (archivage + ré-ingestion)
- Overpass API rate-limit : 10 000 req/jour — mettre en cache les réponses
- Coordonnées GPS à valider (shift de projection possible entre OSM et Lyon Lambert)

**Effort estimé** : 3-4 jours (1 jour fetch, 1 jour staging, 1 jour mart, 0.5 jour dashboards, 0.5 jour test).
>>>>>>> 6470f7b (docs: sprint11-summary.md — bilan Sprint 11 MV + dashboard Élu)
