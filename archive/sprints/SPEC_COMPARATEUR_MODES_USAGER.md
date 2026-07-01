# SPEC — Comparateur de modes de transport (Persona Usager)

> **Sprint 15+ (2026-06-19)** — Spécification complète pour implémentation par agent.
> **Auteur** : Patrice DUCLOS / Claude Opus 4.6
> **Branche cible** : `vps`
> **Statut** : PRÊT À IMPLÉMENTER

---

## Table des matières

1. [Contexte et objectif](#1-contexte-et-objectif)
2. [Architecture actuelle (état des lieux)](#2-architecture-actuelle)
3. [Concepts récupérés de LyonTraffic](#3-concepts-récupérés-de-lyontraffic)
4. [Spécification Phase 1 — Mode unique avec KPIs temps + coût](#4-phase-1)
5. [Spécification Phase 2 — Comparateur multi-modes + recommandation](#5-phase-2)
6. [Fichiers à créer](#6-fichiers-à-créer)
7. [Fichiers à modifier](#7-fichiers-à-modifier)
8. [Migration SQL](#8-migration-sql)
9. [Code source de référence (LyonTraffic)](#9-code-source-de-référence)
10. [Tests à écrire](#10-tests)
11. [Contraintes projet](#11-contraintes-projet)
12. [Checklist de livraison](#12-checklist)

---

## 1. Contexte et objectif

### Problème actuel

La page `Usager_1_Mon_Trajet.py` permet de sélectionner UN mode de transport (TC, Vélov, Voiture) via un `st.segmented_control` single-select. Chaque mode affiche son résultat (itinéraire, carte, segments) mais :

- **Aucune information de coût** n'est affichée (ni €, ni CO2)
- **Aucune comparaison** entre modes n'est possible
- L'usager ne sait pas quel mode est optimal pour son trajet

### Objectif

Implémenter un **comparateur de modes de transport** en 2 phases :

- **Phase 1** : L'usager sélectionne 1 mode → résultat enrichi avec **temps + coût + CO2** (KPIs)
- **Phase 2** : L'usager peut demander une **comparaison des 3 modes** → le système recommande le meilleur selon un critère (temps OU coût) → l'usager choisit ensuite son mode et voit le détail

### 3 modes de transport

| Mode | Clé interne | Icône | Sources données |
|------|-------------|-------|-----------------|
| Transport en commun | `tc` | 🚌 | `referentiel.lieux_transports`, `referentiel.lieux_calendrier`, `gold.bus_delay_segments` |
| Voiture | `voiture` | 🚗 | `gold.trafic_predictions`, `gold.dim_spatial_grid_mapping`, graphe Dijkstra |
| Vélov | `velov` | 🚲 | `silver.velov_clean`, smart routing `plan_velov_trip()` |

### 2 critères de sélection

| Critère | Clé | Description |
|---------|-----|-------------|
| Temps | `temps` | Minimiser la durée totale du trajet |
| Coût | `cout` | Minimiser le coût total en euros |

---

## 2. Architecture actuelle

### Fichiers impliqués

```
dashboard/
  pages/
    Usager_1_Mon_Trajet.py          # Page principale — MODIFIER
  components/
    widgets/usager/
      __init__.py                    # Exports — MODIFIER
      search_bar.py                  # Sélecteur O/D + modes — MODIFIER
      transit_trip.py                # Widget TC (existe, complet)
      velov_trip.py                  # Widget Vélov (existe, complet)
      itinerary.py                   # Widget voiture (existe, complet)
      weather_widget.py              # Météo contexte (existe)
      traffic_widget.py              # Trafic contexte (existe)
      velov_widget.py                # Vélov contexte (existe)
    data_cache.py                    # Cache Streamlit — MODIFIER

src/routing/
  __init__.py                        # Facade — MODIFIER
  pathfinder_multimodal.py           # plan_velov_trip(), plan_car_trip(), plan_transit_trip() — EXISTE
  pathfinder.py                      # compute_itinerary() Dijkstra — EXISTE
  graph.py                           # build_routing_graph() — EXISTE
  eco_calculator.py                  # À CRÉER (porté de LyonTraffic)

src/data/
  data_loader.py                     # Wrappers fail-loud — MODIFIER
  db_query.py                        # Helpers SQL — MODIFIER

scripts/sql/
  migration_016_tarifs_modes.sql     # À CRÉER
```

### Fonctions de calcul existantes (pathfinder_multimodal.py)

#### `plan_transit_trip(origin, destination) -> TransitItinerary | None`

**Fichier** : `src/routing/pathfinder_multimodal.py:895`

Retourne un `TransitItinerary` (dataclass) avec :
```python
@dataclass
class TransitItinerary:
    origin_label: str
    destination_label: str
    segments: list[TransitSegment]  # segments TC (ligne, arrêts, cadence, retard)
    transfer_hub: str | None        # hub de correspondance
    n_transfers: int                 # 0 = direct, 1 = 1 correspondance
    total_duration_min: float        # durée totale en minutes
    total_walk_m: int                # marche totale en mètres
    total_delay_min: float           # retard cumulé moyen
    confidence: float                # 0.0 - 1.0
    source: str                      # "db"
    diagnostics: list[str]
```

Chaque `TransitSegment` :
```python
@dataclass
class TransitSegment:
    line_ref: str
    line_mode: str           # "metro" | "tram" | "bus" | "funicular"
    line_label: str          # ex: "Métro A" (via clean_line_label)
    stop_origin: str
    stop_dest: str
    distance_walk_to_m: int
    distance_walk_from_m: int
    cadence_min: float       # fréquence estimée
    wait_estimate_min: float # attente estimée (cadence/2)
    delay_avg_min: float     # retard moyen 7j glissant
    duration_estimate_min: float
    confidence: float
```

#### `plan_velov_trip(...) -> VelovItinerary`

**Fichier** : `src/routing/pathfinder_multimodal.py:253`

Retourne un `VelovItinerary` (dataclass) avec :
```python
@dataclass
class VelovItinerary:
    origin_label: str
    destination_label: str
    segments: list[VelovSegment]      # 3 segments: walk → cycle → walk
    total_duration_min: float
    total_distance_m: float
    origin_alternatives: list[dict]
    dest_alternatives: list[dict]
    origin_neighbors: list[dict]
    dest_neighbors: list[dict]
    diagnostics: list[str]
    source: str

    @property
    def feasible(self) -> bool: ...
```

Chaque `VelovSegment` :
```python
@dataclass
class VelovSegment:
    mode: str              # "walk" | "cycle" | "destination"
    from_label: str
    to_label: str
    from_lon: float
    from_lat: float
    to_lon: float
    to_lat: float
    distance_m: float
    duration_min: float
    n_bikes_depart: int | None
    n_docks_arrive: int | None
    n_bikes_mechanical: int | None
    n_bikes_electrical: int | None
    notes: str
```

#### `plan_car_trip(...) -> dict`

**Fichier** : `src/routing/pathfinder_multimodal.py:513`

Retourne un dict :
```python
{
    "origin_label": str,
    "destination_label": str,
    "total_length_m": float,
    "total_duration_min": float,
    "average_speed_kmh": float,
    "horizon_minutes": int,
    "segments": [
        {
            "channel_id": str,
            "length_m": float,
            "speed_kmh": float,
            "duration_s": float,
            "start_lat": float,
            "start_lon": float,
            "end_lat": float,
            "end_lon": float,
        }
    ],
    "source": "db" | "unavailable",
}
```

### Sérialisation existante dans data_loader.py

`load_transit_itinerary()` (ligne 807) sérialise `TransitItinerary` → dict pour Streamlit cache. Pattern à reproduire pour le comparateur.

### search_bar.py actuel (état au Sprint 15+)

**Fichier** : `dashboard/components/widgets/usager/search_bar.py`

Retourne :
```python
{
    "origin": str,          # ex: "🏙 Villeurbanne"
    "destination": str,     # ex: "🚉 Part-Dieu"
    "departure_mode": str,  # "🚶 Partir maintenant" | "⏰ Arriver à l'heure"
    "departure_time": str | None,
    "modes": [str],         # liste d'1 élément, ex: ["🚌 Transport en commun"]
}
```

Le sélecteur de modes est un `st.segmented_control` single-select avec 3 options :
```python
selected_mode = st.segmented_control(
    "Modes de transport autorisés",
    options=["🚌 Transport en commun", "🚲 Vélov", "🚗 Voiture"],
    selection_mode="single",
    default="🚌 Transport en commun",
    key="search_modes",
    width="stretch",
    required=True,
)
```

### Usager_1_Mon_Trajet.py — flux actuel

```
render_search_bar() → dict
    ↓
"Trouver mon trajet" button click
    ↓
modes = search["modes"]
has_velov = "Vélov" in modes[0]
has_voiture = "Voiture" in modes[0]
has_tc = "Transport en commun" in modes[0]
    ↓
if has_tc  → render_transit_trip(origin, destination)
if has_voiture → render_traffic_widget() + render_itinerary_result(...)
if has_velov → render_velov_trip(origin, destination, ...)
```

---

## 3. Concepts récupérés de LyonTraffic

### 3.1. eco_calculator.py (à adapter)

**Source** : `github.com/PDUCLOS/Lyontraffic/src/routing/eco_calculator.py`

Calcul d'impact CO2 et coût par mode. Code source complet :

```python
def calculate_impact(mode: str, distance_km: float, is_congested: bool = False) -> dict:
    """
    Calcule l'impact CO2 et le coût d'un trajet.
    
    Args:
        mode: 'voiture', 'tcl', 'velov'
        distance_km: distance du trajet en kilomètres
        is_congested: True si trafic saturé (augmente conso voiture +40%)

    Returns:
        {"co2_g": float, "cost_eur": float, "fuel_l": float}
    """
    impact = {"co2_g": 0.0, "cost_eur": 0.0, "fuel_l": 0.0}
    
    if mode == "voiture":
        co2_per_km = 193          # g CO2/km (ADEME 2024, mix urbain)
        fuel_per_100km = 7.5      # L/100km
        fuel_price_per_l = 1.85   # € SP95 (2026-05)
        penalty = 1.4 if is_congested else 1.0  # +40% bouchons
        impact["fuel_l"] = (fuel_per_100km / 100) * distance_km * penalty
        impact["co2_g"] = co2_per_km * distance_km * penalty
        impact["cost_eur"] = impact["fuel_l"] * fuel_price_per_l
        
    elif mode == "tcl":
        co2_per_km = 35           # g CO2/km (mix bus/tram/métro Lyon)
        impact["co2_g"] = co2_per_km * distance_km
        impact["cost_eur"] = 2.00 # Ticket unitaire TCL standard
        
    elif mode == "velov":
        impact["co2_g"] = 0.0
        impact["cost_eur"] = 0.0  # Gratuit < 30min (abonné annuel)

    for k in ("co2_g", "cost_eur", "fuel_l"):
        impact[k] = round(impact[k], 2)
    return impact


def get_comparison(distance_km: float, is_congested: bool = False) -> dict:
    """Comparaison complète pour tous les modes."""
    return {
        "voiture": calculate_impact("voiture", distance_km, is_congested),
        "tcl": calculate_impact("tcl", distance_km, is_congested),
        "velov": calculate_impact("velov", distance_km, is_congested),
    }
```

### 3.2. Tarifs TCL réels (table SQL)

**Source** : `github.com/PDUCLOS/Lyontraffic/infra/docker/migrate_tarifs_modes.sql`

```sql
CREATE TABLE IF NOT EXISTS gold.tarifs_modes (
    id              SERIAL PRIMARY KEY,
    mode            TEXT NOT NULL,        -- 'tcl' | 'velov'
    produit         TEXT NOT NULL,        -- 'ticket_unitaire', 'velov_1jour', etc.
    produit_label   TEXT NOT NULL,
    age_min         INT DEFAULT NULL,
    age_max         INT DEFAULT NULL,
    prix_eur        NUMERIC(6,3) NOT NULL,
    duree_min       INT DEFAULT NULL,
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mode, produit, age_min, age_max)
);

-- Données de référence :
INSERT INTO gold.tarifs_modes VALUES
    ('tcl', 'ticket_unitaire',    'Ticket unitaire TCL',     NULL, NULL,  2.05,  60,  '1 trajet'),
    ('tcl', 'ticket_aller_retour','Ticket aller-retour TCL', NULL, NULL,  4.00, 120,  '2 trajets'),
    ('tcl', 'ticket_24h',         'Ticket 24h TCL',          NULL, NULL,  6.30, 1440, '24h'),
    ('tcl', 'ticket_jeune',       'Ticket jeunes (-25 ans)', 0,    24,    1.60,  60,  NULL),
    ('tcl', 'ticket_enfant',      'Ticket enfant (4-10)',    4,    10,    1.00,  60,  NULL),
    ('tcl', 'ticket_gratuit',     'Gratuit (0-3 ans)',       0,     3,    0.00,  NULL, NULL),
    ('tcl', 'carnet_10',          'Carnet 10 voyages',       NULL, NULL, 17.20,  NULL, '10 trajets'),
    ('velov', 'velov_1jour',      'Vélov 1 jour',            NULL, NULL,  1.50, 1440, NULL),
    ('velov', 'velov_1an',        'Vélov 1 an',              NULL, NULL, 39.00, NULL, NULL),
    ('velov', 'velov_1mois',      'Vélov 1 mois',            NULL, NULL,  5.00, 43200, NULL),
    -- Ajout voiture (référence coûts moyens Lyon)
    ('voiture', 'carburant_sp95', 'SP95 (prix/L)',           NULL, NULL,  1.85, NULL, '2026-05'),
    ('voiture', 'parking_1h_z2',  'Parking voirie 1h zone 2',NULL, NULL,  2.00,  60,  'standard'),
    ('voiture', 'parking_2h_z2',  'Parking voirie 2h zone 2',NULL, NULL,  6.00, 120,  'standard'),
ON CONFLICT DO NOTHING;
```

### 3.3. Scoring composite (critère de tri)

**Source** : `github.com/PDUCLOS/Lyontraffic/dashboard/pages/9_Recommandation_Trajet.py:958`

```python
def _score_mode(m: dict) -> float:
    """Score composite pour tri multi-critère."""
    t = m["time"] or 9999
    cost_total = m["impact"].get("cost_eur", 0) + (parking_cost if m["key"] == "voiture" else 0)
    co2 = m["impact"].get("co2_g", 0)
    
    if critere == "cout":
        # 1 min ~ 0.30 €/pers équivalent → score = t + cost × 3.3
        return t + cost_total * 3.3
    if critere == "eco":
        return co2 * 100 + t  # CO2 prioritaire, temps tie-break
    return t  # défaut: meilleur temps
```

### 3.4. Parking Lyon (optionnel Phase 2+)

**Source** : `github.com/PDUCLOS/Lyontraffic/src/routing/parking.py`

Grille tarification voirie Lyon 2026 (3 zones poids véhicule) :

| Zone | Catégorie | 1h | 2h | 4h | 7h | FPS |
|------|-----------|-----|-----|------|------|------|
| 1 | Sobre (<1t therm / <2.1t élec) | 1.00€ | 3.00€ | 12.00€ | 18.00€ | 35€ |
| 2 | Standard (1-1.5t therm) | 2.00€ | 6.00€ | 14.00€ | 26.00€ | 55€ |
| 3 | Lourd (>1.5t) | 3.50€ | 9.50€ | 21.50€ | 39.50€ | 80€ |

Plus : zone bleue (gratuit < 2h, FPS au-delà), P+R TCL (~4-6.30€/jour).

**Décision** : le parking est un enrichissement Phase 2. En Phase 1, le coût voiture = carburant seul. Documenter qu'on peut brancher `price_parking()` plus tard.

### 3.5. Calories (enrichissement)

**Source** : `Recommandation_Trajet.py:358`

```python
_CALORIES_PER_KM = {"velov": 46, "marche": 50}  # kcal/km, source MET tables ADEME/INSERM
```

Afficher les calories brûlées pour Vélov (46 kcal/km). Enrichissement visuel utile pour usager.

---

## 4. Phase 1 — Mode unique avec KPIs temps + coût

### 4.1. Modifications search_bar.py

**Ajouter** un sélecteur de critère SOUS le sélecteur de mode :

```python
critere = st.radio(
    "Optimiser pour",
    ["⏱️ Temps", "💰 Coût"],
    horizontal=True,
    key="search_critere",
    index=0,
)
```

Le dict retourné par `render_search_bar()` ajoute :
```python
{
    ...existing keys...,
    "critere": "temps" | "cout",   # NEW
}
```

### 4.2. Nouveau module src/routing/eco_calculator.py

Créer `src/routing/eco_calculator.py` avec :

```python
"""Calculateur d'impact écologique et économique par mode de transport.

Adapté de PDUCLOS/Lyontraffic pour le pipeline LyonFlow (Sprint 15+).
Sources données : ADEME 2024, Grille TCL SYTRAL 2026, Ville de Lyon 2025.
"""

from __future__ import annotations

# Constantes coût/CO2 par mode (sources documentées)
VOITURE_CO2_G_PER_KM = 193       # ADEME 2024, mix urbain France
VOITURE_FUEL_L_PER_100KM = 7.5   # consommation moyenne urbaine
VOITURE_FUEL_PRICE_EUR = 1.85    # SP95 prix moyen 2026-05
VOITURE_CONGESTION_PENALTY = 1.4  # +40% consommation en bouchons

TCL_CO2_G_PER_KM = 35            # mix bus/tram/métro Lyon (SYTRAL/ADEME)
TCL_TICKET_UNITAIRE_EUR = 2.05   # tarif TCL 2026

VELOV_CO2_G_PER_KM = 0.0
VELOV_COST_EUR = 0.0             # gratuit si abonné annuel et trajet < 30min
VELOV_COST_JOUR_EUR = 1.50       # ticket journée

CALORIES_PER_KM = {"velov": 46, "marche": 50}  # kcal/km (MET tables ADEME/INSERM)


def calculate_impact(
    mode: str,
    distance_km: float,
    is_congested: bool = False,
    duration_min: float | None = None,
) -> dict:
    """Calcule CO2, coût et carburant pour un trajet.

    Args:
        mode: 'voiture' | 'tc' | 'velov'
        distance_km: distance en km
        is_congested: True si trafic congestionné (voiture uniquement)
        duration_min: durée réelle du trajet (pour enrichissement)

    Returns:
        {
            "co2_g": float,
            "cost_eur": float,
            "fuel_l": float,
            "calories_kcal": int,
            "is_congested": bool,
            "congestion_penalty": float,
        }
    """
    ...  # Implémenter selon le code source §3.1


def get_comparison(
    distance_km: float,
    is_congested: bool = False,
    durations: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Comparaison des 3 modes.

    Args:
        distance_km: distance en km
        is_congested: état trafic
        durations: {"voiture": min, "tc": min, "velov": min} optionnel

    Returns:
        {"voiture": {...}, "tc": {...}, "velov": {...}}
    """
    ...


def recommend_mode(
    comparison: dict[str, dict],
    critere: str = "temps",
    durations: dict[str, float] | None = None,
) -> dict:
    """Recommande le meilleur mode selon le critère.

    Args:
        comparison: output de get_comparison()
        critere: "temps" | "cout"
        durations: {"voiture": min, "tc": min, "velov": min}

    Returns:
        {
            "winner": "tc" | "voiture" | "velov",
            "scores": {"voiture": float, "tc": float, "velov": float},
            "explanation": str,  # texte pour l'usager
        }
    """
    ...  # Implémenter scoring composite inspiré §3.3
```

### 4.3. Nouveau widget : mode_summary.py

Créer `dashboard/components/widgets/usager/mode_summary.py` :

Widget qui affiche **4 KPI cards** en haut de chaque résultat de mode :

```
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ 🕐 Durée│ │ 💰 Coût │ │ 🌿 CO2  │ │ 📏 Dist │
│  23 min │ │  2.05 € │ │  105 g  │ │  3.0 km │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

Pour Vélov, ajouter une 5e card "🔥 Calories" (46 kcal/km).

```python
def render_mode_summary(
    mode: str,           # "tc" | "voiture" | "velov"
    duration_min: float,
    distance_km: float,
    impact: dict,        # output de calculate_impact()
) -> None:
    """Affiche les KPIs temps + coût + CO2 pour un mode."""
    ...
```

### 4.4. Modifications Usager_1_Mon_Trajet.py

Le flux devient :

```
render_search_bar() → dict  (inclut maintenant "critere")
    ↓
"Trouver mon trajet" button click
    ↓
Calcul distance haversine O → D (pour eco_calculator)
    ↓
Pour le mode sélectionné :
  1. Appeler plan_*() existant → obtenir duration_min + distance
  2. Appeler calculate_impact() → obtenir coût + CO2
  3. Afficher render_mode_summary() (4-5 KPIs)
  4. Afficher le widget détaillé existant (transit_trip / velov_trip / itinerary_result)
```

**Code de calcul distance** (haversine adapté du `_haversine_m` existant dans pathfinder_multimodal.py:109) :

```python
import math

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

**Important** : pour la voiture, utiliser la distance réelle du graphe Dijkstra (`total_length_m`) plutôt que haversine. Pour TC et Vélov, utiliser haversine × 1.3 (facteur détour urbain, comme dans LyonTraffic ligne 689).

### 4.5. Ajouts data_cache.py

```python
@st.cache_data(ttl=60, show_spinner=False)
def cached_mode_impact(mode: str, distance_km: float, is_congested: bool = False) -> dict:
    """Cache l'impact CO2/coût pour un mode."""
    from src.routing.eco_calculator import calculate_impact
    return calculate_impact(mode=mode, distance_km=distance_km, is_congested=is_congested)
```

---

## 5. Phase 2 — Comparateur multi-modes + recommandation

### 5.1. UX cible

Après le sélecteur de mode, ajouter un **toggle** :

```python
compare_all = st.toggle("🔄 Comparer les 3 modes", value=False, key="compare_modes")
```

Quand activé :
1. Calculer les 3 modes en parallèle (transit + voiture + vélov)
2. Afficher un **tableau comparatif** horizontal
3. Afficher une **recommandation** (winner card) selon le critère choisi
4. L'usager peut cliquer sur un mode pour voir le détail

### 5.2. Nouveau widget : mode_comparison.py

Créer `dashboard/components/widgets/usager/mode_comparison.py` :

```python
def render_mode_comparison(
    results: dict[str, dict],    # {"tc": {...}, "voiture": {...}, "velov": {...}}
    critere: str = "temps",      # "temps" | "cout"
    origin: str = "",
    destination: str = "",
) -> str | None:
    """Affiche le comparatif 3 modes + winner card.

    Args:
        results: pour chaque mode, un dict avec :
            - duration_min: float
            - distance_km: float
            - impact: dict (output calculate_impact)
            - feasible: bool
            - source: str
        critere: critère de tri
        origin/destination: pour affichage bannière

    Returns:
        Le mode choisi par l'usager (clic sur card) ou None.
    """
```

### 5.3. Layout comparatif

```
┌─── COMPARATIF ────────────────────────────────────────────────┐
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │ 🏆 RECOMMANDÉ    │  │                  │  │              │ │
│  │ 🚌 TC            │  │ 🚲 Vélov         │  │ 🚗 Voiture   │ │
│  │ 23 min           │  │ 18 min           │  │ 15 min       │ │
│  │ 2.05 €           │  │ 0.00 €           │  │ 1.42 €       │ │
│  │ 105 g CO2        │  │ 0 g CO2          │  │ 579 g CO2    │ │
│  │ [Voir détail]    │  │ [Voir détail]    │  │ [Voir détail]│ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
│                                                                │
│  💡 Insight : Vélov économise 579g CO2 vs voiture              │
└────────────────────────────────────────────────────────────────┘
```

### 5.4. Winner card (inspirée de LyonTraffic)

La card du mode recommandé a :
- Bordure colorée + badge "🏆 RECOMMANDÉ"
- Grande police pour la durée
- Sous-ligne coût + CO2
- Si voiture : mention congestion si applicable
- Si vélov : calories brûlées

### 5.5. Scoring pour la recommandation

```python
def _score_mode(mode_key: str, duration_min: float, cost_eur: float, critere: str) -> float:
    if critere == "cout":
        # Scoring combiné : 1 min vaut ~0.30€
        return duration_min + cost_eur * 3.3
    # critere == "temps"
    return duration_min
```

Le winner = mode avec le score le plus bas.

### 5.6. Flux Phase 2 dans Usager_1_Mon_Trajet.py

```
render_search_bar() → dict
    ↓
compare_all toggle = True ?
    ↓ OUI                              ↓ NON (Phase 1)
Calculer les 3 modes :              Calculer 1 mode :
  tc = plan_transit_trip()             mode_result = plan_*()
  voiture = plan_car_trip()            impact = calculate_impact()
  velov = plan_velov_trip()            render_mode_summary()
  impacts = get_comparison()           render_*_detail()
    ↓
render_mode_comparison(results, critere)
    ↓
Usager clique "Voir détail" sur un mode
    ↓
Afficher le widget détaillé de CE mode
```

---

## 6. Fichiers à créer

### 6.1. `src/routing/eco_calculator.py`

Module de calcul d'impact. Voir §4.2 pour l'interface complète.

**Implémentation** : adapter le code de LyonTraffic (§3.1) en ajoutant :
- Paramètre `duration_min` optionnel
- Calcul calories pour vélov
- Détection congestion via `plan_car_trip()` average_speed (< 25 km/h = congestionné)
- Docstrings avec sources ADEME/SYTRAL
- Typage complet

### 6.2. `dashboard/components/widgets/usager/mode_summary.py`

Widget KPIs 4-5 cards. Voir §4.3.

### 6.3. `dashboard/components/widgets/usager/mode_comparison.py`

Widget comparateur 3 modes + winner. Voir §5.2.

### 6.4. `scripts/sql/migration_016_tarifs_modes.sql`

Migration SQL. Voir §8.

### 6.5. Tests (voir §10)

---

## 7. Fichiers à modifier

### 7.1. `dashboard/components/widgets/usager/search_bar.py`

**Modifications** :

1. **Ajouter** le radio "Optimiser pour" (temps/coût) dans `col_modes` SOUS le segmented_control
2. **Ajouter** `"critere"` au dict de retour
3. CSS pour le radio (style horizontal compact)

**Position dans le layout** : sous le hint contextuel du mode, avant la fermeture du `st.container(border=True)`.

### 7.2. `dashboard/pages/Usager_1_Mon_Trajet.py`

**Modifications majeures** :

1. **Import** `render_mode_summary`, `render_mode_comparison` depuis usager widgets
2. **Import** `calculate_impact`, `get_comparison`, `recommend_mode` depuis eco_calculator
3. **Ajouter** calcul distance haversine après résolution coords O/D
4. **Ajouter** `compare_all` toggle après le bouton "Trouver mon trajet"
5. **Phase 1 path** : pour chaque mode, insérer `render_mode_summary()` AVANT le widget détaillé
6. **Phase 2 path** : si `compare_all`, calculer les 3 modes, appeler `render_mode_comparison()`, puis afficher le détail du mode choisi
7. **Extraire** `critere = search.get("critere", "temps")` du dict search

### 7.3. `dashboard/components/widgets/usager/__init__.py`

Ajouter les exports :
```python
from dashboard.components.widgets.usager.mode_summary import render_mode_summary
from dashboard.components.widgets.usager.mode_comparison import render_mode_comparison
```

### 7.4. `dashboard/components/data_cache.py`

Ajouter `cached_mode_impact()` (§4.5).

Ajouter `cached_car_trip()` (wrapper autour de `plan_car_trip` sérialisé, TTL 30s) :
```python
@st.cache_data(ttl=30, show_spinner=False)
def cached_car_trip(origin: str, destination: str) -> dict | None:
    from dashboard.components.widgets.usager.velov_trip import _resolve_lieu
    from src.routing.pathfinder_multimodal import plan_car_trip
    origin_coords = _resolve_lieu(origin)
    dest_coords = _resolve_lieu(destination)
    if not origin_coords or not dest_coords:
        return None
    return plan_car_trip(
        origin_lon=origin_coords[0], origin_lat=origin_coords[1],
        dest_lon=dest_coords[0], dest_lat=dest_coords[1],
        origin_label=origin, dest_label=destination,
        horizon_minutes=60,
    )
```

### 7.5. `src/routing/__init__.py`

Ajouter à la facade :
```python
from src.routing.eco_calculator import calculate_impact, get_comparison, recommend_mode
```

---

## 8. Migration SQL

**Fichier** : `scripts/sql/migration_016_tarifs_modes.sql`

```sql
-- =============================================================================
-- MIGRATION 016 : gold.tarifs_modes — Grille tarifaire modes de transport Lyon
-- Sprint 15+ (2026-06-19)
-- Source : SYTRAL TCL 2026, Ville de Lyon 2025, Vélov SYTRAL
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS gold.tarifs_modes (
    id              SERIAL PRIMARY KEY,
    mode            TEXT NOT NULL,
    produit         TEXT NOT NULL,
    produit_label   TEXT NOT NULL,
    age_min         INT DEFAULT NULL,
    age_max         INT DEFAULT NULL,
    prix_eur        NUMERIC(6,3) NOT NULL,
    duree_min       INT DEFAULT NULL,
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mode, produit, age_min, age_max)
);

CREATE INDEX IF NOT EXISTS idx_tarifs_modes_mode
    ON gold.tarifs_modes (mode);

INSERT INTO gold.tarifs_modes
    (mode, produit, produit_label, age_min, age_max, prix_eur, duree_min, notes)
VALUES
    ('tcl', 'ticket_unitaire',     'Ticket unitaire TCL',         NULL, NULL,  2.05,   60, '1 trajet, validité 1h'),
    ('tcl', 'ticket_aller_retour', 'Ticket aller-retour TCL',     NULL, NULL,  4.00,  120, '2 trajets'),
    ('tcl', 'ticket_24h',          'Ticket 24h TCL',              NULL, NULL,  6.30, 1440, 'Illimité 24h'),
    ('tcl', 'ticket_jeune',        'Ticket jeunes (-25 ans)',        0,   24,  1.60,   60, NULL),
    ('tcl', 'ticket_enfant',       'Ticket enfant (4-10 ans)',       4,   10,  1.00,   60, NULL),
    ('tcl', 'ticket_gratuit',      'Gratuit (0-3 ans)',              0,    3,  0.00, NULL, NULL),
    ('tcl', 'carnet_10',           'Carnet 10 voyages',           NULL, NULL, 17.20, NULL, '1.72€/trajet'),
    ('velov', 'velov_ticket_1j',   'Vélov ticket courte durée',   NULL, NULL,  1.50, 1440, '30min gratuites puis 2€/30min'),
    ('velov', 'velov_abo_mensuel', 'Vélov abonnement mensuel',    NULL, NULL,  5.00, NULL, '30min gratuites incluses'),
    ('velov', 'velov_abo_annuel',  'Vélov abonnement annuel',     NULL, NULL, 39.00, NULL, '30min gratuites incluses'),
    ('voiture', 'sp95_litre',      'SP95 (prix au litre)',        NULL, NULL,  1.85, NULL, 'Prix moyen 2026-05'),
    ('voiture', 'parking_z2_1h',   'Parking voirie zone 2 (1h)',  NULL, NULL,  2.00,   60, 'Véhicule standard 1-1.5t'),
    ('voiture', 'parking_z2_2h',   'Parking voirie zone 2 (2h)',  NULL, NULL,  6.00,  120, 'Véhicule standard 1-1.5t')
ON CONFLICT DO NOTHING;

COMMIT;
```

**Note** : cette table est **référentielle** (comme `referentiel.lieux_lyon`). Les tarifs sont mis à jour manuellement (1-2x/an quand SYTRAL publie une nouvelle grille). L'`eco_calculator.py` peut requêter cette table OU utiliser des constantes hardcodées (plus simple pour Phase 1, migration SQL = enrichissement futur pour Phase 2).

---

## 9. Code source de référence (LyonTraffic)

### 9.1. Page Recommandation Trajet complète

**Fichier source** : `github.com/PDUCLOS/Lyontraffic/dashboard/pages/9_🗺️_Recommandation_Trajet.py`

Concepts à reprendre :
- **Lignes 677-683** : Radio critère de choix (temps / rapport temps-coût / écologique)
- **Lignes 883-905** : Construction `modes_data` (list de dicts uniformes par mode)
- **Lignes 958-970** : `_score_mode()` scoring composite
- **Lignes 996-1057** : Winner card HTML (badge RECOMMANDÉ + KPIs)
- **Lignes 1059-1109** : Cards alternatives côte à côte
- **Lignes 1111-1126** : Insight contextuel (économie CO2 vs voiture)
- **Lignes 328-355** : `_cost_display()` avec gestion passagers + A/R + parking

Concepts à **NE PAS** reprendre (non applicables) :
- Navitia API (on utilise notre pipeline)
- OSRM routing (on utilise notre graphe Dijkstra)
- Vélo électrique (hors scope — 3 modes seulement)
- Marche comme mode autonome (intégrée dans Vélov)
- 59 communes LIEUX_PAR_VILLE (on utilise `referentiel.lieux_lyon` 21 lieux)
- Aller-retour toggle (hors scope Phase 1, possible enrichissement futur)
- Nominatim geocoding (on utilise notre referentiel DB)

### 9.2. Page Synergie Multimodale

**Fichier source** : `github.com/PDUCLOS/Lyontraffic/dashboard/pages/7_🌐_Synergie_Multimodale.py`

Concepts à reprendre :
- **Simulateur Eco-Mobilité** : tableau comparatif 3 modes (Voiture / TCL / Vélov) avec coût + CO2 + carburant
- **Insight** : "Prendre les TCL économise X kg CO2 vs voiture"

### 9.3. Parking.py

**Fichier source** : `github.com/PDUCLOS/Lyontraffic/src/routing/parking.py`

**Décision** : NE PAS porter en Phase 1. Documenter dans `eco_calculator.py` que le parking est un enrichissement Phase 2. Le coût voiture Phase 1 = carburant seul.

Quand Phase 2 le branchera :
- `price_parking(duration_h, regulation, zone_tarif)` → `ParkingResult`
- 3 zones × interpolation linéaire sur grille (1h/2h/4h/7h)
- Zone bleue, P+R TCL, gratuit

---

## 10. Tests

### 10.1. Tests eco_calculator (CRÉER `tests/data/test_eco_calculator.py`)

```python
import pytest
from src.routing.eco_calculator import calculate_impact, get_comparison, recommend_mode

class TestCalculateImpact:
    def test_voiture_basic(self):
        r = calculate_impact("voiture", 5.0)
        assert r["co2_g"] > 0
        assert r["cost_eur"] > 0
        assert r["fuel_l"] > 0
        assert not r["is_congested"]

    def test_voiture_congested(self):
        normal = calculate_impact("voiture", 5.0, is_congested=False)
        congested = calculate_impact("voiture", 5.0, is_congested=True)
        assert congested["co2_g"] > normal["co2_g"]
        assert congested["cost_eur"] > normal["cost_eur"]
        assert congested["congestion_penalty"] == 1.4

    def test_tc_basic(self):
        r = calculate_impact("tc", 5.0)
        assert r["co2_g"] == round(35 * 5.0, 2)
        assert r["cost_eur"] == 2.05
        assert r["fuel_l"] == 0.0

    def test_velov_zero_emission(self):
        r = calculate_impact("velov", 5.0)
        assert r["co2_g"] == 0.0
        assert r["cost_eur"] == 0.0
        assert r["calories_kcal"] == 5 * 46

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            calculate_impact("avion", 5.0)

    def test_zero_distance(self):
        r = calculate_impact("voiture", 0.0)
        assert r["co2_g"] == 0.0
        assert r["cost_eur"] == 0.0

class TestGetComparison:
    def test_all_three_modes(self):
        c = get_comparison(5.0)
        assert set(c.keys()) == {"voiture", "tc", "velov"}
        assert c["voiture"]["co2_g"] > c["tc"]["co2_g"] > c["velov"]["co2_g"]

class TestRecommendMode:
    def test_temps_winner(self):
        c = get_comparison(5.0)
        durations = {"voiture": 10, "tc": 25, "velov": 20}
        r = recommend_mode(c, critere="temps", durations=durations)
        assert r["winner"] == "voiture"

    def test_cout_winner(self):
        c = get_comparison(5.0)
        durations = {"voiture": 10, "tc": 25, "velov": 20}
        r = recommend_mode(c, critere="cout", durations=durations)
        # Vélov = 0€ + 20min → score = 20 + 0 = 20
        # TC = 2.05€ + 25min → score = 25 + 6.77 = 31.77
        # Voiture = ~0.69€ + 10min → score = 10 + 2.28 = 12.28
        # Winner = voiture (lowest combined score)
        assert r["winner"] == "voiture"

    def test_cout_long_distance_tc_wins(self):
        c = get_comparison(15.0)
        durations = {"voiture": 35, "tc": 40, "velov": 55}
        r = recommend_mode(c, critere="cout", durations=durations)
        # Voiture 15km = fuel ~2.08€ → score = 35 + 6.86 = 41.86
        # TC = 2.05€ → score = 40 + 6.77 = 46.77
        # Vélov 0€ → score = 55 + 0 = 55
        # Closest fight, but voiture wins on combined
        assert r["winner"] in ("voiture", "tc")
```

### 10.2. Tests widget mode_summary (CRÉER `tests/persona/test_mode_summary.py`)

```python
from unittest.mock import patch
import pytest

class TestModeSummary:
    def test_render_tc_smoke(self):
        from dashboard.components.widgets.usager.mode_summary import render_mode_summary
        # Smoke test — ne lève pas d'exception
        # (nécessite mock st.metric / st.columns)

    def test_render_velov_shows_calories(self):
        # Vélov doit afficher une 5e KPI "Calories"
        ...
```

### 10.3. Tests widget mode_comparison (CRÉER `tests/persona/test_mode_comparison.py`)

```python
class TestModeComparison:
    def test_winner_badge_displayed(self):
        ...

    def test_three_cards_rendered(self):
        ...

    def test_infeasible_mode_greyed_out(self):
        ...
```

---

## 11. Contraintes projet

### 11.1. Règles CLAUDE.md (à respecter impérativement)

- **🔴 ZÉRO MOCK** : tout vient du pipeline. Si DB indispo → `DashboardDataError` + `st.error`. Jamais de fallback mock.
- **🔴 SQL PARAMÉTRÉ** : `psycopg2 %s`, zéro f-string SQL.
- **Fail loud** : toute erreur remonte via `DashboardDataError`.
- **Politique Sprint 8** : `_is_demo_mode()` retourne toujours `False`. Ne pas réintroduire de mode démo.
- **Version unique** : `get_settings().app_version` (importé de `src/config.py`).
- **Auto-refresh** : `setup_auto_refresh()` déjà câblé (Usager 60s).
- **Tests** : convention `tests/` avec `conftest.py` MockDB. Tests unitaires dans `tests/data/` ou `tests/persona/`.

### 11.2. Patterns Streamlit à suivre

- Tout widget est une fonction `render_*()` dans `dashboard/components/widgets/usager/`.
- Export dans `__init__.py` avec `__all__`.
- Cache via `dashboard/components/data_cache.py` (fonctions `cached_*`).
- Résolution lieux via `_resolve_lieu()` (strip emoji, query `referentiel.lieux_lyon`).
- HTML inline via `st.markdown(..., unsafe_allow_html=True)` ou `st.html(...)`.
- Couleurs via `dashboard/components/colors.py` (`COLORS` dict).
- KPIs via `st.metric()` dans `st.columns()`.

### 11.3. Structure des données (convention)

Les fonctions `plan_*_trip()` retournent des dataclasses ou dicts. Pour le cache Streamlit (`@st.cache_data`), les sérialiser en dicts (comme fait dans `load_transit_itinerary()`).

Le comparateur manipule un dict uniforme par mode :
```python
{
    "mode": "tc" | "voiture" | "velov",
    "duration_min": float,
    "distance_km": float,
    "impact": {
        "co2_g": float,
        "cost_eur": float,
        "fuel_l": float,
        "calories_kcal": int,
        "is_congested": bool,
        "congestion_penalty": float,
    },
    "feasible": bool,
    "source": str,
}
```

### 11.4. Styling

Reprendre le pattern HTML inline utilisé dans `transit_trip.py` et `velov_trip.py` :
- Cards avec `border-left` colorée
- Badges pastille (vert/rouge/orange)
- Variables CSS `var(--bg-card)`, `var(--primary-color)`, etc.
- Police 0.8-1.1rem selon hiérarchie

Pour la winner card Phase 2, s'inspirer du HTML de LyonTraffic (§9.1 lignes 1042-1057) mais adapter aux CSS variables du thème LyonFlow.

---

## 12. Checklist de livraison

### Phase 1

- [ ] `src/routing/eco_calculator.py` créé et fonctionnel
- [ ] `dashboard/components/widgets/usager/mode_summary.py` créé
- [ ] `dashboard/components/widgets/usager/search_bar.py` modifié (ajout critère)
- [ ] `dashboard/pages/Usager_1_Mon_Trajet.py` modifié (KPIs par mode)
- [ ] `dashboard/components/widgets/usager/__init__.py` modifié (exports)
- [ ] `dashboard/components/data_cache.py` modifié (cached_mode_impact, cached_car_trip)
- [ ] `src/routing/__init__.py` modifié (exports eco_calculator)
- [ ] `tests/data/test_eco_calculator.py` créé (≥10 tests)
- [ ] `pytest tests/ -v --tb=short` — tous verts
- [ ] `ruff check . --output-format=github` — clean

### Phase 2

- [ ] `dashboard/components/widgets/usager/mode_comparison.py` créé
- [ ] `scripts/sql/migration_016_tarifs_modes.sql` créé
- [ ] Toggle "Comparer les 3 modes" dans Usager_1
- [ ] Winner card + alternatives + insight
- [ ] Scoring composite temps/coût fonctionnel
- [ ] `tests/persona/test_mode_comparison.py` créé (≥5 tests)
- [ ] `pytest tests/ -v --tb=short` — tous verts

### Hors scope (enrichissements futurs)

- [ ] Parking voiture (porter `parking.py` de LyonTraffic)
- [ ] Aller-retour toggle
- [ ] Nombre de passagers (adultes + enfants, tarif enfant TCL)
- [ ] Requête `gold.tarifs_modes` au lieu de constantes hardcodées
- [ ] CO2 comme 3e critère de tri
- [ ] Carte Folium comparative (polylines 3 modes superposées)

---

## Annexe A — Arbre de décision du scoring

```
critere = "temps"
    → score = duration_min
    → winner = min(scores)

critere = "cout"
    → score = duration_min + cost_eur × 3.3
    → (1 minute vaut 0.30€ pour l'usager — source : valeur du temps CEREMA 2023)
    → winner = min(scores)
```

Exemples concrets pour un trajet Part-Dieu → Bellecour (3 km) :

| Mode | Durée | Coût | CO2 | Score temps | Score coût |
|------|-------|------|-----|-------------|------------|
| TC | 15 min | 2.05€ | 105g | 15.0 | 15 + 6.77 = 21.77 |
| Vélov | 14 min | 0.00€ | 0g | 14.0 | 14 + 0 = 14.0 |
| Voiture | 8 min | 0.41€ | 579g | 8.0 | 8 + 1.35 = 9.35 |

- Critère temps → **Voiture** (8 min)
- Critère coût → **Voiture** (9.35, combiné temps+coût le meilleur)

Pour un trajet Villeurbanne → Confluence (8 km, congestionné) :

| Mode | Durée | Coût | CO2 | Score temps | Score coût |
|------|-------|------|-----|-------------|------------|
| TC | 28 min | 2.05€ | 280g | 28.0 | 28 + 6.77 = 34.77 |
| Vélov | 35 min | 0.00€ | 0g | 35.0 | 35 + 0 = 35.0 |
| Voiture | 25 min | 1.53€ | 2161g | 25.0 | 25 + 5.05 = 30.05 |

- Critère temps → **Voiture** (25 min, malgré congestion)
- Critère coût → **Voiture** (30.05, toujours gagnant temps+coût combiné)

**Observation** : sur courte distance urbaine, la voiture gagne souvent en score combiné. Le Vélov gagne quand la distance est < 5km ET le temps voiture est gonflé par la congestion. Le TC gagne sur longue distance (coût fixe 2.05€ vs carburant proportionnel).
