# SPEC — Fix Elu_2_Bottlenecks (9 bugs)

> **Contexte** : La page `Elu_2_Bottlenecks.py` ("Bottlenecks prioritaires — Investissements") affiche des données économiques (gain, coût, ROI, délai) qui sont **100% synthétiques** — fonctions linéaires de la position dans une boucle Python. La carte ne rend **aucun marqueur**. Le diagnostic SQL (seul signal réel) est calculé puis jeté avant l'affichage.
>
> **Objectif** : Brancher le dashboard sur les vraies données DB, utiliser la vue matérialisée spatiale existante (`gold.mv_bus_traffic_spatial`), et afficher les coordonnées GPS réelles.
>
> **Branche** : `vps` (branche active de production)
>
> **Contraintes projet** :
> - SQL paramétré partout (`psycopg2 %s`), zéro f-string SQL
> - Zéro mock dans le projet — `DashboardDataError` si DB indispo
> - Zéro credential dans le code — tout via `os.getenv()`
> - Tests : `pytest tests/ -v --tb=short`
> - Lint : `ruff check . && ruff format --check .`

---

## Diagramme pipeline actuel

```
_BOTTLENECK_SQL (silver_to_gold.py:398)
  → DELETE + INSERT gold.infrastructure_bottlenecks (*/10 min, DAG transform_silver_to_gold)
    → get_bottlenecks_summary() (db_query.py:545)  [SQL SELECT]
      → load_bottlenecks_summary() (data_loader.py:445)
        → load_bottlenecks_top() (data_loader.py:621) ← ⚠️ HARDCODES ICI
          → cached_bottlenecks_top() (data_cache.py)
            → 3 widgets : bottleneck_map, bottleneck_ranking, roi_calculator
```

---

## Bug 1 — Économie 100% synthétique (🔴 CRITIQUE)

### Fichier : `src/data/data_loader.py:644-656`

### État actuel

```python
# Lignes 650-653 dans load_bottlenecks_top()
bottlenecks.append(
    {
        "rank": int(row.get("bottleneck_id", i + 1)),
        "zone": zone,
        "lines_impacted": [lines_impacted_raw] if lines_impacted_raw else [],
        "voyageurs_jour": int(row.get("voyageurs_jour", 5000 + i * 1000)),
        "gain_min": 5 + i,                          # ← HARDCODÉ : 5 à 14
        "cout_M_euros": round(2.5 - i * 0.15, 2),   # ← HARDCODÉ : 2.50 à 1.15
        "roi_mois": 18 + i * 3,                      # ← HARDCODÉ : 18 à 45
        "delai_mois": 6 + i * 2,                     # ← HARDCODÉ : 6 à 24
        "description": f"Amélioration #{i + 1} du bottleneck {zone}",
    }
)
```

Les champs `gain_min`, `cout_M_euros`, `roi_mois`, `delai_mois` sont des fonctions linéaires de l'index `i` de la boucle. Aucune donnée DB derrière.

### Fix attendu

Remplacer les 4 champs hardcodés par des **estimations data-driven** dérivées des colonnes DB réellement disponibles. Colonnes disponibles dans le DataFrame `row` (cf. `get_bottlenecks_summary()` lignes 575-590) :

| Colonne DB | Alias DataFrame | Type |
|---|---|---|
| `bus_delay_seconds` | `avg_bus_delay_s` | numeric(8,2) — secondes |
| `traffic_speed_kmh` | `avg_traffic_speed_kmh` | numeric(8,2) — km/h |
| `traffic_congestion` | `traffic_congestion` | numeric(4,3) — ratio 0.0-1.0 |
| `n_observations` | `voyageurs_jour` | int — nb observations bus |
| `diagnosis` | `diagnosis` | text — 'infra' / 'operations' / 'bus_lane_ok' / 'ok' |

**Formules proposées** (à calibrer) :

```python
avg_delay_s = float(row.get("avg_bus_delay_s", 0) or 0)
avg_speed = float(row.get("avg_traffic_speed_kmh", 50) or 50)
congestion = float(row.get("traffic_congestion", 0) or 0)
diagnosis = row.get("diagnosis", "ok")

# gain_min : estimation du gain si le bottleneck est résolu
# Hypothèse : on peut récupérer la moitié du retard bus en améliorant l'infra
gain_min = round(avg_delay_s / 60 * 0.5, 1)  # demi-retard converti en minutes

# cout_M_euros : estimation coût aménagement selon diagnostic
# infra = gros travaux (2-5 M€), operations = ajustement léger (0.5-1 M€)
COUT_PAR_DIAGNOSTIC = {
    "infra": 3.0,
    "operations": 0.8,
    "bus_lane_ok": 0.3,
    "ok": 0.1,
}
cout_M_euros = COUT_PAR_DIAGNOSTIC.get(diagnosis, 1.0)

# roi_mois et delai_mois : calculés depuis gain_annuel (formule ROI existante)
# Pas hardcodés — le calculateur ROI les recalcule de toute façon (Bug 7)
```

**Important** : le `roi_mois` dans le dict était incohérent avec le `roi_mois` recalculé par `roi_calculator.py`. Avec ce fix, **ne plus mettre `roi_mois` ni `delai_mois` en dur**. Laisser le calculateur ROI les dériver.

---

## Bug 2 — Carte affiche ZÉRO marqueur (🔴 CRITIQUE)

### Fichier : `dashboard/components/widgets/elu/bottleneck_map.py:23-51`

### État actuel

```python
# Ligne 23-34 — dict hardcodé de noms de rues
coords = {
    "Rue Garibaldi": (45.7575, 4.8461),
    "Cours Lafayette": (45.7542, 4.8411),
    # ... 8 autres noms de rues
}

# Ligne 48-50 — lookup par zone
for b in bottlenecks:
    zone = b.get("zone", "—")
    if zone not in coords:   # ← zone vaut "L66 ; 20h", JAMAIS "Rue Garibaldi"
        continue              # ← TOUS les bottlenecks sont skippés
```

`zone` provient de `clean_line_label(segment_id)` où `segment_id = line_ref || '_h' || hour`. Résultat : `"L66 ; 20h"`, `"T3 ; 8h"`, etc. Jamais un nom de rue. Le `continue` skippe tout. Carte vide.

### Fix attendu

Utiliser les coordonnées `lat`/`lon` depuis le dict bottleneck (après le fix Bug 6 qui met les vraies coordonnées).

```python
for b in bottlenecks:
    zone = b.get("zone", "—")
    lat = b.get("lat")
    lon = b.get("lon")
    if lat is None or lon is None:
        continue
    # ... rest of marker code using lat, lon
```

**Supprimer** le dict `coords` hardcodé entièrement.

**Ajouter** `lat` et `lon` dans le dict retourné par `load_bottlenecks_top()` (Bug 1 fix).

---

## Bug 3 — JOIN global par heure au lieu de spatial (🟠 MAJEUR)

### Fichier : `src/transformation/silver_to_gold.py:398-443`

### État actuel

```sql
-- Lignes 409-415 : CTE traffic_hourly
traffic_hourly AS (
    SELECT
        EXTRACT(HOUR FROM fetched_at)::int AS hour_of_day,
        AVG(speed_kmh)::numeric(8,2)        AS avg_speed
    FROM gold.traffic_features_live
    WHERE fetched_at > NOW() - INTERVAL '7 days'
    GROUP BY EXTRACT(HOUR FROM fetched_at)::int
)
-- ...
-- Ligne 442 : JOIN par heure globale
FROM bus_hourly bh
LEFT JOIN traffic_hourly th ON th.hour_of_day = bh.hour
```

Le CTE `traffic_hourly` moyenne la vitesse sur **TOUT Lyon** par heure. Le retard du bus L66 à 8h est corrélé au trafic moyen de toute la ville à 8h, pas au trafic de la zone traversée par la L66.

### Fix attendu

La vue matérialisée `gold.mv_bus_traffic_spatial` (migration 018, `scripts/sql/migration_018_bus_traffic_spatial.sql`) **existe déjà** et fait le JOIN spatial correct (résolution 0.001° ≈ 100m). Elle est en production depuis Sprint 15+ (2026-06-19).

**Option A** (recommandée) : Modifier `get_bottlenecks_summary()` dans `db_query.py:575` pour lire `gold.mv_bus_traffic_spatial` au lieu de `gold.infrastructure_bottlenecks`. Adapter le mapping colonnes :

Colonnes disponibles dans `gold.mv_bus_traffic_spatial` :
```
line_ref, hour, lat, lon, bus_delay_sec, bus_observations,
bus_delayed_count, traffic_speed_kmh, traffic_sensors,
diagnosis, traffic_congestion, computed_at
```

Nouveau SQL dans `get_bottlenecks_summary()` :
```sql
SELECT
    ROW_NUMBER() OVER (ORDER BY bus_delay_sec DESC) AS bottleneck_id,
    line_ref || '_h' || hour AS road_name,
    line_ref,
    diagnosis,
    bus_delay_sec AS avg_bus_delay_s,
    traffic_speed_kmh AS avg_traffic_speed_kmh,
    traffic_congestion,
    bus_observations AS n_observations,
    bus_observations AS voyageurs_jour,
    lat, lon AS lng,
    computed_at
FROM gold.mv_bus_traffic_spatial
WHERE diagnosis IN ('infra', 'operations')
ORDER BY bus_delay_sec DESC NULLS LAST
LIMIT %s
```

**Note** : `gold.mv_bus_traffic_spatial` a des coordonnées GPS réelles (arrondies à 0.001°), ce qui résout aussi le Bug 6.

**Option B** (conservative) : Garder `gold.infrastructure_bottlenecks` mais remplacer le SQL de `_BOTTLENECK_SQL` par un équivalent spatial. Plus intrusif car ça touche au pipeline de transformation.

---

## Bug 4 — Diagnostic (seul signal réel) jeté avant affichage (🟠 MAJEUR)

### Fichier : `src/data/data_loader.py:644-656`

### État actuel

`get_bottlenecks_summary()` retourne une colonne `diagnosis` (valeurs : `infra`, `operations`, `bus_lane_ok`, `ok`). Mais `load_bottlenecks_top()` ne l'inclut pas dans le dict passé aux widgets. Le seul calcul data-driven est jeté.

### Fix attendu

Ajouter `"diagnosis"` au dict dans `load_bottlenecks_top()` :

```python
bottlenecks.append(
    {
        # ... existing fields ...
        "diagnosis": row.get("diagnosis", "ok"),
    }
)
```

Et l'afficher dans les widgets :

- **`bottleneck_ranking.py`** : ajouter une colonne "Diagnostic" avec emoji/couleur :
  - `infra` → 🔴 "Infrastructure"
  - `operations` → 🟠 "Opérationnel"
  - `bus_lane_ok` → 🟢 "Voie bus OK"
  - `ok` → ⚪ "OK"

- **`bottleneck_map.py`** : utiliser le diagnostic pour la couleur des marqueurs au lieu du ROI synthétique :
  - `infra` → rouge
  - `operations` → orange
  - `bus_lane_ok` → vert
  - `ok` → gris

- **`roi_calculator.py`** : afficher le diagnostic du bottleneck sélectionné en info.

---

## Bug 5 — n_observations ≠ voyageurs (proxy mislabeled) (🟠 MAJEUR)

### Fichier : `src/data/db_query.py:584`

### État actuel

```sql
n_observations AS voyageurs_jour,
```

`n_observations` = nombre d'observations bus (passages de véhicules captés par SIRI Lite). Ce n'est PAS le nombre de voyageurs par jour. L'alias `voyageurs_jour` est trompeur et fausse tous les calculs ROI en aval.

### Fix attendu

**Option A** (quick) : Renommer l'alias en `obs_jour` et adapter le label dans les widgets pour dire "Observations/j" au lieu de "Voyageurs/j". Honnête sur ce que c'est.

**Option B** (meilleure) : Estimer le nombre de voyageurs à partir des observations. Approximation raisonnable SYTRAL :
```python
# 1 observation ≈ passage d'1 bus. Capacité moyenne bus Lyon : ~80 passagers.
# Taux occupation moyen SYTRAL : ~45%
# voyageurs_estimes = n_observations * 80 * 0.45
voyageurs_jour = int(n_obs * 36)  # 80 * 0.45 = 36
```

Ajouter un commentaire expliquant l'estimation. Et afficher "(estimé)" dans les widgets.

---

## Bug 6 — lat/lon HASHTEXT (faux GPS) (🟡 MOYEN)

### Fichier : `src/transformation/silver_to_gold.py:438-439`

### État actuel

```sql
45.76 + (HASHTEXT(bh.line_ref) % 100) * 0.0002,   -- lat
4.84  + (HASHTEXT(bh.line_ref) % 70)  * 0.0003,    -- lon
```

Coordonnées déterministes mais fausses. Tout concentré dans un rectangle ~200m × 210m.

### Fix attendu

**Si Bug 3 Option A** (lecture de `mv_bus_traffic_spatial`) : les coordonnées sont déjà réelles (arrondies à 0.001° ≈ 100m). Ce bug se résout automatiquement.

**Si Bug 3 Option B** (on garde `gold.infrastructure_bottlenecks`) : modifier `_BOTTLENECK_SQL` pour joindre les positions GPS réelles. Les positions bus sont dans `gold.tcl_vehicle_realtime.latitude/longitude`. Ajouter un CTE :

```sql
bus_centroid AS (
    SELECT
        line_ref,
        AVG(latitude)::numeric(7,4) AS avg_lat,
        AVG(longitude)::numeric(7,4) AS avg_lon
    FROM gold.tcl_vehicle_realtime
    WHERE recorded_at > NOW() - INTERVAL '7 days'
      AND latitude IS NOT NULL
    GROUP BY line_ref
)
```

Et joindre : `LEFT JOIN bus_centroid bc ON bc.line_ref = bh.line_ref` puis utiliser `COALESCE(bc.avg_lat, 45.76)` et `COALESCE(bc.avg_lon, 4.84)`.

---

## Bug 7 — Deux ROI contradictoires (🟡 MOYEN)

### Fichiers : `data_loader.py:652` + `roi_calculator.py:76-77`

### État actuel

**Tableau ranking** affiche `roi_mois = 18 + i * 3` (hardcodé, Bug 1).

**Calculateur ROI** recalcule :
```python
gain_annuel = voyageurs * (gain_min / 60) * valeur_temps * 2 * jours_an
roi_mois = (cout / gain_annuel * 12) if gain_annuel > 0 else 999
```

Les deux ROI sont différents pour le même bottleneck. Incohérence visible par l'utilisateur.

### Fix attendu

**Une seule source de calcul ROI.** Deux approches :

**Option A** (recommandée) : `load_bottlenecks_top()` calcule le ROI avec la formule du calculateur (valeurs par défaut : `valeur_temps=15`, `jours_an=250`). Le tableau ranking affiche ce ROI par défaut. Le calculateur permet de recalculer avec des sliders.

```python
# Dans load_bottlenecks_top(), après avoir dérivé gain_min et cout_M_euros (Bug 1 fix)
DEFAULT_VALEUR_TEMPS = 15  # €/h
DEFAULT_JOURS_AN = 250
gain_annuel = voyageurs * (gain_min / 60) * DEFAULT_VALEUR_TEMPS * 2 * DEFAULT_JOURS_AN
roi_mois = round(cout_M_euros * 1_000_000 / gain_annuel * 12, 1) if gain_annuel > 0 else 999
```

**Option B** : Le tableau ranking n'affiche pas de ROI. Seul le calculateur le montre. Plus simple mais moins informatif au premier coup d'œil.

---

## Bug 8 — DELETE + INSERT complet toutes les 10 min (🟡 MOYEN)

### Fichier : `src/transformation/silver_to_gold.py:446-452`

### État actuel

```python
def _build_infrastructure_bottlenecks() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM gold.infrastructure_bottlenecks")
        cur.execute(_BOTTLENECK_SQL)
```

**Si Bug 3 Option A** (lecture de `mv_bus_traffic_spatial`) : ce code n'est plus sur le chemin critique de Elu_2. La MV est rafraîchie par `REFRESH MATERIALIZED VIEW CONCURRENTLY`. Ce bug devient sans objet.

**Si Bug 3 Option B** : Utiliser `TRUNCATE` au lieu de `DELETE` (plus rapide, pas de dead tuples) + `REFRESH MATERIALIZED VIEW CONCURRENTLY` si conversion en MV. Ou au minimum, envelopper dans une transaction explicite pour éviter la fenêtre "table vide" entre DELETE et INSERT.

### Fix attendu (si Option B)

```python
def _build_infrastructure_bottlenecks() -> int:
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE gold.infrastructure_bottlenecks")
        cur.execute(_BOTTLENECK_SQL)
        n = cur.rowcount
    logger.info("gold.infrastructure_bottlenecks: %d rows upserted", n)
    return n
```

---

## Bug 9 — mv_bus_traffic_spatial existe mais Elu_2 lit l'ancien (🟡 MOYEN)

### Fichier : `src/data/db_query.py:575-590`

### État actuel

```sql
SELECT id AS bottleneck_id,
       segment_id AS road_name,
       -- ...
FROM gold.infrastructure_bottlenecks
ORDER BY bus_delay_seconds DESC NULLS LAST
LIMIT %s
```

La vue matérialisée `gold.mv_bus_traffic_spatial` est en production depuis Sprint 15+ (2026-06-19, ≥ 6 jours). Elle fait le JOIN spatial correct. Mais `get_bottlenecks_summary()` lit toujours l'ancienne table globale.

### Fix attendu

C'est le même fix que Bug 3 Option A. Voir la section Bug 3 pour le nouveau SQL.

---

## Ordre d'implémentation recommandé

Les bugs sont interdépendants. Ordre optimal :

1. **Bug 3 / Bug 9** (switch vers `mv_bus_traffic_spatial`) — résout aussi Bug 6 (lat/lon réels) et Bug 8 (plus de DELETE+INSERT)
2. **Bug 4** (ajouter `diagnosis` au dict)
3. **Bug 1** (remplacer hardcodes par données DB — gain, cout)
4. **Bug 7** (unifier le calcul ROI)
5. **Bug 2** (carte avec vraies coordonnées)
6. **Bug 5** (renommer ou estimer voyageurs)

### Fichiers modifiés (6 fichiers)

| Fichier | Modifications |
|---|---|
| `src/data/db_query.py` | Lignes 575-590 : nouveau SQL lisant `mv_bus_traffic_spatial` |
| `src/data/data_loader.py` | Lignes 644-656 : remplacer hardcodes par dérivation DB |
| `dashboard/components/widgets/elu/bottleneck_map.py` | Supprimer dict coords hardcodé, utiliser lat/lon du dict |
| `dashboard/components/widgets/elu/bottleneck_ranking.py` | Ajouter colonne diagnostic, unifier ROI |
| `dashboard/components/widgets/elu/roi_calculator.py` | Afficher diagnostic, vérifier cohérence ROI |
| `dashboard/pages/Elu_2_Bottlenecks.py` | Mettre à jour caption/footer si wording change |

### Tests à ajouter/modifier

- `tests/data/test_data_loader.py` : vérifier que `load_bottlenecks_top()` retourne `diagnosis`, `lat`, `lon` et pas de hardcodes
- `tests/persona/test_elu_widgets.py` : vérifier que `render_bottleneck_map` ne skippe pas tous les bottlenecks
- `tests/data/test_db_query.py` : vérifier que `get_bottlenecks_summary()` lit `mv_bus_traffic_spatial`

### Vérification post-fix

```bash
# Tests
pytest tests/ -v --tb=short

# Lint
ruff check . && ruff format --check .

# Vérification visuelle (si dashboard accessible)
# 1. Carte : des marqueurs apparaissent aux positions réelles des lignes bus
# 2. Ranking : diagnostic affiché, ROI cohérent avec calculateur
# 3. Calculateur : ROI recalcule en temps réel avec sliders
```

---

## Schéma gold.mv_bus_traffic_spatial (référence)

Source : `scripts/sql/migration_018_bus_traffic_spatial.sql`

```sql
CREATE MATERIALIZED VIEW gold.mv_bus_traffic_spatial AS
-- JOIN spatial 0.001° (≈ 100m) entre positions bus et capteurs trafic
-- Colonnes :
--   line_ref          TEXT     — identifiant ligne TCL
--   hour              INT     — heure du jour (0-23)
--   lat               NUMERIC — latitude arrondie 0.001°
--   lon               NUMERIC — longitude arrondie 0.001°
--   bus_delay_sec     NUMERIC(8,2) — retard moyen bus (secondes)
--   bus_observations  INT     — nombre de passages bus
--   bus_delayed_count INT     — nombre de passages en retard
--   traffic_speed_kmh NUMERIC(6,2) — vitesse trafic locale
--   traffic_sensors   INT     — nombre de capteurs trafic dans la zone
--   diagnosis         TEXT    — 'infra' / 'operations' / 'bus_lane_ok' / 'ok'
--   traffic_congestion NUMERIC(4,3) — ratio congestion (0.0-1.0)
--   computed_at       TIMESTAMPTZ
-- Index : PK (line_ref, hour, lat, lon), diagnosis, line_ref
-- Refresh : CONCURRENTLY, */15 min par DAG transform_silver_to_gold
```

---

## Contrat existant à préserver

### Widgets qui consomment `cached_bottlenecks_top()`

Les 3 widgets + `top_decisions.py` (utilisé par Elu_1_Synthese) consomment le même format de dict. Clés actuelles attendues :

```python
{
    "rank": int,
    "zone": str,
    "lines_impacted": list[str],
    "voyageurs_jour": int,
    "gain_min": float,          # ← actuellement hardcodé
    "cout_M_euros": float,      # ← actuellement hardcodé
    "roi_mois": float,          # ← actuellement hardcodé
    "delai_mois": int,          # ← actuellement hardcodé
    "description": str,
}
```

Les clés existantes doivent rester présentes (rétro-compat avec `top_decisions.py`). Ajouter les nouvelles (`diagnosis`, `lat`, `lon`, `avg_delay_s`, `traffic_speed_kmh`) en plus.

### Fonction `cached_bottlenecks_top()` dans `data_cache.py`

Cache Streamlit. TTL = 30 secondes. Appelle `load_bottlenecks_top()`. Pas de modification nécessaire dans `data_cache.py` — les changements sont dans `load_bottlenecks_top()` en amont.
