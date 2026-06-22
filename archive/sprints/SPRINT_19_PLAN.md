# Sprint 19 — Plan d'exécution

> **Date** : 2026-06-22
> **Version cible** : v0.10.1 (patch) — v0.11.0 si nouveau scope
> **Branche** : `vps`
> **Auteur** : Patrice DUCLOS / Mavis

---

## Objectifs

> **⚠️ Note 2026-06-22** : ce plan a été rédigé le 2026-06-22 alors que
> **B.1 (Axe 4) et B.2 (Axe 7) étaient déjà livrés au Sprint 17 v0.9.0**
> (2026-06-20). Le sprint 17 a déjà commité migrations 022/023, widgets,
> DAGs de refresh, et câblage dans `Pro_3_Correlation.py`. Voir
> `CHANGELOG.md` et `archive/sprints/SPRINT_17_REPORT.md` (à créer).
>
> **Sprint 19 = comblement de la dette** : tests manquants sur les widgets
> Axe 4/7 + cleanup cosmétique (ruff + force_mock docstrings) +
> déploiement VPS du Sprint 18.

Sprint 19 comporte **trois volets** :

1. **Volet A — Déploiement VPS Sprint 18** (pgRouting) — ~1h (Patrice en SSH)
2. **Volet B — Cleanup + tests manquants** — ~30 min
   * **B.1 Axe 4** : ⚠️ **DÉJÀ LIVRÉ Sprint 17 v0.9.0** (migration 023 + widget + DAG + câblage)
   * **B.2 Axe 7** : ⚠️ **DÉJÀ LIVRÉ Sprint 17 v0.9.0** (migration 022 + widget + DAG + câblage)
   * **B.3 Ruff cleanup** : 24 → 0 erreurs (17 auto + 7 manuelles)
   * **B.4 force_mock cleanup** : 4 fichiers (docstrings/commentaires historiques)
   * **B.5 Tests manquants** : 47 tests pour `meteo_impact.py` (23) et `modal_shift_alert.py` (24)
3. **Volet C — MAJ doc** : SPRINT_19_PLAN.md (ce fichier) + CHANGELOG/CLAUDE.md

Le volet A est un pré-requis pour tag v0.10.0 (tag = "ça marche en prod", pas "c'est commité").

---

## Volet A — Déploiement VPS pgRouting (Sprint 18)

### Contexte

Sprint 18 livré en local (7 commits sur `vps` ahead de `origin/vps`,
2 commits de plus que les 6 annoncés initialement : `eea9d16` est le
fix SIM117 dans `test_pgrouting.py`). Reste 4 items VPS décrits dans
`docs/NEXT_STEPS_PGROUTING.md`.

### Check-list VPS (ordre strict)

#### A.1 — Backup DB (~5 min)

```bash
ssh lyonflow@51.83.159.224
cd /opt/lyonflow

# Backup offsite AVANT toute migration
make backup-offsite
```

#### A.2 — Push + pull code (~5 min)

```bash
# Local
git push origin vps

# VPS
ssh lyonflow@51.83.159.224
cd /opt/lyonflow
git pull origin vps
```

#### A.3 — Migration 028 — fix mv_sensor_to_way (CRITIQUE, ~10 min)

**Pourquoi c'est critique** : sans cette migration, `osm.mv_sensor_to_way` est vide → `refresh_traffic_costs()` ne met à jour aucune arête → le routing utilise `cost_default` (maxspeed OSM fixe, pas le trafic temps réel).

**Root cause** : `mv_twgid_to_lyo.properties_twgid` contient le format ancien (`"537"`) alors que `dim_spatial_grid_mapping.properties_twgid` contient maintenant `"LYO02236"`. La migration 028 bypass toute la chaîne et va directement depuis `traffic_features_live` (qui a `channel_id` LYO + `lat` + `lon`).

```bash
# Exécuter la migration
psql -U $POSTGRES_USER -d lyonflow -f scripts/sql/migration_028_fix_sensor_to_way.sql
```

**Vérifications** :

```sql
-- Doit retourner ~1100 capteurs
SELECT COUNT(*) FROM osm.sensor_positions;

-- Doit retourner ~2000-5000 arêtes mappées
SELECT COUNT(*) FROM osm.mv_sensor_to_way;

-- Doit retourner > 0 (arêtes mises à jour avec vitesses réelles)
SELECT osm.refresh_traffic_costs();

-- Les vitesses doivent VARIER (pas toutes 50 ou 30)
SELECT road_name, speed_kmh
FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607)
LIMIT 10;
```

#### A.4 — Unpause DAG refresh_osm_traffic_costs (~2 min)

```bash
# Via CLI Airflow
docker exec -it lyonflow-airflow-scheduler-1 \
    airflow dags unpause refresh_osm_traffic_costs

# Ou via Airflow UI : http://51.83.159.224:8080 → DAGs → refresh_osm_traffic_costs → toggle ON
```

Vérifier qu'un run passe (vert, ~20s).

#### A.5 — Benchmark perfo (~10 min)

```sql
\timing on

-- Court (Part-Dieu → Bellecour, ~2 km)
SELECT COUNT(*) FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607);

-- Moyen (Vieux Lyon → Bron, ~6 km)
SELECT COUNT(*) FROM osm.route_car(4.8058, 45.7798, 4.8700, 45.7310);

-- Long (Écully → Vénissieux, ~12 km)
SELECT COUNT(*) FROM osm.route_car(4.7720, 45.7800, 4.9200, 45.7200);
```

**Cible** : p95 < 150ms. Si trop lent :

```sql
-- Index optionnel sur le coût
CREATE INDEX IF NOT EXISTS idx_ways_cost ON osm.ways (cost) WHERE cost > 0;
```

#### A.6 — Tag v0.10.0

```bash
git tag v0.10.0
git push origin v0.10.0
```

---

## Volet B — Développement Sprint 19

### B.1 — Axe 4 : Report modal Vélov ↔ TC

> **⚠️ DÉJÀ LIVRÉ AU SPRINT 17 v0.9.0 (2026-06-20)** — voir
> `archive/sprints/SPRINT_17_REPORT.md` (à créer) ou CHANGELOG.md.
>
> Fichiers livrés :
> * `scripts/sql/migration_023_velov_transit_coupling.sql` (Sprint 17 v3 : pivot
>   vers `gold.tcl_vehicle_realtime` car `referentiel.lieux_transports` n'a
>   pas de lat/lon ; DISTINCT ON pour gérer les doublons 12%)
> * `dags/maintenance/refresh_velov_transit_coupling.py` (*/15 min)
> * `dashboard/components/widgets/pro_tcl/modal_shift_alert.py` (232 l.)
> * Helpers `db_query.py` + `data_loader.py`
> * Câblage `Pro_3_Correlation.py` l.149-154
>
> **Tests Sprint 19** (cf. B.5) : 24 tests unitaires sur
> `modal_shift_alert.py` (constantes, `_format_z_score`,
> `_count_anomalies`, `_count_critical_lines`).

#### Spec d'origine (pour mémoire)

#### Concept

Quand un incident TC survient (métro A en panne, tram T1 interrompu), les usagers se reportent sur Vélov. Effet mesurable : stations Vélov proches des arrêts TC impactés se vident anormalement vite.

**Détection** : z-score sur la disponibilité Vélov par station × ligne TC. Si `z < -2` (2 écarts-types en dessous de la moyenne horaire sur 7 jours), c'est anormal.

#### Migration SQL (migration_029)

```sql
-- scripts/sql/migration_029_velov_transit_coupling.sql

CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_velov_transit_coupling AS
WITH
-- Stations Vélov proches d'arrêts TC (JOIN spatial < 300m)
velov_near_transit AS (
    SELECT DISTINCT
        v.station_id AS velov_station_id,
        v.name AS velov_name,
        lt.line_ref,
        lt.lieu_name AS transit_stop,
        ST_Distance(
            ST_SetSRID(ST_MakePoint(v.lon, v.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(lt.lon, lt.lat), 4326)::geography
        )::numeric(8,1) AS distance_m
    FROM silver.velov_clean v
    JOIN referentiel.lieux_transports lt
        ON ST_DWithin(
            ST_SetSRID(ST_MakePoint(v.lon, v.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(lt.lon, lt.lat), 4326)::geography,
            300  -- mètres
        )
    WHERE v.fetched_at = (SELECT MAX(fetched_at) FROM silver.velov_clean)
),
-- Baseline horaire (rolling 7 jours)
velov_hourly AS (
    SELECT
        vnt.velov_station_id,
        vnt.line_ref,
        EXTRACT(HOUR FROM vc.fetched_at)::int AS hour,
        AVG(vc.num_bikes_available)::numeric(6,2) AS avg_bikes,
        STDDEV(vc.num_bikes_available)::numeric(6,2) AS std_bikes,
        COUNT(*) AS n_obs
    FROM velov_near_transit vnt
    JOIN silver.velov_clean vc ON vc.station_id = vnt.velov_station_id
    WHERE vc.fetched_at > NOW() - INTERVAL '7 days'
    GROUP BY vnt.velov_station_id, vnt.line_ref,
             EXTRACT(HOUR FROM vc.fetched_at)::int
),
-- Disponibilité actuelle
velov_now AS (
    SELECT DISTINCT ON (station_id)
        station_id AS velov_station_id,
        num_bikes_available AS bikes_now,
        fetched_at
    FROM silver.velov_clean
    WHERE fetched_at > NOW() - INTERVAL '15 minutes'
    ORDER BY station_id, fetched_at DESC
)
SELECT
    vh.velov_station_id,
    vnt.velov_name,
    vh.line_ref AS transit_line,
    vnt.transit_stop,
    vnt.distance_m,
    vh.hour,
    vh.avg_bikes AS baseline_bikes,
    vh.std_bikes,
    vh.n_obs,
    vn.bikes_now,
    CASE WHEN vh.std_bikes > 0
         THEN ((vn.bikes_now - vh.avg_bikes) / vh.std_bikes)::numeric(4,2)
         ELSE 0
    END AS z_score,
    CASE WHEN vh.std_bikes > 0
          AND (vn.bikes_now - vh.avg_bikes) / vh.std_bikes < -2
         THEN TRUE
         ELSE FALSE
    END AS anomaly_detected
FROM velov_hourly vh
JOIN velov_now vn ON vn.velov_station_id = vh.velov_station_id
JOIN velov_near_transit vnt ON vnt.velov_station_id = vh.velov_station_id
    AND vnt.line_ref = vh.line_ref
WHERE vh.hour = EXTRACT(HOUR FROM NOW())::int;

CREATE INDEX IF NOT EXISTS idx_velov_transit_coupling_anomaly
    ON gold.mv_velov_transit_coupling (anomaly_detected)
    WHERE anomaly_detected = TRUE;

-- Refresh concurrently (DAG */15 min)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_velov_transit_coupling;
```

#### Helpers Python

**`src/data/db_query.py`** — 2 fonctions :

```python
def get_velov_transit_coupling(conn) -> list[dict]:
    """Couplage Vélov ↔ TC avec z-score et anomalies."""
    sql = """
        SELECT velov_station_id, velov_name, transit_line, transit_stop,
               distance_m, baseline_bikes, bikes_now, z_score, anomaly_detected
        FROM gold.mv_velov_transit_coupling
        ORDER BY z_score ASC
    """
    return _fetch_dicts(conn, sql)


def get_velov_transit_anomalies(conn) -> list[dict]:
    """Stations Vélov en anomalie (z < -2) par ligne TC."""
    sql = """
        SELECT transit_line,
               COUNT(*) AS n_anomalies,
               ARRAY_AGG(velov_name ORDER BY z_score) AS stations,
               MIN(z_score) AS worst_z
        FROM gold.mv_velov_transit_coupling
        WHERE anomaly_detected = TRUE
        GROUP BY transit_line
        ORDER BY n_anomalies DESC
    """
    return _fetch_dicts(conn, sql)
```

**`src/data/data_loader.py`** — wrappers fail-loud :

```python
def load_velov_transit_coupling() -> list[dict]:
    return _load_from_db(get_velov_transit_coupling, "mv_velov_transit_coupling")

def load_velov_transit_anomalies() -> list[dict]:
    return _load_from_db(get_velov_transit_anomalies, "mv_velov_transit_coupling")
```

#### Widget `modal_shift_alert.py`

Emplacement : `dashboard/components/widgets/pro_tcl/modal_shift_alert.py`
Câblage : `Pro_3_Correlation.py` (sous la matrice bus × trafic)

```python
def render_modal_shift_alert():
    """Alerte report modal Vélov ↔ TC.

    Détecte les stations Vélov anormalement vides à proximité d'arrêts TC.
    Z-score < -2 sur la moyenne horaire 7 jours = anomalie.
    """
    anomalies = cached_velov_transit_anomalies()
    coupling = cached_velov_transit_coupling()

    # KPI cards
    col1, col2, col3 = st.columns(3)
    n_anomalies = sum(1 for c in coupling if c["anomaly_detected"])
    n_lines_impacted = len(anomalies)
    worst_z = min((c["z_score"] for c in coupling), default=0)

    col1.metric("Anomalies Vélov", n_anomalies,
                delta_color="inverse")
    col2.metric("Lignes TC impactées", n_lines_impacted)
    col3.metric("Pire z-score", f"{worst_z:.1f}")

    if not anomalies:
        st.success("Aucune anomalie détectée — réseau nominal.")
        return

    # Tableau anomalies par ligne TC
    st.subheader("Report modal détecté")
    for a in anomalies:
        with st.expander(
            f"🚌 {a['transit_line']} — {a['n_anomalies']} station(s) anormale(s)"
        ):
            st.write(f"**Stations vides** : {', '.join(a['stations'])}")
            st.write(f"**Pire z-score** : {a['worst_z']:.2f}")
            st.caption(
                "z < -2 = disponibilité Vélov significativement inférieure "
                "à la moyenne horaire (7 jours). Probable report modal."
            )

    # Scatter z-score par station
    if coupling:
        df = pd.DataFrame(coupling)
        fig = px.scatter(
            df, x="baseline_bikes", y="bikes_now",
            color="anomaly_detected",
            color_discrete_map={True: "red", False: "steelblue"},
            hover_data=["velov_name", "transit_line", "z_score"],
            labels={
                "baseline_bikes": "Baseline (moy. 7j, même heure)",
                "bikes_now": "Vélos dispo maintenant",
            },
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=30, y1=30,
                      line=dict(dash="dot", color="gray"))
        st.plotly_chart(fig, use_container_width=True)
```

#### Tests

Fichier : `tests/widgets/test_modal_shift_alert.py`

```python
# Tests clés :
# 1. z_score calcul correct (bikes_now=2, avg=10, std=3 → z=-2.67)
# 2. anomaly_detected=True si z < -2
# 3. anomaly_detected=False si z >= -2
# 4. std_bikes=0 → z_score=0 (pas de division par zéro)
# 5. n_anomalies=0 → st.success affiché
# 6. Groupement par transit_line correct
# 7. Scatter plot avec ligne y=x
```

**Estimation** : ~15 tests.

#### DAG refresh

Dans `dags/transforms/` ou `dags/maintenance/` — refresh `*/15 min` :

```python
# REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_velov_transit_coupling;
```

Ajouté au DAG `transform_silver_to_gold` ou en DAG standalone léger.

---

### B.2 — Axe 7 : Météo comme variable d'interaction

> **⚠️ DÉJÀ LIVRÉ AU SPRINT 17 v0.9.0 (2026-06-20)** — voir
> `archive/sprints/SPRINT_17_REPORT.md` (à créer) ou CHANGELOG.md.
>
> Fichiers livrés :
> * `scripts/sql/migration_022_meteo_impact.sql`
> * `dags/maintenance/refresh_meteo_impact.py` (1×/jour 04h30)
> * `dashboard/components/widgets/pro_tcl/meteo_impact.py` (280 l.)
> * Helpers `db_query.py` + `data_loader.py`
> * Câblage `Pro_3_Correlation.py` l.135-140
>
> **Tests Sprint 19** (cf. B.5) : 23 tests unitaires sur
> `meteo_impact.py` (constantes, `_format_delta_*`, `_find_worst_band`).

#### Spec d'origine (pour mémoire)

#### Concept

La météo est déjà une feature ML (XGBoost : `temperature_2m`, `precipitation`). Mais on ne l'utilise pas pour **expliquer** les interdépendances. Sprint 19 crée une vue matérialisée qui quantifie l'impact de chaque condition météo sur chaque mode.

#### Table d'impact attendu (à valider vs données réelles)

| Condition | Trafic Δ vitesse | TC Δ retard | Vélov Δ dispo |
|-----------|-----------------|-------------|---------------|
| 🌧 Pluie forte (>5mm/h) | -20 à -40% | +30% | -60% |
| 🌦 Pluie légère (1-5mm) | -10% | +10% | -30% |
| ❄ Gel (<0°C) | -15% | +20% | -80% |
| 🔥 Canicule (>35°C) | ~0 | +5% | -20% |
| ☀ Beau temps | baseline | baseline | baseline |

#### Migration SQL (migration_030)

```sql
-- scripts/sql/migration_030_meteo_impact.sql

CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_meteo_impact AS
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
    JOIN meteo_bands mb
        ON DATE_TRUNC('hour', tf.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
),
tcl_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(tr.delay_seconds)::numeric(8,2) AS avg_delay,
        STDDEV(tr.delay_seconds)::numeric(8,2) AS std_delay,
        COUNT(*) AS n_obs
    FROM gold.tcl_vehicle_realtime tr
    JOIN meteo_bands mb
        ON DATE_TRUNC('hour', tr.recorded_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
),
velov_by_meteo AS (
    SELECT
        mb.meteo_band,
        AVG(vc.num_bikes_available)::numeric(6,2) AS avg_bikes,
        STDDEV(vc.num_bikes_available)::numeric(6,2) AS std_bikes,
        COUNT(*) AS n_obs
    FROM silver.velov_clean vc
    JOIN meteo_bands mb
        ON DATE_TRUNC('hour', vc.fetched_at) = DATE_TRUNC('hour', mb.measurement_time)
    GROUP BY mb.meteo_band
)
SELECT
    t.meteo_band,
    t.avg_speed AS traffic_avg_speed,
    t.std_speed AS traffic_std_speed,
    t.n_obs AS traffic_obs,
    (t.avg_speed - fair_t.avg_speed)::numeric(6,2) AS traffic_delta_vs_fair,
    c.avg_delay AS tcl_avg_delay_sec,
    c.std_delay AS tcl_std_delay,
    c.n_obs AS tcl_obs,
    (c.avg_delay - fair_c.avg_delay)::numeric(8,2) AS tcl_delay_delta_vs_fair,
    v.avg_bikes AS velov_avg_bikes,
    v.std_bikes AS velov_std_bikes,
    v.n_obs AS velov_obs,
    (v.avg_bikes - fair_v.avg_bikes)::numeric(6,2) AS velov_delta_vs_fair
FROM traffic_by_meteo t
LEFT JOIN tcl_by_meteo c ON c.meteo_band = t.meteo_band
LEFT JOIN velov_by_meteo v ON v.meteo_band = t.meteo_band
CROSS JOIN (SELECT avg_speed FROM traffic_by_meteo WHERE meteo_band = 'fair') fair_t
CROSS JOIN (SELECT avg_delay FROM tcl_by_meteo WHERE meteo_band = 'fair') fair_c
CROSS JOIN (SELECT avg_bikes FROM velov_by_meteo WHERE meteo_band = 'fair') fair_v;
```

> **Note** : `LEFT JOIN` au lieu de `INNER JOIN` (spec originale) pour éviter de perdre des bandes météo si un mode n'a pas de données pour cette bande. Ex : gel rare à Lyon → `frost` pourrait n'avoir que des obs trafic.

#### Helpers Python

**`src/data/db_query.py`** :

```python
def get_meteo_impact(conn) -> list[dict]:
    """Impact météo par mode (delta vs beau temps baseline)."""
    sql = """
        SELECT meteo_band,
               traffic_avg_speed, traffic_delta_vs_fair, traffic_obs,
               tcl_avg_delay_sec, tcl_delay_delta_vs_fair, tcl_obs,
               velov_avg_bikes, velov_delta_vs_fair, velov_obs
        FROM gold.mv_meteo_impact
        ORDER BY CASE meteo_band
            WHEN 'heavy_rain' THEN 1
            WHEN 'light_rain' THEN 2
            WHEN 'frost'      THEN 3
            WHEN 'heatwave'   THEN 4
            WHEN 'fair'       THEN 5
        END
    """
    return _fetch_dicts(conn, sql)
```

#### Widget `meteo_impact.py`

Emplacement : `dashboard/components/widgets/pro_tcl/meteo_impact.py`
Câblage : `Pro_3_Correlation.py` (section "Impact météo")

Le widget affiche :
- **Bar chart groupé** (Plotly) : 5 bandes météo × 3 deltas (trafic, TC, Vélov)
- **Tableau récapitulatif** avec emojis météo + couleurs conditionnelles
- **KPI** : condition météo actuelle + son impact estimé

```python
_METEO_LABELS = {
    "heavy_rain": "🌧 Pluie forte",
    "light_rain": "🌦 Pluie légère",
    "frost": "❄ Gel",
    "heatwave": "🔥 Canicule",
    "fair": "☀ Beau temps",
}
```

#### Tests

Fichier : `tests/widgets/test_meteo_impact.py`

```python
# Tests clés :
# 1. 5 bandes météo présentes
# 2. fair baseline = delta 0
# 3. heavy_rain → traffic_delta_vs_fair < 0 (vitesse baisse)
# 4. heavy_rain → tcl_delay_delta_vs_fair > 0 (retard augmente)
# 5. heavy_rain → velov_delta_vs_fair < 0 (dispo baisse)
# 6. LEFT JOIN : bande sans données → NULL (pas crash)
# 7. _METEO_LABELS couvre les 5 bandes
```

**Estimation** : ~10 tests.

#### DAG refresh

`1×/jour 04h30` (lourd : 30 jours × 3 JOINs). Ajouté au DAG `data_quality_daily` ou standalone.

---

### B.3 — Ruff cleanup cosmétique ✅ LIVRÉ (Sprint 19, 2026-06-22)

**24 → 0 erreurs ruff.** Pas de changement de logique.

* **20 auto-fixées** via `ruff check . --fix` :
  * 7× I001 (imports non triés)
  * UP035, UP037, UP017 (typing modernization)
  * 2× F811 (redefinition of `pd`)
  * 4× RUF100 (unused `noqa`)
  * etc.
* **4 fixées manuellement** :
  * `scripts/migrate_font_size_to_lyf.py:92: SIM108` → ternary
  * `scripts/migrate_font_size_to_lyf.py:121: N806` → `BLACKLIST` → `blacklist`
  * `tests/monitoring/test_evidently_configuration.py:307: RUF059` → `_msg` (msg unused)
  * `tests/persona/test_drift_badge.py:64: RUF059` → `_icon` (icon unused)
  * `tests/persona/test_real_durations.py:58: SIM115` → `with open(...) as f:`

Commande : `ruff check .` retourne `All checks passed!`.

---

### B.4 — Cleanup dette `force_mock` ✅ LIVRÉ (Sprint 19, 2026-06-22)

4 fichiers nettoyés (commentaires/docstrings historiques mentionnant
`_is_demo_mode` / `DEMO_MODE`, helper déprécié depuis Sprint 8) :

| Fichier | Avant | Après |
|---------|-------|-------|
| `src/data/exceptions.py` | docstring mentionnait "mode production vs mode démo" | docstring explique fail loud + "zéro mock" |
| `src/ml/mlflow_integration.py` | "Note: Mode démo (LYONFLOW_DEMO_MODE=1)" dans `list_experiments()` | "Raises: DashboardDataError si MLflow indispo" |
| `pro_tcl/model_monitoring.py` | "Helper _is_demo_mode() viré" dans la docstring module | Mention retirée |
| `pro_tcl/pipeline_management.py` | 3 commentaires "Sprint 9+ — viré la branche _is_demo_mode()" | Commentaires retirés (3 endroits : module docstring + render_pipeline_status + render_health_panel) |

Zéro changement de logique — uniquement du nettoyage docstrings/commentaires.

### B.5 — Tests manquants pour widgets Sprint 17 ✅ LIVRÉ (Sprint 19, 2026-06-22)

Les widgets `meteo_impact.py` et `modal_shift_alert.py` livrés au Sprint 17
n'avaient **aucun test unitaire**. Sprint 19 comble ce trou.

| Fichier | Tests | Couverture |
|---------|-------|------------|
| `tests/widgets/test_meteo_impact.py` | **23** | constantes (5 bandes, emoji, hex), `_format_delta_traffic`/`_format_delta_tcl`/`_format_delta_velov` (NaN, zéro, ±), `_find_worst_band` (df vide, pas de non-fair, modes traffic/tcl/velov) |
| `tests/widgets/test_modal_shift_alert.py` | **24** | constantes (3 niveaux, seuil -2.0, emoji, hex), `_format_z_score` (None, NaN, 4 paliers), `_count_anomalies` (5 cas), `_count_critical_lines` (6 cas) |

**Total B.5** : 47 tests verts. Pas de mock de Streamlit — tests sur les
fonctions pures avec DataFrames synthétiques, conforme au pattern de
`tests/widgets/test_propagation_map.py`.

---

## Résumé des livrables Sprint 19 (état réel 2026-06-22)

| Item | Statut | Type | Fichiers touchés | Tests |
|------|--------|------|------------------|-------|
| **A. VPS pgRouting** | 🟡 en cours (Patrice SSH) | deploy | 0 nouveau (push existant 7 commits) | bench SQL |
| **B.1 Axe 4 — Report modal** | ✅ DÉJÀ LIVRÉ Sprint 17 | feat (legacy) | migration_023 + widget + DAG + câblage | +24 (B.5) |
| **B.2 Axe 7 — Météo impact** | ✅ DÉJÀ LIVRÉ Sprint 17 | feat (legacy) | migration_022 + widget + DAG + câblage | +23 (B.5) |
| **B.3 Ruff cleanup** | ✅ LIVRÉ Sprint 19 | chore | 6 fichiers (20 auto + 4 manuel) | 0 (cosmétique) |
| **B.4 force_mock cleanup** | ✅ LIVRÉ Sprint 19 | chore | 4 fichiers docstrings | 0 (commentaires) |
| **B.5 Tests manquants** | ✅ LIVRÉ Sprint 19 | test | 2 nouveaux fichiers `tests/widgets/test_*.py` | +47 |

**Total Sprint 19** (en local, à commit) :
* 6 fichiers chore (B.3 + B.4)
* 2 fichiers tests (B.5)
* 1 fichier doc (SPRINT_19_PLAN.md MAJ)
* **+47 tests verts** (507 → 507+47=507, mais avant le sprint 19 c'était 460, donc delta réel = +47)

**Tests totaux** : 507 passed, 4 skipped, 20 deselected, 0 failed.

---

## Ordre d'exécution Sprint 19 (état réel 2026-06-22)

```
Matin (Patrice en SSH) :
  1. Volet A — VPS deploy
     - push 7 commits Sprint 18 origin/vps
     - ssh VPS, git pull
     - psql migration_028 + vérif mv_sensor_to_way > 0
     - airflow dags unpause refresh_osm_traffic_costs
     - bench 3 routes (p95 < 150ms)
     - retour Mavis avec OK

Matin (Mavis en local) :
  2. B.3 ruff --fix (5 min)        ✅ FAIT
  3. B.4 cleanup force_mock (15 min) ✅ FAIT
  4. B.5 tests meteo_impact + modal_shift_alert (1h) ✅ FAIT
  5. MAJ SPRINT_19_PLAN.md (10 min) ✅ FAIT

Après VPS OK :
  6. Commit chore(sprint19) (Patrice : push après merge éventuel)
  7. Tag v0.10.0 (Patrice, après validation prod)
```

---

## Critères de succès Sprint 19

### Volet A (VPS, Patrice)
- [ ] VPS : `SELECT COUNT(*) FROM osm.mv_sensor_to_way` > 0 (~41 737 attendu)
- [ ] VPS : `SELECT road_name, speed_kmh FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607) LIMIT 10;` → vitesses variées
- [ ] VPS : DAG `refresh_osm_traffic_costs` unpausé, 1er run vert ~20s
- [ ] VPS : bench p95 < 150ms (3 routes : court/moyen/long)
- [ ] Tag v0.10.0 posé après validation prod

### Volet B (local, Mavis)
- [x] Ruff : 0 erreur (`All checks passed!`)
- [x] 4 fichiers force_mock nettoyés
- [x] 47 nouveaux tests verts (23 meteo_impact + 24 modal_shift_alert)
- [x] 507 tests passed, 0 failed, 0 régression
- [x] SPRINT_19_PLAN.md mis à jour (B.1/B.2 marqués DÉJÀ LIVRÉS Sprint 17)

### Commit final
- [ ] `chore(sprint19): cleanup ruff + force_mock docstrings + tests manquants Axes 4+7`
- [ ] Push sur `origin/vps` (Patrice) après validation Volet A prod
