# SPEC — Optimisation analyse trafic et interdépendances multimodales

> **Sprint 15+ (2026-06-19)** — Spécification complète pour implémentation par agent.
> **Auteur** : Patrice DUCLOS / Claude Opus 4.6
> **Branche cible** : `vps`
> **Sources** : état actuel LyonFlowFull + ancien repo PDUCLOS/Lyontraffic + recherche état de l'art 2024-2026

---

## Table des matières

1. [Diagnostic : ce qu'on a, ce qui manque](#1-diagnostic)
2. [Axe 1 — Vue multimodale grille (port LyonTraffic)](#2-axe-1-grille-multimodale)
3. [Axe 2 — Propagation de congestion (causalité spatiale)](#3-axe-2-propagation-congestion)
4. [Axe 3 — Couplage bus ↔ trafic temporalisé](#4-axe-3-couplage-bus-trafic)
5. [Axe 4 — Vélov ↔ TC : effet report modal](#5-axe-4-velov-tc-report)
6. [Axe 5 — Score de santé réseau temps réel](#6-axe-5-score-sante)
7. [Axe 6 — Qualité des données et détection anomalies](#7-axe-6-qualite-donnees)
8. [Axe 7 — Météo comme variable d'interaction](#8-axe-7-meteo-interaction)
9. [Fichiers à créer / modifier](#9-fichiers)
10. [Migrations SQL](#10-migrations-sql)
11. [Tests](#11-tests)
12. [Priorités et dépendances](#12-priorites)
13. [Sources académiques](#13-sources)

---

## 1. Diagnostic

### 1.1. Ce qu'on a déjà (état Sprint 15+)

| Capacité | Fichier/table | Statut |
|----------|---------------|--------|
| **Bottleneck bus × trafic** | `gold.infrastructure_bottlenecks` + `silver_to_gold.py:_BOTTLENECK_SQL` | ✅ Fonctionne, mais JOIN par heure globale (pas spatial) |
| **Corrélation bus × trafic** | `widgets/pro_tcl/correlation_matrix.py` | ✅ Matrice 2×2 (bus_state × traffic_state → 4 diagnostics) |
| **Cohérence TomTom ↔ GL** | `gold.v_coherence_tomtom_vs_grandlyon` + `coherence_scatter.py` | ✅ Sprint 13+ — JOIN spatial PostGIS ST_DWithin 200m |
| **Capteurs HS** | `gold.v_tomtom_gl_drift` | ✅ Détecteur auto (≥60% drift 24h) |
| **GNN spatial** | `training/stgcn/` — ST-GRU-GNN ~1520 nœuds H3 | ✅ Propagation spatiale congestion, mais pas exploité pour interdépendances |
| **XGBoost H+1h** | `dag_inference_xgboost` — 11 features | ✅ Prédiction vitesse avec météo+vacances |
| **Vélov prédiction** | XGBoost H+30min + H+1h | ✅ Par station, pas de lien avec TC/trafic |
| **Bus delay segments** | `gold.bus_delay_segments` | ✅ Retard agrégé par ligne/heure/jour |
| **KPIs par ligne TCL** | `gold.mv_line_kpis_live` + `gold.mv_otp_heatmap` | ✅ Sprint 7 — OTP et heatmap |

### 1.2. Ce qui manque (lacunes identifiées)

| Lacune | Impact | Priorité |
|--------|--------|----------|
| **Pas de vue multimodale unifiée** | On ne peut pas voir simultanément trafic + TC + vélov sur une même grille spatiale. Chaque source est silotée. | 🔴 Haute |
| **Bottleneck pas spatialisé** | `_BOTTLENECK_SQL` JOIN bus × trafic par HEURE globale, pas par ZONE. Un retard bus à Gerland est corrélé au trafic global Lyon, pas au trafic local Gerland. | 🔴 Haute |
| **Pas de propagation temporelle** | On sait qu'un segment est congestionné, mais on ne détecte pas la propagation (segment A congestionné → segment B congestionné 5 min plus tard). | 🟠 Moyenne |
| **Pas de couplage Vélov ↔ TC** | Quand le métro A est en panne, les stations Vélov Part-Dieu se vident. Ce report modal n'est pas détecté. | 🟠 Moyenne |
| **Pas de score de santé global** | Pas de KPI unique "le réseau Lyon va bien/mal" qui agrège toutes les sources. | 🟡 Enrichissement |
| **Qualité données non automatisée** | Pas de validation systématique des données brutes avant feature engineering (plages valides, taux de null, doublons). | 🟠 Moyenne |
| **Météo pas croisée avec l'analyse** | La météo est une feature ML mais n'est pas utilisée dans l'analyse d'interdépendances (ex: pluie → +X% retard bus ET -Y% disponibilité vélov). | 🟡 Enrichissement |

---

## 2. Axe 1 — Vue multimodale grille spatiale

### 2.1. Concept

**Source LyonTraffic** : `scripts/create_multimodal_view.py` — vue `gold.multimodal_status_grid`

Grille spatiale 0.01° (~1km) qui FUSIONNE les 3 sources en une seule vue :

```
Cellule grille (lat_grid, lon_grid)
├── Trafic routier : vitesse moyenne, % congestion
├── TCL : retard moyen, % véhicules en retard
├── Vélov : vélos disponibles, places libres
└── Météo : température, précipitations (CROSS JOIN)
```

**Score multimodal** par cellule :
```
score = 0.5 × pct_congestion_route + 0.5 × pct_tcl_retard
score -= 1.0  si velos_dispo >= 5  (bonus résilience : alternative dispo)
score = clamp(0, 10)
```

### 2.2. Adaptation au projet actuel

LyonTraffic utilisait `bronze.pvotrafic_snapshots` (schéma ancien). LyonFlowFull utilise :
- Trafic : `gold.traffic_features_live` (a `speed_kmh`, `lat`, `lon`)
- TCL : `gold.tcl_vehicle_realtime` (a `latitude`, `longitude`, `delay_seconds`, `is_delayed`)
- Vélov : `silver.velov_clean` (a `lat`, `lon`, `num_bikes_available`, `num_docks_available`)
- Météo : `silver.meteo_hourly` (a `temperature_2m`, `precipitation`)

### 2.3. SQL cible (vue matérialisée)

```sql
CREATE MATERIALIZED VIEW gold.mv_multimodal_grid AS
WITH
trafic_grid AS (
    SELECT
        ROUND(lat::numeric, 2) AS grid_lat,
        ROUND(lon::numeric, 2) AS grid_lon,
        AVG(speed_kmh)::numeric(6,2) AS avg_speed_kmh,
        COUNT(*) AS n_sensors,
        (SUM(CASE WHEN speed_kmh < 25 THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2) AS pct_congestion
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '1 hour'
    GROUP BY 1, 2
),
tcl_grid AS (
    SELECT
        ROUND(latitude::numeric, 2) AS grid_lat,
        ROUND(longitude::numeric, 2) AS grid_lon,
        AVG(delay_seconds)::numeric(8,2) AS avg_delay_sec,
        COUNT(*) AS n_vehicles,
        (SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2) AS pct_delayed
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '1 hour'
    GROUP BY 1, 2
),
velov_grid AS (
    SELECT
        ROUND(lat::numeric, 2) AS grid_lat,
        ROUND(lon::numeric, 2) AS grid_lon,
        SUM(num_bikes_available) AS bikes_available,
        SUM(num_docks_available) AS docks_available,
        COUNT(*) AS n_stations
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
    GROUP BY 1, 2
),
meteo AS (
    SELECT temperature_2m, precipitation
    FROM silver.meteo_hourly
    ORDER BY measurement_time DESC LIMIT 1
)
SELECT
    COALESCE(t.grid_lat, c.grid_lat, v.grid_lat) AS lat,
    COALESCE(t.grid_lon, c.grid_lon, v.grid_lon) AS lon,
    -- Trafic
    COALESCE(t.avg_speed_kmh, 0) AS avg_speed_kmh,
    COALESCE(t.pct_congestion, 0) AS pct_congestion,
    COALESCE(t.n_sensors, 0) AS n_sensors,
    -- TCL
    COALESCE(c.avg_delay_sec, 0) AS avg_delay_sec,
    COALESCE(c.pct_delayed, 0) AS pct_delayed,
    COALESCE(c.n_vehicles, 0) AS n_vehicles,
    -- Vélov
    COALESCE(v.bikes_available, 0) AS bikes_available,
    COALESCE(v.docks_available, 0) AS docks_available,
    COALESCE(v.n_stations, 0) AS n_stations,
    -- Météo
    m.temperature_2m,
    m.precipitation,
    -- Score multimodal (0-10, haut = saturé)
    GREATEST(0, LEAST(10,
        0.5 * COALESCE(t.pct_congestion, 0) / 10.0
      + 0.5 * COALESCE(c.pct_delayed, 0) / 10.0
      - CASE WHEN COALESCE(v.bikes_available, 0) >= 5 THEN 1.0 ELSE 0.0 END
    ))::numeric(4,2) AS score_multimodal,
    -- Diagnostic textuel
    CASE
        WHEN COALESCE(t.pct_congestion, 0) > 60 AND COALESCE(c.pct_delayed, 0) > 40
            THEN 'saturated'
        WHEN COALESCE(t.pct_congestion, 0) > 60
            THEN 'road_congested'
        WHEN COALESCE(c.pct_delayed, 0) > 40
            THEN 'transit_delayed'
        WHEN COALESCE(v.bikes_available, 0) < 3 AND COALESCE(v.n_stations, 0) > 0
            THEN 'velov_scarce'
        ELSE 'ok'
    END AS diagnosis,
    NOW() AS computed_at
FROM trafic_grid t
FULL OUTER JOIN tcl_grid c ON t.grid_lat = c.grid_lat AND t.grid_lon = c.grid_lon
FULL OUTER JOIN velov_grid v ON COALESCE(t.grid_lat, c.grid_lat) = v.grid_lat
                             AND COALESCE(t.grid_lon, c.grid_lon) = v.grid_lon
CROSS JOIN meteo m
WHERE COALESCE(t.grid_lat, c.grid_lat, v.grid_lat) IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_multimodal_grid_latlon
    ON gold.mv_multimodal_grid (lat, lon);
```

**Refresh** : `REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_multimodal_grid` toutes les 5 minutes dans un DAG maintenance.

### 2.4. Widget dashboard — Carte chaleur multimodale

Page **Pro_3_Correlation.py** (ou nouvelle page Élu) : carte Folium rectangles colorées par `score_multimodal`.

- Score > 7 → rouge "Saturé"
- Score 4-7 → orange "Tendu"
- Score < 4 → vert "Fluide"
- Popup : détail trafic + TCL + vélov + météo

**Fichier** : `dashboard/components/widgets/pro_tcl/multimodal_heatmap.py` (ou `elu/`)

---

## 3. Axe 2 — Propagation de congestion (causalité spatiale)

### 3.1. Concept

**Problème** : on sait que le segment A est congestionné ET le segment B aussi, mais on ne sait pas si A a CAUSÉ B (congestion qui se propage en amont) ou si c'est une coïncidence.

**État de l'art** :
- **Granger Causality** : test si la série temporelle de vitesse du segment A "précède" celle de B. Si oui, A cause (au sens Granger) B. Limité (linéaire, faux positifs).
- **Transfer Entropy** : version non-linéaire de Granger, capte les dépendances non-linéaires. Plus robuste.
- **STGC-GNN** : GNN avec graphe de causalité Granger comme matrice d'adjacence. Exactement ce qu'on a avec ST-GRU-GNN mais en ajoutant la dimension causale.
- **Convergent Cross-Mapping (CCM)** : méthode 2025 (Mao et al., Wiley) spécifiquement pour la causalité spatiale du trafic urbain. Gère la non-linéarité mieux que Granger.

### 3.2. Implémentation pragmatique (adapté VPS 12Go RAM)

On ne peut pas tourner du Transfer Entropy sur 1520 nœuds. Approche simplifiée :

**Étape 1 — Lag cross-correlation SQL**

Pour chaque paire de capteurs voisins (K=2 dans `gold.dim_gnn_adjacency`), calculer la corrélation croisée avec décalage temporel (lag 5min, 10min, 15min) :

```sql
CREATE MATERIALIZED VIEW gold.mv_congestion_propagation AS
WITH speed_series AS (
    SELECT
        channel_id,
        DATE_TRUNC('minute', fetched_at) AS ts_5min,
        AVG(speed_kmh) AS speed
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '24 hours'
    GROUP BY channel_id, DATE_TRUNC('minute', fetched_at)
),
pairs AS (
    SELECT DISTINCT source_node AS node_a, target_node AS node_b
    FROM gold.dim_gnn_adjacency
    WHERE source_node != target_node
)
SELECT
    p.node_a,
    p.node_b,
    CORR(a.speed, b.speed) AS corr_lag0,
    CORR(a.speed, b_lag1.speed) AS corr_lag5min,
    CORR(a.speed, b_lag2.speed) AS corr_lag10min,
    CASE
        WHEN CORR(a.speed, b_lag1.speed) > CORR(a.speed, b.speed) + 0.05
        THEN 'propagation_A_to_B'
        WHEN CORR(a.speed, b.speed) > 0.7
        THEN 'co_congested'
        ELSE 'independent'
    END AS relationship
FROM pairs p
JOIN speed_series a ON a.channel_id = p.node_a
JOIN speed_series b ON b.channel_id = p.node_b AND b.ts_5min = a.ts_5min
LEFT JOIN speed_series b_lag1 ON b_lag1.channel_id = p.node_b
    AND b_lag1.ts_5min = a.ts_5min + INTERVAL '5 minutes'
LEFT JOIN speed_series b_lag2 ON b_lag2.channel_id = p.node_b
    AND b_lag2.ts_5min = a.ts_5min + INTERVAL '10 minutes'
GROUP BY p.node_a, p.node_b;
```

**Résultat** : pour chaque paire de capteurs adjacents, on sait si :
- `propagation_A_to_B` : A ralentit 5min AVANT B → congestion se propage de A vers B
- `co_congested` : corrélés simultanément → même cause externe (ex: feu rouge, chantier)
- `independent` : pas de lien

**Étape 2 — Widget "Propagation de congestion"**

Carte Folium avec flèches directionnelles entre capteurs (A → B si propagation détectée). Épaisseur proportionnelle au `corr_lag5min`. Couleur : rouge si propagation active (vitesse actuelle < 20), gris sinon.

### 3.3. Enrichissement futur (Phase 2)

- Intégrer la propagation comme feature du GNN : remplacer la matrice d'adjacence binaire par les poids de `corr_lag5min`
- Python `statsmodels.tsa.stattools.grangercausalitytests()` pour validation
- Détection de "sources de congestion" : nœuds qui propagent le plus souvent vers leurs voisins

---

## 4. Axe 3 — Couplage bus ↔ trafic temporalisé ET spatialisé

### 4.1. Problème actuel

`_BOTTLENECK_SQL` (dans `silver_to_gold.py:395`) fait :

```sql
-- ACTUEL (problématique)
FROM bus_hourly bh
LEFT JOIN traffic_hourly th ON th.hour_of_day = bh.hour
```

Ce JOIN est **global** : le retard moyen du bus L12 à 8h est corrélé au trafic moyen de TOUT Lyon à 8h. C'est trop grossier — le bus L12 circule entre Gerland et Part-Dieu, il faudrait le corréler au trafic de CETTE zone.

### 4.2. Solution : JOIN spatial bus ↔ trafic

Utiliser les coordonnées GPS des véhicules TCL (`gold.tcl_vehicle_realtime.latitude/longitude`) et les coordonnées des capteurs trafic (`gold.traffic_features_live.lat/lon`) pour un JOIN spatial :

```sql
CREATE MATERIALIZED VIEW gold.mv_bus_traffic_spatial AS
WITH
bus_positions AS (
    SELECT
        line_ref,
        EXTRACT(HOUR FROM recorded_at)::int AS hour,
        ROUND(latitude::numeric, 3) AS lat3,
        ROUND(longitude::numeric, 3) AS lon3,
        AVG(delay_seconds)::numeric(8,2) AS avg_delay_sec,
        COUNT(*) AS n_obs,
        BOOL_OR(is_delayed) AS any_delayed
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '7 days'
    GROUP BY line_ref, EXTRACT(HOUR FROM recorded_at)::int,
             ROUND(latitude::numeric, 3), ROUND(longitude::numeric, 3)
),
traffic_zones AS (
    SELECT
        ROUND(lat::numeric, 3) AS lat3,
        ROUND(lon::numeric, 3) AS lon3,
        EXTRACT(HOUR FROM fetched_at)::int AS hour,
        AVG(speed_kmh)::numeric(6,2) AS avg_speed
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
    GROUP BY ROUND(lat::numeric, 3), ROUND(lon::numeric, 3),
             EXTRACT(HOUR FROM fetched_at)::int
)
SELECT
    bp.line_ref,
    bp.hour,
    bp.lat3 AS lat,
    bp.lon3 AS lon,
    bp.avg_delay_sec AS bus_delay_sec,
    bp.n_obs AS bus_obs,
    tz.avg_speed AS traffic_speed_kmh,
    -- Diagnostic spatialisé
    CASE
        WHEN bp.avg_delay_sec > 120 AND tz.avg_speed < 25
            THEN 'infra'           -- bus ET trafic souffrent dans la MÊME zone
        WHEN bp.avg_delay_sec > 120 AND (tz.avg_speed >= 25 OR tz.avg_speed IS NULL)
            THEN 'operations'      -- bus en retard mais trafic OK → problème opérationnel TCL
        WHEN bp.avg_delay_sec <= 120 AND tz.avg_speed < 25
            THEN 'bus_lane_ok'     -- trafic congestionné mais bus OK → voie dédiée efficace
        ELSE 'ok'
    END AS diagnosis
FROM bus_positions bp
LEFT JOIN traffic_zones tz
    ON bp.lat3 = tz.lat3
   AND bp.lon3 = tz.lon3
   AND bp.hour = tz.hour;
```

**Différence clé** : `ON bp.lat3 = tz.lat3 AND bp.lon3 = tz.lon3` — le bus est corrélé au trafic de SA zone (résolution 0.001° ≈ 100m), pas au trafic global Lyon.

### 4.3. Impact dashboard

Le widget `correlation_matrix.py` existant utilise `cached_infra_bottlenecks()`. On peut soit :
- **Option A** : remplacer `gold.infrastructure_bottlenecks` par `gold.mv_bus_traffic_spatial` (breaking mais plus correct)
- **Option B** : ajouter un widget parallèle "Corrélation spatialisée" qui lit la nouvelle MV (non-breaking)

**Recommandation** : Option B pour Sprint 15+, Option A à terme.

---

## 5. Axe 4 — Vélov ↔ TC : effet report modal

### 5.1. Concept

Quand un incident TC survient (métro A en panne, tram T1 interrompu), les usagers se reportent sur d'autres modes. Effet mesurable :
- Stations Vélov proches des arrêts TC impactés se vident rapidement
- Trafic routier augmente dans la zone

**État de l'art 2025** : les études sur le couplage bike-sharing ↔ transit montrent que ~24% des trajets vélos en libre-service sont des trajets "first/last mile" connectés au métro. Quand le métro tombe, ces trajets basculent.

### 5.2. Détection automatique

**Vue SQL : variation anormale Vélov par zone TC**

```sql
CREATE MATERIALIZED VIEW gold.mv_velov_transit_coupling AS
WITH
-- Stations Vélov proches d'arrêts TC (JOIN spatial < 300m)
velov_near_transit AS (
    SELECT DISTINCT
        v.station_id AS velov_station_id,
        v.name AS velov_name,
        lt.line_ref,
        lt.lieu_name AS transit_stop
    FROM silver.velov_clean v
    JOIN referentiel.lieux_transports lt
        ON ST_DWithin(
            ST_SetSRID(ST_MakePoint(v.lon, v.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(lt.lon, lt.lat), 4326)::geography,
            300  -- mètres
        )
    WHERE v.fetched_at > NOW() - INTERVAL '15 minutes'
),
-- Disponibilité Vélov horaire (rolling 7 jours)
velov_hourly AS (
    SELECT
        vnt.velov_station_id,
        vnt.line_ref,
        EXTRACT(HOUR FROM vc.fetched_at)::int AS hour,
        AVG(vc.num_bikes_available)::numeric(6,2) AS avg_bikes,
        STDDEV(vc.num_bikes_available)::numeric(6,2) AS std_bikes
    FROM velov_near_transit vnt
    JOIN silver.velov_clean vc ON vc.station_id = vnt.velov_station_id
    WHERE vc.fetched_at > NOW() - INTERVAL '7 days'
    GROUP BY vnt.velov_station_id, vnt.line_ref, EXTRACT(HOUR FROM vc.fetched_at)::int
),
-- Disponibilité Vélov actuelle
velov_now AS (
    SELECT
        station_id AS velov_station_id,
        num_bikes_available AS bikes_now
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
)
SELECT
    vh.velov_station_id,
    vh.line_ref AS transit_line,
    vh.hour,
    vh.avg_bikes AS baseline_bikes,
    vh.std_bikes,
    vn.bikes_now,
    -- Z-score : combien d'écarts-types en dessous de la moyenne ?
    CASE WHEN vh.std_bikes > 0
         THEN ((vn.bikes_now - vh.avg_bikes) / vh.std_bikes)::numeric(4,2)
         ELSE 0
    END AS z_score,
    -- Alerte si z_score < -2 (2 écarts-types en dessous = anormal)
    CASE WHEN vh.std_bikes > 0
          AND (vn.bikes_now - vh.avg_bikes) / vh.std_bikes < -2
         THEN TRUE
         ELSE FALSE
    END AS anomaly_detected
FROM velov_hourly vh
JOIN velov_now vn ON vn.velov_station_id = vh.velov_station_id
WHERE vh.hour = EXTRACT(HOUR FROM NOW())::int;
```

**Interprétation** : si `anomaly_detected = TRUE` pour plusieurs stations Vélov proches d'une même ligne TC → probable incident sur cette ligne TC causant un report modal.

### 5.3. Widget "Alerte report modal"

Dans `Pro_3_Correlation.py` ou en page dédiée :
- KPI : nombre d'anomalies Vélov détectées
- Tableau : stations Vélov anormalement vides + ligne TC associée
- Corrélation temporelle : graphe Vélov dispo vs retard TC (même zone, même heure)

---

## 6. Axe 5 — Score de santé réseau temps réel

### 6.1. Concept

Un KPI unique 0-100 qui dit "le réseau de mobilité Lyon va bien/mal" :

```
health_score = 100
  - (pct_congestion_globale × 0.3)       # trafic routier
  - (pct_tcl_retard_global × 0.3)        # transport en commun
  - (pct_velov_vides × 0.2)              # vélov
  - (penalty_meteo × 0.2)                # météo défavorable
```

### 6.2. SQL

```sql
CREATE OR REPLACE FUNCTION gold.fn_network_health_score()
RETURNS TABLE (
    score numeric(5,2),
    pct_congestion numeric(5,2),
    pct_tcl_delayed numeric(5,2),
    pct_velov_empty numeric(5,2),
    meteo_penalty numeric(5,2),
    diagnosis text,
    computed_at timestamptz
) AS $$
WITH
traffic AS (
    SELECT
        (SUM(CASE WHEN speed_kmh < 25 THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2) AS pct_cong
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '30 minutes'
),
tcl AS (
    SELECT
        (SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2) AS pct_del
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '30 minutes'
),
velov AS (
    SELECT
        (SUM(CASE WHEN num_bikes_available = 0 THEN 1 ELSE 0 END)::float
         / NULLIF(COUNT(*), 0) * 100)::numeric(5,2) AS pct_empty
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
),
meteo AS (
    SELECT
        CASE
            WHEN precipitation > 5 THEN 15  -- pluie forte
            WHEN precipitation > 1 THEN 8   -- pluie légère
            WHEN temperature_2m < 0 THEN 10 -- gel
            WHEN temperature_2m > 35 THEN 5 -- canicule
            ELSE 0
        END::numeric(5,2) AS penalty
    FROM silver.meteo_hourly
    ORDER BY measurement_time DESC LIMIT 1
)
SELECT
    GREATEST(0, LEAST(100,
        100
        - COALESCE(t.pct_cong, 0) * 0.3
        - COALESCE(c.pct_del, 0) * 0.3
        - COALESCE(v.pct_empty, 0) * 0.2
        - COALESCE(m.penalty, 0)
    ))::numeric(5,2),
    COALESCE(t.pct_cong, 0),
    COALESCE(c.pct_del, 0),
    COALESCE(v.pct_empty, 0),
    COALESCE(m.penalty, 0),
    CASE
        WHEN GREATEST(0, 100 - COALESCE(t.pct_cong,0)*0.3 - COALESCE(c.pct_del,0)*0.3
             - COALESCE(v.pct_empty,0)*0.2 - COALESCE(m.penalty,0)) > 75
            THEN 'healthy'
        WHEN GREATEST(0, 100 - COALESCE(t.pct_cong,0)*0.3 - COALESCE(c.pct_del,0)*0.3
             - COALESCE(v.pct_empty,0)*0.2 - COALESCE(m.penalty,0)) > 50
            THEN 'stressed'
        WHEN GREATEST(0, 100 - COALESCE(t.pct_cong,0)*0.3 - COALESCE(c.pct_del,0)*0.3
             - COALESCE(v.pct_empty,0)*0.2 - COALESCE(m.penalty,0)) > 25
            THEN 'degraded'
        ELSE 'critical'
    END,
    NOW()
FROM traffic t, tcl c, velov v, meteo m;
$$ LANGUAGE SQL STABLE;
```

### 6.3. Widget

Jauge circulaire (gauge chart) en haut de page Pro_TCL ou Élu avec :
- Score 0-100, coloré (vert > 75, orange 50-75, rouge < 50)
- 4 sous-jauges : trafic, TC, vélov, météo
- Historique 24h en sparkline

---

## 7. Axe 6 — Qualité des données et détection anomalies

### 7.1. Concept (porté de LyonTraffic)

**Source** : `PDUCLOS/Lyontraffic/src/transformation/data_quality.py`

Module `QualityConfig` + `QualityReport` qui valide les données AVANT le feature engineering :

| Règle | Seuil | Source |
|-------|-------|--------|
| Taux occupation | 0-100% | Physiquement impossible au-delà |
| Vitesse | 0-130 km/h | Limite légale + capteurs urbains |
| Température | -20 à 45°C | Records historiques Lyon |
| Précipitations | 0-100 mm/h | Orage extrême |
| Taux de null max | 30% | Au-delà, données inexploitables |
| Taux de doublons max | 5% | Source de biais |
| Minimum de lignes | 100 | Pas assez de données pour statistiques |

### 7.2. Implémentation

Créer `src/transformation/data_quality.py` adapté au schéma LyonFlowFull :

```python
@dataclass
class QualityConfig:
    speed_min_kmh: float = 0.0
    speed_max_kmh: float = 130.0
    temperature_min_c: float = -20.0
    temperature_max_c: float = 45.0
    precipitation_max_mm: float = 100.0
    delay_max_seconds: int = 3600      # 1h max de retard (au-delà = erreur)
    max_null_ratio: float = 0.30
    max_duplicate_ratio: float = 0.05
    min_rows: int = 100


def validate_traffic_features(df: pl.DataFrame, config: QualityConfig = None) -> QualityReport:
    """Valide gold.traffic_features_live."""
    ...

def validate_tcl_realtime(df: pl.DataFrame, config: QualityConfig = None) -> QualityReport:
    """Valide gold.tcl_vehicle_realtime."""
    ...

def validate_velov_clean(df: pl.DataFrame, config: QualityConfig = None) -> QualityReport:
    """Valide silver.velov_clean."""
    ...
```

**Intégration** : appeler dans le DAG `dag_data_quality_daily` (déjà existant dans le scheduling Airflow à 04h00).

---

## 8. Axe 7 — Météo comme variable d'interaction

### 8.1. Concept

La météo est déjà une feature du XGBoost (`temperature_2m`, `precipitation`, `is_vacances`, `is_ferie`). Mais on ne l'utilise pas pour EXPLIQUER les interdépendances :

| Condition météo | Effet trafic | Effet TC | Effet Vélov |
|-----------------|-------------|----------|-------------|
| Pluie > 5mm/h | +20-40% congestion | +30% retard bus | -60% dispo vélos |
| Pluie légère 1-5mm | +10% congestion | +10% retard | -30% dispo |
| Gel (< 0°C) | +15% congestion (verglas) | +20% retard | -80% dispo (dangereux) |
| Canicule (> 35°C) | Neutre | +5% retard (climatisation = surconso) | -20% dispo |
| Beau temps | Baseline | Baseline | +30% dispo |

### 8.2. Vue SQL d'interaction météo

```sql
CREATE MATERIALIZED VIEW gold.mv_meteo_impact AS
WITH
meteo_bands AS (
    SELECT
        measurement_time,
        temperature_2m,
        precipitation,
        CASE
            WHEN precipitation > 5 THEN 'heavy_rain'
            WHEN precipitation > 1 THEN 'light_rain'
            WHEN temperature_2m < 0 THEN 'frost'
            WHEN temperature_2m > 35 THEN 'heatwave'
            ELSE 'fair'
        END AS meteo_band
    FROM silver.meteo_hourly
    WHERE measurement_time > NOW() - INTERVAL '30 days'
),
traffic_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(tf.speed_kmh)::numeric(6,2) AS avg_speed,
        STDDEV(tf.speed_kmh)::numeric(6,2) AS std_speed,
        COUNT(*) AS n_obs
    FROM gold.traffic_features_live tf
    JOIN meteo_bands mb ON DATE_TRUNC('hour', tf.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
),
tcl_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(tr.delay_seconds)::numeric(8,2) AS avg_delay,
        COUNT(*) AS n_obs
    FROM gold.tcl_vehicle_realtime tr
    JOIN meteo_bands mb ON DATE_TRUNC('hour', tr.recorded_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
),
velov_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(vc.num_bikes_available)::numeric(6,2) AS avg_bikes,
        COUNT(*) AS n_obs
    FROM silver.velov_clean vc
    JOIN meteo_bands mb ON DATE_TRUNC('hour', vc.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
)
SELECT
    t.meteo_band,
    -- Trafic
    t.avg_speed AS traffic_avg_speed,
    t.std_speed AS traffic_std_speed,
    t.n_obs AS traffic_obs,
    -- Impact vs baseline (fair weather)
    (t.avg_speed - fair_t.avg_speed)::numeric(6,2) AS traffic_delta_vs_fair,
    -- TCL
    c.avg_delay AS tcl_avg_delay_sec,
    c.n_obs AS tcl_obs,
    (c.avg_delay - fair_c.avg_delay)::numeric(8,2) AS tcl_delay_delta_vs_fair,
    -- Vélov
    v.avg_bikes AS velov_avg_bikes,
    v.n_obs AS velov_obs,
    (v.avg_bikes - fair_v.avg_bikes)::numeric(6,2) AS velov_delta_vs_fair
FROM traffic_by_meteo t
JOIN tcl_by_meteo c ON c.meteo_band = t.meteo_band
JOIN velov_by_meteo v ON v.meteo_band = t.meteo_band
-- Baselines "fair weather"
CROSS JOIN (SELECT avg_speed FROM traffic_by_meteo WHERE meteo_band = 'fair') fair_t
CROSS JOIN (SELECT avg_delay FROM tcl_by_meteo WHERE meteo_band = 'fair') fair_c
CROSS JOIN (SELECT avg_bikes FROM velov_by_meteo WHERE meteo_band = 'fair') fair_v;
```

### 8.3. Widget

Tableau / bar chart montrant l'impact de chaque condition météo sur chaque mode. Format :

```
┌─────────────┬───────────────┬──────────────┬──────────────┐
│ Météo       │ Trafic Δ      │ TC retard Δ  │ Vélov Δ      │
├─────────────┼───────────────┼──────────────┼──────────────┤
│ 🌧 Forte    │ -12 km/h      │ +45 sec      │ -8 vélos     │
│ 🌦 Légère   │ -5 km/h       │ +15 sec      │ -4 vélos     │
│ ❄ Gel       │ -8 km/h       │ +25 sec      │ -12 vélos    │
│ ☀ Beau      │ baseline      │ baseline     │ baseline     │
└─────────────┴───────────────┴──────────────┴──────────────┘
```

---

## 9. Fichiers à créer / modifier

### Fichiers à CRÉER

| Fichier | Axe | Description |
|---------|-----|-------------|
| `scripts/sql/migration_017_multimodal_grid.sql` | 1 | Vue matérialisée `gold.mv_multimodal_grid` |
| `scripts/sql/migration_018_congestion_propagation.sql` | 2 | Vue `gold.mv_congestion_propagation` |
| `scripts/sql/migration_019_bus_traffic_spatial.sql` | 3 | Vue `gold.mv_bus_traffic_spatial` (remplace bottleneck global) |
| `scripts/sql/migration_020_velov_transit_coupling.sql` | 4 | Vue `gold.mv_velov_transit_coupling` |
| `scripts/sql/migration_021_meteo_impact.sql` | 7 | Vue `gold.mv_meteo_impact` |
| `scripts/sql/migration_022_network_health.sql` | 5 | Fonction `gold.fn_network_health_score()` |
| `src/transformation/data_quality.py` | 6 | Module validation données (port LyonTraffic) |
| `dashboard/components/widgets/pro_tcl/multimodal_heatmap.py` | 1 | Carte chaleur grille multimodale |
| `dashboard/components/widgets/pro_tcl/propagation_map.py` | 2 | Carte propagation congestion |
| `dashboard/components/widgets/pro_tcl/meteo_impact.py` | 7 | Tableau impact météo × modes |
| `dashboard/components/widgets/pro_tcl/network_health.py` | 5 | Jauge santé réseau |
| `dashboard/components/widgets/pro_tcl/modal_shift_alert.py` | 4 | Alerte report modal Vélov ↔ TC |

### Fichiers à MODIFIER

| Fichier | Modification |
|---------|-------------|
| `src/transformation/silver_to_gold.py` | Ajouter refresh des nouvelles MVs dans `transform_silver_to_gold()` |
| `dags/transforms/` | Ajouter DAG refresh MVs (toutes les 5 min pour grille, 1h pour les autres) |
| `dashboard/components/data_cache.py` | Ajouter `cached_multimodal_grid()`, `cached_network_health()`, etc. |
| `dashboard/components/widgets/pro_tcl/__init__.py` | Exporter nouveaux widgets |
| `dashboard/pages/Pro_3_Correlation.py` | Intégrer grille multimodale + propagation |
| `src/data/db_query.py` | Helpers SQL pour les nouvelles vues |
| `src/data/data_loader.py` | Wrappers fail-loud pour les nouvelles vues |

---

## 10. Migrations SQL

Toutes les migrations sont idempotentes (`CREATE MATERIALIZED VIEW IF NOT EXISTS` ou `CREATE OR REPLACE`).

**Ordre d'exécution** :
1. `migration_017` : grille multimodale (dépend de `gold.traffic_features_live`, `gold.tcl_vehicle_realtime`, `silver.velov_clean`)
2. `migration_018` : propagation congestion (dépend de `gold.traffic_features_live`, `gold.dim_gnn_adjacency`)
3. `migration_019` : bus × trafic spatial (dépend de `gold.tcl_vehicle_realtime`, `gold.traffic_features_live`)
4. `migration_020` : couplage Vélov ↔ TC (dépend de `silver.velov_clean`, `referentiel.lieux_transports` — **requiert PostGIS ST_DWithin**)
5. `migration_021` : impact météo (dépend de `silver.meteo_hourly`, `gold.traffic_features_live`, etc.)
6. `migration_022` : score santé réseau (dépend de toutes les sources)

**Refresh scheduling** (dans DAG maintenance) :

| Vue | Fréquence | Coût estimé |
|-----|-----------|-------------|
| `mv_multimodal_grid` | */5 min | Léger (3 aggregations + FULL JOIN) |
| `mv_congestion_propagation` | */30 min | Moyen (CORR sur 24h × paires adjacentes) |
| `mv_bus_traffic_spatial` | */15 min | Moyen |
| `mv_velov_transit_coupling` | */15 min | Léger si PostGIS indexé |
| `mv_meteo_impact` | 1×/jour (04h30) | Lourd (30 jours × 3 JOINs) |
| `fn_network_health_score` | Temps réel (fonction, pas MV) | Très léger |

---

## 11. Tests

### Tests unitaires (par axe)

| Fichier test | Axe | Tests |
|-------------|-----|-------|
| `tests/data/test_multimodal_grid.py` | 1 | Score multimodal calcul, diagnostic, cas limites (0 capteurs) |
| `tests/data/test_congestion_propagation.py` | 2 | Détection lag cross-corr, relationship classification |
| `tests/data/test_bus_traffic_spatial.py` | 3 | Diagnostic spatial vs global, cas sans trafic dans zone |
| `tests/data/test_velov_transit_coupling.py` | 4 | Z-score anomaly, seuil -2σ |
| `tests/data/test_network_health.py` | 5 | Score 0-100, diagnosis labels, cas extrêmes |
| `tests/data/test_data_quality.py` | 6 | Validation plages, null ratio, doublons |
| `tests/data/test_meteo_impact.py` | 7 | Delta vs fair baseline, bands classification |

---

## 12. Priorités et dépendances

```
Priorité 1 (fondations) :
  ┌─ Axe 1 : Grille multimodale (permet tout le reste)
  └─ Axe 3 : Bus × trafic spatial (corrige bottleneck actuel)

Priorité 2 (enrichissement majeur) :
  ┌─ Axe 5 : Score santé réseau (KPI de synthèse)
  ├─ Axe 6 : Qualité données (fiabilise tout)
  └─ Axe 4 : Report modal Vélov ↔ TC

Priorité 3 (avancé) :
  ├─ Axe 2 : Propagation congestion (causalité)
  └─ Axe 7 : Météo interaction (analytique)
```

**Estimation effort** :

| Axe | Effort | Pré-requis |
|-----|--------|-----------|
| Axe 1 — Grille multimodale | 1 jour | Aucun |
| Axe 3 — Bus × trafic spatial | 0.5 jour | Aucun |
| Axe 5 — Score santé | 0.5 jour | Aucun |
| Axe 6 — Qualité données | 1 jour | Aucun |
| Axe 4 — Report modal | 1 jour | PostGIS ST_DWithin (déjà utilisé migration 14) |
| Axe 2 — Propagation | 1.5 jours | `gold.dim_gnn_adjacency` peuplé |
| Axe 7 — Météo interaction | 0.5 jour | 30 jours d'historique météo |

---

## 13. Sources académiques et techniques

### Recherche état de l'art (2024-2026)

- [FusionTransNet: Spatiotemporal Traffic Forecasting Through Multimodal Network Integration](https://arxiv.org/pdf/2405.05786) — fusion multi-sources pour prédiction trafic
- [Cascading failure and recovery propagation of metro-bus double-layer network](https://www.sciencedirect.com/science/article/abs/pii/S1361920924005285) — modèle cascading failure bus ↔ métro sous charge passagers variable
- [STGC-GNNs: GNN with spatial-temporal Granger causality graph](https://arxiv.org/abs/2210.16789) — utiliser la causalité Granger comme matrice d'adjacence du GNN
- [Convergent Cross-Mapping for congestion spatial causality](https://onlinelibrary.wiley.com/doi/10.1111/mice.13334) — méthode 2025 non-linéaire pour causalité spatiale trafic
- [Time delay estimation of traffic congestion propagation](https://arxiv.org/pdf/2108.06717) — estimation lag de propagation entre segments
- [Real-time bus arrival delays using SUR model](https://link.springer.com/article/10.1007/s11116-024-10507-3) — corrélation retards bus entre arrêts consécutifs
- [Bike-sharing demand prediction with GNN and spatial aggregation](https://www.sciencedirect.com/science/article/pii/S2210670725003555) — prédiction demande vélo partagé par GNN
- [Demand prediction for shared bicycles around metro stations (STAGCN)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0328452) — lien vélo ↔ métro via GCN spatio-temporel
- [Multi-modal data fusion and explainable AI for smart traffic flow prediction](https://www.sciencedirect.com/science/article/pii/S1110866526001222) — fusion multi-modale + XAI
- [A data-driven framework for measuring multimodal transport success](https://www.nature.com/articles/s41598-026-43179-3) — métriques succès transport multimodal (Dubaï 2026)
- [Cascading failures and resilience in urban road traffic networks](https://www.sciencedirect.com/science/article/abs/pii/S0378437125001086) — résilience réseau routier sous failure cascade

### Code source récupéré (LyonTraffic)

- `scripts/create_multimodal_view.py` — vue `gold.multimodal_status_grid` (FULL OUTER JOIN grille 0.01°)
- `dashboard/pages/7_Synergie_Multimodale.py` — carte chaleur + simulateur éco-mobilité
- `src/transformation/data_quality.py` — module `QualityConfig` + `QualityReport`
- `docs/archive_historique/IMPACT_ANALYSIS.md` — analyse d'impact prédictions pré-calculées

---

## Annexe A — Schéma d'interdépendances

```
                    ┌──────────────┐
                    │   MÉTÉO      │
                    │ (exogène)    │
                    └──────┬───────┘
                           │ impacte
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ TRAFIC   │ │   TC     │ │  VÉLOV   │
       │ ROUTIER  │ │ (bus/    │ │          │
       │          │ │ tram/    │ │          │
       │          │ │ métro)   │ │          │
       └────┬─────┘ └────┬─────┘ └────┬─────┘
            │             │            │
            ├─────────────┤            │
            │  Axe 3      │            │
            │  bus ↔       │            │
            │  trafic      │            │
            │  (spatial)   │            │
            │             ├────────────┤
            │             │  Axe 4     │
            │             │  TC ↔ vélov│
            │             │  (report)  │
            │             │            │
       ┌────▼─────────────▼────────────▼────┐
       │        GRILLE MULTIMODALE           │
       │       (Axe 1 — fusion)              │
       │  score = f(trafic, TC, vélov, météo)│
       └────────────────┬───────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  SCORE SANTÉ    │
              │  RÉSEAU (Axe 5) │
              │  0-100          │
              └─────────────────┘
```

## Annexe B — Tables/vues existantes utilisées

| Table/vue | Schéma | Colonnes clés | Refresh |
|-----------|--------|---------------|---------|
| `gold.traffic_features_live` | gold | `channel_id, speed_kmh, lat, lon, fetched_at` | */5 min |
| `gold.tcl_vehicle_realtime` | gold | `vehicle_ref, line_ref, latitude, longitude, delay_seconds, is_delayed, recorded_at` | */5 min |
| `silver.velov_clean` | silver | `station_id, lat, lon, num_bikes_available, num_docks_available, fetched_at` | */5 min |
| `silver.meteo_hourly` | silver | `measurement_time, temperature_2m, precipitation` | */1h |
| `gold.dim_gnn_adjacency` | gold | `source_node, target_node` | 1×/jour |
| `gold.bus_delay_segments` | gold | `line_ref, hour, date, avg_delay_seconds, n_observations` | */15 min |
| `gold.infrastructure_bottlenecks` | gold | `segment_id, line_ref, diagnosis, bus_delay_seconds, traffic_speed_kmh` | */15 min |
| `gold.v_coherence_tomtom_vs_grandlyon` | gold | `tile_key, channel_id, delta_kmh, status` | Vue live |
| `referentiel.lieux_transports` | referentiel | `lieu_id, line_ref, lat, lon` | Mensuel |
