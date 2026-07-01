# SPEC Sprint 16 — Validation modèle + Qualité données + Durées réelles

> **Date** : 2026-06-20  
> **Version cible** : v0.8.0  
> **Branche** : `vps`  
> **Prérequis** : Sprint 15+ (v0.7.1) déployé  
> **Effort estimé** : ~3 jours (A: 1.5j, B: 1j, C: 0.5j)

---

## Table des matières

1. [Axe A — TomTom Niveau 2 : Backtest Engine](#axe-a--tomtom-niveau-2--backtest-engine)
2. [Axe B — Qualité données : Monitoring multi-source](#axe-b--qualité-données--monitoring-multi-source)
3. [Axe C — Durées réelles dans le comparateur](#axe-c--durées-réelles-dans-le-comparateur)
4. [Widgets — Inventaire complet](#widgets--inventaire-complet)
5. [Migrations SQL](#migrations-sql)
6. [DAGs Airflow](#dags-airflow)
7. [Tests](#tests)
8. [Plan d'implémentation](#plan-dimplémentation)

---

## Axe A — TomTom Niveau 2 : Backtest Engine

### Objectif

Valider la qualité des prédictions XGBoost H+1h en les comparant à une **source indépendante** (TomTom Traffic Flow = GPS flottes de véhicules). Boucle MLOps complète : train → deploy → infer → **validate vs oracle externe**.

### Existant

| Composant | État | Fichier |
|-----------|------|---------|
| `bronze.tomtom_traffic` | ✅ Ingestion active */15 min | `src/ingestion/tomtom.py` |
| `gold.v_coherence_tomtom_vs_grandlyon` | ✅ Sprint 13+ | `scripts/sql/migration_14_gold_coherence_tomtom_v2.sql` |
| `gold.v_tomtom_gl_drift` | ✅ Sprint 13+ (capteurs HS) | idem |
| `gold.predictions_vs_actuals` | ⚠️ Existe mais sans TomTom | `src/data/db_query.py:295` |
| `check_drift_evidently()` | ⚠️ Placeholder (count only) | `src/monitoring/health_checks.py:165` |
| Widget `coherence_scatter` | ✅ Sprint 13+ (TomTom vs GL) | `dashboard/components/widgets/pro_tcl/coherence_scatter.py` |

### Ce qui manque

#### A.1. Vue SQL `gold.mv_xgb_vs_tomtom` (migration 020)

Vue matérialisée qui croise les **prédictions XGBoost** avec les **observations TomTom** sur la même zone/heure.

```sql
-- Migration 020 : cross-validation XGBoost predictions vs TomTom oracle
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_xgb_vs_tomtom AS
WITH pred AS (
    -- Prédictions XGBoost H+1h les plus récentes par axis_key
    SELECT
        axis_key,
        calculated_at,
        speed_pred,
        etat_pred,
        lat,
        lon,
        model_version
    FROM gold.trafic_predictions
    WHERE horizon_h = 1
      AND calculated_at > NOW() - INTERVAL '7 days'
),
tomtom AS (
    -- Observations TomTom par tuile (speed_kmh = vitesse mesurée GPS)
    SELECT
        tile_key,
        fetched_at,
        speed_kmh AS tomtom_speed_kmh,
        free_flow_speed_kmh,
        confidence,
        lat_center,
        lon_center
    FROM gold.v_tomtom_traffic_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
)
SELECT
    p.axis_key,
    p.calculated_at,
    p.speed_pred   AS xgb_speed_kmh,
    t.tomtom_speed_kmh,
    t.free_flow_speed_kmh,
    ABS(p.speed_pred - t.tomtom_speed_kmh)    AS error_abs_kmh,
    CASE
        WHEN t.tomtom_speed_kmh > 0
        THEN ABS(p.speed_pred - t.tomtom_speed_kmh) / t.tomtom_speed_kmh * 100
        ELSE NULL
    END AS error_pct,
    t.confidence AS tomtom_confidence,
    p.model_version,
    p.etat_pred,
    p.lat AS pred_lat,
    p.lon AS pred_lon,
    t.tile_key,
    t.fetched_at AS tomtom_fetched_at,
    -- Diagnostic
    CASE
        WHEN ABS(p.speed_pred - t.tomtom_speed_kmh) < 5  THEN 'accurate'
        WHEN ABS(p.speed_pred - t.tomtom_speed_kmh) < 15 THEN 'acceptable'
        ELSE 'poor'
    END AS accuracy_band
FROM pred p
JOIN tomtom t
  ON ST_DWithin(
       ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
       ST_SetSRID(ST_MakePoint(t.lon_center, t.lat_center), 4326)::geography,
       200  -- 200 m (même seuil que cohérence Sprint 13+)
     )
  AND t.fetched_at BETWEEN p.calculated_at - INTERVAL '10 minutes'
                        AND p.calculated_at + INTERVAL '10 minutes'
WITH DATA;

-- Index pour les requêtes dashboard
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_calculated
    ON gold.mv_xgb_vs_tomtom (calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mv_xgb_vs_tomtom_accuracy
    ON gold.mv_xgb_vs_tomtom (accuracy_band);
```

**Refresh** : toutes les 30 min (aligné sur le cycle d'inférence XGBoost).

#### A.2. Vue SQL `gold.v_xgb_accuracy_summary` (migration 020)

Vue simple (pas matérialisée) pour les KPIs agrégés.

```sql
CREATE OR REPLACE VIEW gold.v_xgb_accuracy_summary AS
SELECT
    date_trunc('hour', calculated_at) AS hour_bucket,
    COUNT(*)                          AS n_pairs,
    AVG(error_abs_kmh)                AS mae_kmh,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY error_abs_kmh) AS median_error_kmh,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY error_abs_kmh) AS p90_error_kmh,
    AVG(error_pct) FILTER (WHERE error_pct IS NOT NULL) AS mape_pct,
    COUNT(*) FILTER (WHERE accuracy_band = 'accurate')   AS n_accurate,
    COUNT(*) FILTER (WHERE accuracy_band = 'acceptable') AS n_acceptable,
    COUNT(*) FILTER (WHERE accuracy_band = 'poor')       AS n_poor,
    AVG(tomtom_confidence) AS avg_tomtom_confidence
FROM gold.mv_xgb_vs_tomtom
GROUP BY 1
ORDER BY 1 DESC;
```

#### A.3. Fonction `get_xgb_vs_tomtom()` + `get_xgb_accuracy_summary()`

Fichier : `src/data/db_query.py`

```python
def get_xgb_vs_tomtom(hours: int = 24, limit: int = 500) -> pd.DataFrame:
    """Paires (prédiction XGBoost, observation TomTom) des dernières N heures."""
    query = """
        SELECT axis_key, calculated_at, xgb_speed_kmh, tomtom_speed_kmh,
               error_abs_kmh, error_pct, accuracy_band,
               tomtom_confidence, model_version, etat_pred
        FROM gold.mv_xgb_vs_tomtom
        WHERE calculated_at > NOW() - INTERVAL '%s hours'
        ORDER BY calculated_at DESC
        LIMIT %s
    """
    return _df_from_query(query, (hours, limit))


def get_xgb_accuracy_summary(hours: int = 168) -> pd.DataFrame:
    """KPIs agrégés par heure (MAE, MAPE, P90, distribution accuracy)."""
    query = """
        SELECT hour_bucket, n_pairs, mae_kmh, median_error_kmh,
               p90_error_kmh, mape_pct, n_accurate, n_acceptable, n_poor,
               avg_tomtom_confidence
        FROM gold.v_xgb_accuracy_summary
        WHERE hour_bucket > NOW() - INTERVAL '%s hours'
        ORDER BY hour_bucket DESC
    """
    return _df_from_query(query, (hours,))
```

#### A.4. Drift detection Evidently (remplace le placeholder)

Fichier : `src/monitoring/drift_detector.py` (nouveau)

```python
"""Drift detector — compare distribution XGBoost vs TomTom via Evidently.

Utilise Evidently DataDriftPreset pour détecter si la distribution des
erreurs XGBoost a changé (shift dans accuracy_band, MAE drift).

Appelé par le DAG daily à 05h30 (après le refresh de mv_xgb_vs_tomtom).
Résultat stocké dans gold.model_drift_reports (table existante).
"""

from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report


def run_drift_report(
    reference_df: pd.DataFrame,  # J-7 → J-1
    current_df: pd.DataFrame,    # dernières 24h
) -> dict:
    """Compare reference vs current, retourne le résultat Evidently.

    Colonnes attendues : xgb_speed_kmh, tomtom_speed_kmh, error_abs_kmh,
    error_pct, tomtom_confidence.

    Returns:
        {"dataset_drift": bool, "n_drifted_features": int,
         "share_drifted_features": float, "details": dict}
    """
    column_mapping = ColumnMapping(
        numerical_features=[
            "xgb_speed_kmh", "tomtom_speed_kmh",
            "error_abs_kmh", "error_pct", "tomtom_confidence",
        ],
    )

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference_df, current_data=current_df,
               column_mapping=column_mapping)

    result = report.as_dict()
    drift_info = result.get("metrics", [{}])[0].get("result", {})

    return {
        "dataset_drift": drift_info.get("dataset_drift", False),
        "n_drifted_features": drift_info.get("number_of_drifted_columns", 0),
        "share_drifted_features": drift_info.get("share_of_drifted_columns", 0.0),
        "details": drift_info,
    }
```

#### A.5. Widget `backtest_dashboard` (Pro TCL — Model Monitoring)

Page cible : `Pro_7_Model_Monitoring.py`  
Fichier : `dashboard/components/widgets/pro_tcl/backtest_dashboard.py`

**Contenu** :

1. **4 KPI cards** (bandeau horizontal) :
   - MAE (km/h) — dernières 24h
   - MAPE (%) — dernières 24h
   - P90 erreur (km/h) — seuil d'alerte
   - Paires validées (n) — volume de cross-validation

2. **Scatter plot XGBoost vs TomTom** (Plotly) :
   - X = `tomtom_speed_kmh` (oracle)
   - Y = `xgb_speed_kmh` (prédiction)
   - Ligne y=x (prédiction parfaite)
   - Couleur par `accuracy_band` (vert/orange/rouge)
   - Hover : axis_key, delta, confidence TomTom

3. **Courbe MAE temporelle** (Plotly line) :
   - X = `hour_bucket` (7 derniers jours)
   - Y = `mae_kmh`
   - Bande grisée = seuil acceptable (< 10 km/h)
   - Indicateur drift Evidently (pastille rouge si drift détecté)

4. **Distribution accuracy_band** (Plotly pie ou bar) :
   - 3 segments : accurate / acceptable / poor
   - Target : > 60% accurate, < 10% poor

5. **Table top 10 pires prédictions** :
   - Trié par `error_abs_kmh` DESC
   - Colonnes : axis_key, XGB, TomTom, delta, heure, confidence

**Renderers** : Plotly (3 charts) + st.markdown (KPIs) + st.dataframe (table)  
**Coût estimé** : 🟠 Lourd (1 MV + 1 vue + 3 Plotly)  
**Recommandation** : button-gate via `deferred_render()` (déjà implémenté Sprint 15+)

#### A.6. Widget `drift_status_badge` (Élu — Synthèse)

Page cible : `Elu_1_Synthese.py` (en bandeau, à côté de `network_health_gauge`)  
Fichier : `dashboard/components/widgets/elu/drift_status_badge.py`

**Contenu** : badge simple (1 ligne HTML) :
- 🟢 **Modèle stable** — MAE 7.2 km/h, 0 drift détecté
- 🟡 **Attention** — MAE 12.4 km/h, 1 feature en drift
- 🔴 **Drift détecté** — MAE 18.1 km/h, retrain recommandé

**Renderer** : st.markdown HTML (léger)  
**Coût estimé** : 🟢 Léger (1 requête scalaire)

---

## Axe B — Qualité données : Monitoring multi-source

### Objectif

Passer du monitoring basique actuel (6 checks quotidiens, mono-table) à un **monitoring par source** temps réel, avec score de qualité et alertes. Port de la logique LyonTraffic `data_quality.py` adaptée au pipeline LyonFlow.

### Existant

| Composant | État | Limitation |
|-----------|------|-----------|
| `check_bronze_freshness()` | ✅ | Mono-table (`trafic_boucles` seulement) |
| `check_bronze_volume()` | ✅ | Seuil global 1000 records, pas par source |
| `check_silver_nulls()` | ✅ | Mono-table (`trafic_boucles_clean`) |
| `check_silver_doublons()` | ✅ | Mono-table |
| `check_predictions_presentes()` | ✅ | Count seulement, pas de MAE |
| `check_drift_evidently()` | ⚠️ Placeholder | Count `model_drift_reports` |
| DAG `data_quality_daily` | ✅ 04h15 | 6 checks, pas granulaire |

### Ce qui manque

#### B.1. Vue SQL `gold.v_source_health` (migration 021)

Score de santé **par source** (8 sources Bronze + 5 tables Silver + 3 Gold).

```sql
CREATE OR REPLACE VIEW gold.v_source_health AS
WITH source_status AS (
    -- Bronze : fraîcheur par table
    SELECT 'bronze.trafic_boucles' AS source,
           MAX(fetched_at) AS last_update,
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60 AS age_minutes,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour') AS records_1h,
           5 AS expected_interval_min  -- toutes les 5 min
    FROM bronze.trafic_boucles

    UNION ALL
    SELECT 'bronze.velov', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           5
    FROM bronze.velov

    UNION ALL
    SELECT 'bronze.tcl_vehicles', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           5
    FROM bronze.tcl_vehicles

    UNION ALL
    SELECT 'bronze.meteo', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           60
    FROM bronze.meteo

    UNION ALL
    SELECT 'bronze.air_quality', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 day'),
           60
    FROM bronze.air_quality

    UNION ALL
    SELECT 'bronze.chantiers', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 day'),
           1440  -- 1x/jour
    FROM bronze.chantiers

    UNION ALL
    SELECT 'bronze.tomtom_traffic', MAX(fetched_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60,
           COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '1 hour'),
           15
    FROM bronze.tomtom_traffic

    UNION ALL
    SELECT 'gold.trafic_predictions', MAX(calculated_at),
           EXTRACT(EPOCH FROM (NOW() - MAX(calculated_at)))/60,
           COUNT(*) FILTER (WHERE calculated_at > NOW() - INTERVAL '2 hours'),
           30
    FROM gold.trafic_predictions
)
SELECT
    source,
    last_update,
    age_minutes,
    records_1h,
    expected_interval_min,
    -- Score 0-100 : 100 = parfait, 0 = mort
    GREATEST(0, LEAST(100,
        CASE
            WHEN age_minutes IS NULL THEN 0
            WHEN age_minutes <= expected_interval_min * 1.5 THEN 100
            WHEN age_minutes <= expected_interval_min * 3   THEN 70
            WHEN age_minutes <= expected_interval_min * 6   THEN 40
            WHEN age_minutes <= expected_interval_min * 12  THEN 15
            ELSE 0
        END
    )) AS health_score,
    -- Statut lisible
    CASE
        WHEN age_minutes IS NULL                           THEN 'dead'
        WHEN age_minutes <= expected_interval_min * 1.5    THEN 'healthy'
        WHEN age_minutes <= expected_interval_min * 3      THEN 'delayed'
        WHEN age_minutes <= expected_interval_min * 6      THEN 'stale'
        ELSE 'dead'
    END AS status
FROM source_status
ORDER BY health_score ASC;  -- les plus malades en premier
```

#### B.2. Vue SQL `gold.v_data_completeness` (migration 021)

Complétude par table Silver (% colonnes critiques non-NULL).

```sql
CREATE OR REPLACE VIEW gold.v_data_completeness AS
SELECT
    'silver.trafic_boucles_clean' AS source,
    COUNT(*) AS total_rows,
    ROUND(100.0 * COUNT(*) FILTER (WHERE vitesse_kmh IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS speed_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE geom_wgs84 IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS geo_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE channel_id IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS id_pct
FROM silver.trafic_boucles_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours'

UNION ALL
SELECT
    'silver.tcl_vehicles_clean',
    COUNT(*),
    NULL,  -- pas de vitesse
    ROUND(100.0 * COUNT(*) FILTER (WHERE lat IS NOT NULL) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(*) FILTER (WHERE line_ref IS NOT NULL) / NULLIF(COUNT(*), 0), 1)
FROM silver.tcl_vehicles_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours'

UNION ALL
SELECT
    'silver.velov_clean',
    COUNT(*),
    NULL,
    ROUND(100.0 * COUNT(*) FILTER (WHERE lat IS NOT NULL) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(*) FILTER (WHERE station_id IS NOT NULL) / NULLIF(COUNT(*), 0), 1)
FROM silver.velov_clean
WHERE measurement_time > NOW() - INTERVAL '24 hours';
```

#### B.3. Helpers `get_source_health()` + `get_data_completeness()`

Fichier : `src/data/db_query.py`

```python
def get_source_health() -> pd.DataFrame:
    """Santé par source (fraîcheur + score 0-100 + statut)."""
    query = """
        SELECT source, last_update, age_minutes, records_1h,
               expected_interval_min, health_score, status
        FROM gold.v_source_health
        ORDER BY health_score ASC
    """
    return _df_from_query(query, ())


def get_data_completeness() -> pd.DataFrame:
    """Complétude colonnes critiques par table Silver (24h)."""
    query = """
        SELECT source, total_rows, speed_pct, geo_pct, id_pct
        FROM gold.v_data_completeness
    """
    return _df_from_query(query, ())
```

#### B.4. Widget `source_health_monitor` (Pro TCL — Pipeline)

Page cible : `Pro_6_Pipeline_Mgmt.py`  
Fichier : `dashboard/components/widgets/pro_tcl/source_health_monitor.py`

**Contenu** :

1. **Score global** (bandeau) :
   - Moyenne pondérée des `health_score` (poids : trafic=3, TCL=2, Vélov=2, météo=1, reste=1)
   - Jauge Plotly 0-100 (comme `network_health_gauge` mais pour les données)

2. **Grille source × statut** (8 sources en lignes) :
   - Colonnes : Source | Dernière MAJ | Âge (min) | Records/1h | Score | Statut
   - Code couleur ligne : 🟢 healthy, 🟡 delayed, 🟠 stale, 🔴 dead
   - Statut = pastille colorée

3. **Sparklines fraîcheur** (optionnel, Plotly mini) :
   - Mini courbe `age_minutes` sur 24h par source (si les données historiques sont stockées)
   - Alternative simple : pas de sparkline, juste la grille

4. **Complétude Silver** (section sous la grille) :
   - 3 barres de progression (trafic, TCL, Vélov)
   - % colonnes critiques non-NULL sur 24h

**Renderer** : Plotly gauge + st.dataframe + st.progress_bar  
**Coût estimé** : 🟡 Modéré (2 vues simples, pas de MV)  
**Placement** : en haut de Pro_6, avant les DAG KPIs (remplace les health checks séquentiels actuels)

#### B.5. Widget `data_quality_badge` (Élu — Synthèse)

Page cible : `Elu_1_Synthese.py` (bandeau, à côté de `network_health_gauge` et `drift_status_badge`)  
Fichier : `dashboard/components/widgets/elu/data_quality_badge.py`

**Contenu** : badge 1 ligne :
- 🟢 **Données OK** — 8/8 sources actives, score 94/100
- 🟡 **1 source retardée** — air_quality stale (2h), score 82/100
- 🔴 **Source en panne** — tomtom_traffic dead (6h), score 61/100

**Renderer** : st.markdown HTML  
**Coût estimé** : 🟢 Léger (1 requête)

#### B.6. Upgrade `health_checks.py`

Remplacer les 6 checks mono-table par un seul appel à `gold.v_source_health` :

```python
def check_all_sources() -> list[CheckResult]:
    """Vérifie la santé de toutes les sources via gold.v_source_health."""
    df = get_source_health()
    results = []
    for _, row in df.iterrows():
        status_map = {"healthy": "ok", "delayed": "warning",
                      "stale": "warning", "dead": "critical"}
        results.append(CheckResult(
            name=f"source_{row['source'].replace('.', '_')}",
            status=status_map.get(row["status"], "critical"),
            details=f"{row['source']}: {row['status']} "
                    f"(âge {row['age_minutes']:.0f} min, score {row['health_score']})",
            metric_value=float(row["health_score"]),
            threshold=70.0,
            timestamp=_now_iso(),
        ))
    return results
```

---

## Axe C — Durées réelles dans le comparateur

### Objectif

Remplacer les vitesses moyennes hardcodées (Vélov 12, TC 18, Voiture 25 km/h) dans `Usager_1_Mon_Trajet.py` par les **durées réellement calculées** par chaque widget de trajet. Le comparateur `render_mode_comparison()` affiche alors des données cohérentes.

### Existant

| Widget | Retourne | Champ durée |
|--------|----------|-------------|
| `render_velov_trip()` | Affiche `itin.total_duration_min` | `VelovItinerary.total_duration_min` |
| `render_itinerary_result()` | Affiche `itinerary.total_duration_min` | `Itinerary.total_duration_min` |
| `render_transit_trip()` | Affiche `itin['total_duration_min']` | Dict `total_duration_min` |
| `render_mode_comparison()` | Accepte `results[mode]['duration_min']` | ✅ Déjà prévu |
| `eco_calculator.recommend_mode()` | Accepte `durations` dict | ✅ Déjà prévu |

**Problème actuel** : les widgets de trajet affichent les durées mais ne les **retournent** pas. Le comparateur reçoit des durées estimées via `distance_km / vitesse_moyenne`.

### Solution

#### C.1. Modifier les 3 widgets pour retourner la durée calculée

Chaque widget retourne un dict avec `duration_min` et `distance_km` (au lieu de `None`).

**`render_velov_trip()`** — ajouter un `return` :
```python
def render_velov_trip(...) -> dict | None:
    """..."""
    # ... code existant qui calcule itin ...
    # À la fin :
    return {
        "duration_min": itin.total_duration_min,
        "distance_km": itin.total_distance_m / 1000.0,
        "feasible": True,
    }
```

**`render_transit_trip()`** — idem :
```python
def render_transit_trip(...) -> dict | None:
    # ... code existant ...
    return {
        "duration_min": itin["total_duration_min"],
        "distance_km": itin.get("total_distance_km", 0.0),
        "feasible": True,
    }
```

**`render_itinerary_result()`** — déjà derrière un bouton, retourne :
```python
def render_itinerary_result(...) -> dict | None:
    # ... code existant ...
    return {
        "duration_min": itinerary.total_duration_min,
        "distance_km": itinerary.total_distance_m / 1000.0,
        "feasible": True,
        "avg_speed_kmh": itinerary.avg_speed_kmh,
    }
```

#### C.2. Stocker dans `session_state` dans Usager_1

```python
# Après chaque rendu de widget trajet
if has_tc:
    tc_result = render_transit_trip(origin=..., destination=...)
    if tc_result:
        st.session_state["trip_tc"] = tc_result

if has_velov:
    velov_result = render_velov_trip(origin=..., destination=..., ...)
    if velov_result:
        st.session_state["trip_velov"] = velov_result

if has_voiture:
    # Déjà derrière bouton — stocker au clic
    if st.button("🚗 Calculer l'itinéraire", ...):
        voiture_result = render_itinerary_result(...)
        if voiture_result:
            st.session_state["trip_voiture"] = voiture_result
```

#### C.3. Passer les durées réelles à `render_mode_comparison()`

```python
# Construire results avec durées réelles quand disponibles
trip_data = {}
for mode in modes:
    mode_key = _mode_to_key(mode)  # "Vélov" → "velov", etc.
    trip = st.session_state.get(f"trip_{mode_key}")
    if trip:
        impact = cached_eco_impact(
            mode=mode_key,
            distance_km=trip["distance_km"],
        )
        trip_data[mode_key] = {
            "duration_min": trip["duration_min"],
            "distance_km": trip["distance_km"],
            "impact": impact,
            "feasible": trip.get("feasible", True),
            "source": "computed",
        }
    else:
        # Fallback : estimation (premier affichage, avant calcul)
        trip_data[mode_key] = {
            "duration_min": dist_km / _FALLBACK_SPEEDS[mode_key] * 60,
            "distance_km": dist_km,
            "impact": cached_eco_impact(mode=mode_key, distance_km=dist_km),
            "feasible": True,
            "source": "estimated",
        }

render_mode_comparison(
    results=trip_data,
    critere=search.get("optimize_for", "temps"),
    origin=search["origin"],
    destination=search["destination"],
)
```

#### C.4. Indicateur visuel "estimé vs calculé"

Dans `render_mode_comparison()`, ajouter un badge sous la durée :

```python
source = result.get("source", "estimated")
source_badge = (
    '<span class="lyf-sublabel" style="color:#4CAF50;">✅ calculé</span>'
    if source == "computed"
    else '<span class="lyf-sublabel" style="color:#FF9800;">⏱️ estimé</span>'
)
```

L'usager voit clairement quels modes ont une durée réelle et lesquels sont estimés. Motivation à cliquer "Voir détail" pour obtenir la durée précise.

---

## Widgets — Inventaire complet

### Nouveaux widgets Sprint 16

| Widget | Persona | Page | Renderer | Coût | Gate |
|--------|---------|------|----------|------|------|
| `backtest_dashboard` | Pro TCL | Pro_7_Model_Monitoring | 3× Plotly + table | 🟠 Lourd | `deferred_render()` |
| `drift_status_badge` | Élu | Elu_1_Synthese | st.markdown | 🟢 Léger | Non |
| `source_health_monitor` | Pro TCL | Pro_6_Pipeline_Mgmt | Plotly gauge + table | 🟡 Modéré | Non (remplace les health checks) |
| `data_quality_badge` | Élu | Elu_1_Synthese | st.markdown | 🟢 Léger | Non |

### Widgets modifiés Sprint 16

| Widget | Modification | Fichier |
|--------|-------------|---------|
| `velov_trip` | Retourne `dict` au lieu de `None` | `widgets/usager/velov_trip.py` |
| `transit_trip` | Retourne `dict` au lieu de `None` | `widgets/usager/transit_trip.py` |
| `itinerary_result` | Retourne `dict` au lieu de `None` | `widgets/usager/itinerary.py` |
| `mode_comparison` | Badge "estimé/calculé" + durées réelles | `widgets/usager/mode_comparison.py` |
| `health_checks.py` | `check_all_sources()` remplace 6 checks mono-table | `src/monitoring/health_checks.py` |

### Bilan widgets après Sprint 16

**Total : 55 widgets** (51 existants + 4 nouveaux)

---

## Migrations SQL

| Migration | Axe | Description |
|-----------|-----|------------|
| `migration_020_xgb_vs_tomtom.sql` | A | MV `gold.mv_xgb_vs_tomtom` + vue `gold.v_xgb_accuracy_summary` + index |
| `migration_021_source_health.sql` | B | Vue `gold.v_source_health` + vue `gold.v_data_completeness` |

---

## DAGs Airflow

### Nouveaux

| DAG | Axe | Schedule | Description |
|-----|-----|----------|------------|
| `refresh_xgb_vs_tomtom` | A | `*/30 * * * *` | `REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_xgb_vs_tomtom` |
| `daily_drift_report` | A | `30 5 * * *` | Evidently drift report → INSERT `gold.model_drift_reports` |

### Modifié

| DAG | Modification |
|-----|-------------|
| `data_quality_daily` | Remplace les 6 tasks par 1 task `check_all_sources()` + 1 task drift |

### Bilan DAGs après Sprint 16

**Total : 15 DAGs** (13 existants + 2 nouveaux)

---

## Tests

### Axe A — Backtest Engine

| Test | Type | Fichier |
|------|------|---------|
| `test_get_xgb_vs_tomtom_empty` | unit | `tests/data/test_db_query_backtest.py` |
| `test_get_xgb_vs_tomtom_columns` | unit | idem |
| `test_get_xgb_accuracy_summary` | unit | idem |
| `test_drift_report_no_drift` | unit | `tests/ml/test_drift_detector.py` |
| `test_drift_report_with_drift` | unit | idem |
| `test_backtest_dashboard_smoke` | widget | `tests/persona/test_backtest_dashboard.py` |
| `test_drift_badge_states` | widget | `tests/persona/test_drift_badge.py` |

### Axe B — Data Quality

| Test | Type | Fichier |
|------|------|---------|
| `test_get_source_health_all_sources` | unit | `tests/data/test_db_query_quality.py` |
| `test_get_data_completeness` | unit | idem |
| `test_check_all_sources_healthy` | unit | `tests/monitoring/test_health_checks_v2.py` |
| `test_check_all_sources_dead` | unit | idem |
| `test_source_health_monitor_smoke` | widget | `tests/persona/test_source_health.py` |
| `test_data_quality_badge_states` | widget | `tests/persona/test_dq_badge.py` |

### Axe C — Durées réelles

| Test | Type | Fichier |
|------|------|---------|
| `test_velov_trip_returns_dict` | unit | `tests/persona/test_velov_trip_return.py` |
| `test_transit_trip_returns_dict` | unit | `tests/persona/test_transit_trip_return.py` |
| `test_itinerary_returns_dict` | unit | `tests/persona/test_itinerary_return.py` |
| `test_mode_comparison_computed_badge` | unit | `tests/persona/test_mode_comparison_v2.py` |
| `test_mode_comparison_estimated_fallback` | unit | idem |

**Total tests Sprint 16 : ~18 nouveaux** → ~320 tests verts cible.

---

## Plan d'implémentation

### Phase 1 — Axe A : Backtest Engine (~1.5 jours)

| Étape | Livrable | Effort |
|-------|----------|--------|
| A.1 | Migration 020 : MV `gold.mv_xgb_vs_tomtom` + vue summary | 1h |
| A.2 | Helpers `db_query.py` : `get_xgb_vs_tomtom()` + `get_xgb_accuracy_summary()` | 30 min |
| A.3 | Cache `data_cache.py` : `cached_xgb_vs_tomtom()` + `cached_xgb_accuracy()` | 15 min |
| A.4 | Widget `backtest_dashboard.py` (4 KPI + scatter + courbe MAE + pie + table) | 2h |
| A.5 | Widget `drift_status_badge.py` (badge Élu) | 30 min |
| A.6 | Drift detector Evidently (`src/monitoring/drift_detector.py`) | 1h |
| A.7 | DAG `refresh_xgb_vs_tomtom` (*/30 min) | 15 min |
| A.8 | DAG `daily_drift_report` (05h30) | 30 min |
| A.9 | Câblage Pro_7 + Elu_1 | 15 min |
| A.10 | Tests (7 tests) | 45 min |
| A.11 | Upgrade `check_drift_evidently()` → appel réel | 15 min |

### Phase 2 — Axe B : Data Quality (~1 jour)

| Étape | Livrable | Effort |
|-------|----------|--------|
| B.1 | Migration 021 : vues `v_source_health` + `v_data_completeness` | 45 min |
| B.2 | Helpers `db_query.py` : `get_source_health()` + `get_data_completeness()` | 20 min |
| B.3 | Cache `data_cache.py` : `cached_source_health()` + `cached_data_completeness()` | 10 min |
| B.4 | Widget `source_health_monitor.py` (jauge + grille + complétude) | 1h30 |
| B.5 | Widget `data_quality_badge.py` (badge Élu) | 20 min |
| B.6 | Upgrade `health_checks.py` : `check_all_sources()` | 30 min |
| B.7 | Câblage Pro_6 + Elu_1 | 15 min |
| B.8 | Tests (6 tests) | 30 min |

### Phase 3 — Axe C : Durées réelles (~0.5 jour)

| Étape | Livrable | Effort |
|-------|----------|--------|
| C.1 | Modifier `velov_trip`, `transit_trip`, `itinerary` → retour dict | 30 min |
| C.2 | Usager_1 : stockage `session_state` + passage durées réelles | 30 min |
| C.3 | `mode_comparison` : badge "estimé/calculé" | 20 min |
| C.4 | Tests (5 tests) | 30 min |

### Ordre recommandé

```
Phase 1 (A) → Phase 2 (B) → Phase 3 (C)
```

A d'abord car c'est le plus fort pour le portfolio RNCP (boucle MLOps complète). B enrichit le monitoring (opérationnel). C améliore l'UX usager (finition).

### Résultat attendu v0.8.0

| Métrique | Avant | Après |
|----------|-------|-------|
| Widgets | 51 | **55** |
| DAGs | 13 | **15** |
| Tests | ~301 | **~320** |
| Sources monitorées | 1 (trafic) | **8** (toutes) |
| Validation modèle | Aucune externe | **XGBoost vs TomTom oracle** |
| Drift detection | Placeholder | **Evidently DataDriftPreset** |
| Durées comparateur | Estimées | **Calculées** (+ fallback estimé) |
