# Sprint 14 — Transport en commun : routing TC usager

**Date** : 2026-06-19
**Branche** : `vps`
**Version cible** : 0.7.0
**Statut** : ✅ LIVRÉ (2026-06-19) — 7/7 tâches, 251 tests verts (+33), 0 régression

> **Note** : la roadmap CLAUDE.md réservait Sprint 14 pour TomTom Niveau 2
> (backtest engine). Ce sprint prend la priorité — TomTom Niveau 2 est
> repoussé à Sprint 15. Décision utilisateur 2026-06-19.

---

## Contexte

La page **Usager > Mon trajet** expose 6 modes de transport indépendants
(Métro, Tram, Bus, Vélov, Voiture, Marche). Problèmes identifiés :

1. **Bus, Tram, Métro sont séparés** — l'usager ne pense pas en modes isolés
   mais en "transport en commun" (TC). Un trajet TC combine souvent métro +
   tram + bus. Les séparer n'a pas de sens UX.
2. **Marche est inutile** — pas de calcul derrière, juste un label. La marche
   est un segment implicite (accès à l'arrêt) dans tout trajet TC ou Vélov.
3. **Aucun routing TC implémenté** — quand on sélectionne Métro/Tram/Bus,
   rien ne se passe. Le code ne checke que `has_velov` et `has_voiture`.
4. **Pas de parcours avec lignes, horaires, retards** — l'usager ne sait pas
   quelle ligne prendre, combien de temps attendre, ni quel retard prévoir.

5. **Trajet Vélov sans visibilité station** — les infos vélos/docks dispo
   sont enterrées dans les popups Folium et l'expander "Détail segments".
   L'usager ne voit pas d'un coup d'œil si la borne de départ a des vélos
   et si la borne d'arrivée a des places.

## Objectifs

1. Livrer un **itinéraire transport en commun** fonctionnel dans la page Usager,
   avec lignes concrètes, temps d'attente estimé, retards temps réel, et
   correspondances simples.
2. **Améliorer le trajet Vélov** : afficher les bornes de départ et d'arrivée
   avec vélos disponibles, places disponibles, et statut en temps réel
   directement dans le résultat (pas enterré dans un popup).

---

## Inventaire données existantes

### Ce qu'on a (exploitable Phase 1)

| Donnée | Table | Contenu | Couverture |
|--------|-------|---------|------------|
| Dessertes TC par lieu | `referentiel.lieux_transports` | 56 liaisons (21 lieux × lignes TCL) | 21 lieux emblématiques |
| Cadences par ligne | `referentiel.lieux_calendrier` | 223 cadences (line_ref × day_type × time_bucket) | Weekday/samedi/dimanche/vacances |
| Retards temps réel | `gold.bus_delay_segments` | avg_delay_seconds par ligne/segment/heure/jour | 7j glissants, toutes lignes |
| KPIs par ligne | `gold.mv_line_kpis_live` | OTP, retard moyen, charge, fréquence | 155 lignes |
| Bottlenecks | `gold.infrastructure_bottlenecks` | Croisement retard bus × congestion trafic | Diagnostic infra |
| SIRI temps réel | `silver.tcl_vehicles_clean` | Position + delay_seconds par véhicule | Toutes les 5 min |
| Helper cadence | `db_query.get_cadence_for_line()` | Cadence en min par véhicule | Par ligne/jour/tranche |
| Helper dessertes | `db_query.get_lieux_transports()` | Lignes qui desservent un lieu | Par lieu_id |
| Helper libellés | `db_query.clean_line_label()` | `ActIV:Line::66:SYTRAL_h20` → `L66 ; 20h` | Toutes lignes |

### Ce qu'on n'a PAS

| Donnée | Impact | Quand |
|--------|--------|-------|
| **GTFS stop_times** (horaires théoriques) | Pas de "prochain départ à 14:03". On donne des fréquences ("~toutes les 8 min") | Phase 2 — ingestion GTFS Grand Lyon |
| **Graphe TC complet** (tous arrêts × correspondances) | Limité aux 21 lieux référentiel. Pas d'arrêt intermédiaire | Phase 2 — Raptor router |
| **Temps de trajet inter-arrêts** | Estimé par cadence + distance. Pas de temps réel segment TC | Phase 2 — GTFS shapes.txt |

---

## Architecture — 2 Phases

### Phase 1 — Routing TC référentiel (ce sprint)

**Principe** : pour un trajet entre 2 lieux du référentiel (21 lieux), on
intersecte les lignes qui desservent l'origine et la destination. Si une ligne
commune existe → trajet direct. Sinon → correspondance simple via hub partagé.

```
Origine (lieu_id=1)                    Destination (lieu_id=2)
    │                                      │
    ▼                                      ▼
get_lieux_transports(1)            get_lieux_transports(2)
    │                                      │
    ▼                                      ▼
{M_A, T_3, C_3}                    {M_A, M_C, T_1}
    │                                      │
    └──────── intersection ────────────────┘
                   │
                   ▼
              M_A = direct !
                   │
                   ▼
    get_cadence_for_line('M_A', day_type, time_bucket)
                   │
                   ▼
            cadence = 4 min (weekday HPM)
                   │
                   ▼
    get_bus_delay_segments(line_ref='M_A')
                   │
                   ▼
            retard moyen = +1.2 min
                   │
                   ▼
    ┌─────────────────────────────────┐
    │ 🚇 Métro A                      │
    │ Arrêt : Laurent Bonnevay        │
    │ → Arrêt : Confluence            │
    │ Fréquence : ~4 min              │
    │ Attente estimée : ~2 min        │
    │ Retard moyen observé : +1.2 min │
    │ Temps total estimé : ~18 min    │
    └─────────────────────────────────┘
```

**Si pas de ligne directe** → correspondance :
```
Origine → lignes_O = {T_3, C_3}
Destination → lignes_D = {M_D, C_8}
Pas d'intersection directe.

Pour chaque lieu hub (21 lieux) :
    lignes_hub = get_lieux_transports(hub_id)
    match_O = lignes_O ∩ lignes_hub  → ex: C_3 via Part-Dieu
    match_D = lignes_D ∩ lignes_hub  → ex: M_D via Part-Dieu
    Si match_O ET match_D → correspondance trouvée !

Résultat :
    Segment 1 : 🚌 C3 (origine → Part-Dieu) ~12 min + retard
    ⬇ Correspondance Part-Dieu (~3 min marche)
    Segment 2 : 🚇 Métro D (Part-Dieu → destination) ~8 min + retard
    Total : ~25 min
```

**Limites Phase 1** (affichées clairement à l'usager) :
- Fréquences, pas horaires exacts ("~toutes les 8 min", pas "prochain à 14:03")
- 21 lieux uniquement (= les O/D du référentiel — ce sont les mêmes que la
  selectbox, donc 100% de couverture pour les trajets possibles dans l'UI)
- Maximum 1 correspondance (direct ou 1 hub)
- Retards = moyenne observée sur 7j à cette heure, pas prédiction ML

### Phase 2 — GTFS complet + Raptor (sprint futur)

- Ingestion GTFS TCL (`stops.txt`, `stop_times.txt`, `routes.txt`, `trips.txt`,
  `shapes.txt`) depuis data.grandlyon.com
- Tables `bronze.gtfs_*` → `silver.gtfs_*` → `gold.gtfs_stop_times`
- Router Raptor (Range-RAPTOR) : itinéraire optimal multi-transfer
- Horaires théoriques exacts + ajustement temps réel SIRI
- Couverture : tous les arrêts TCL (~3000), pas juste 21 lieux

---

## Tâches Sprint 14

### T1 — UI : refonte multiselect modes (0.5j)

**Fichier** : `dashboard/components/widgets/usager/search_bar.py`

| Avant | Après |
|-------|-------|
| `["🚇 Métro", "🚊 Tram", "🚌 Bus", "🚲 Vélov", "🚗 Voiture", "🚶 Marche"]` | `["🚌 Transport en commun", "🚲 Vélov", "🚗 Voiture"]` |
| Default : Métro + Tram + Bus + Vélov + Marche | Default : Transport en commun + Vélov |

- Supprimer Marche du multiselect
- Fusionner Métro + Tram + Bus → "🚌 Transport en commun"
- Mettre à jour `Usager_1_Mon_Trajet.py` : `has_tc = any("Transport en commun" in m for m in modes)`

**Critère d'acceptation** : le multiselect affiche 3 choix. "Transport en
commun" sélectionné par défaut.

### T2 — Routing TC : `plan_transit_trip()` (2j)

**Fichier** : `src/routing/pathfinder_multimodal.py` (nouveau code, même module)

```python
@dataclass
class TransitSegment:
    line_ref: str          # ex: 'M_A'
    line_mode: str         # metro | tram | bus | funicular
    line_label: str        # ex: '🚇 Métro A'
    stop_origin: str       # ex: 'Laurent Bonnevay'
    stop_dest: str         # ex: 'Confluence'
    distance_m: int        # à pied jusqu'à l'arrêt
    cadence_min: float     # fréquence (min)
    wait_estimate_min: float  # cadence / 2
    delay_avg_min: float   # retard moyen observé (7j)
    duration_estimate_min: float  # temps total segment

@dataclass
class TransitItinerary:
    segments: list[TransitSegment]
    total_duration_min: float
    total_walk_m: int       # marche totale (accès arrêts)
    n_transfers: int        # 0 = direct, 1 = 1 correspondance
    transfer_hub: str | None  # lieu de correspondance
    confidence: float       # basée sur n_observations cadence

def plan_transit_trip(
    origin: str,
    destination: str,
) -> TransitItinerary | None:
    """Calcule un itinéraire TC entre 2 lieux du référentiel.

    Algorithme :
    1. Résoudre origin/dest → lieu_id (referentiel.lieux_lyon)
    2. get_lieux_transports(lieu_id) pour O et D
    3. Intersection lignes → trajet direct si possible
    4. Sinon : chercher hub parmi les 21 lieux
    5. Pour chaque segment : cadence + retard moyen
    6. Trier par durée totale, retourner le meilleur
    """
```

**Sous-tâches** :
- `_resolve_lieu_id(text: str) -> int | None` : résoudre nom lieu → lieu_id
- `_find_direct_routes(lines_o, lines_d) -> list[TransitSegment]`
- `_find_transfer_routes(lines_o, lines_d, all_lieux) -> list[TransitItinerary]`
- `_estimate_segment_duration(line_ref, distance_m) -> float` : estimation basée
  sur cadence + vitesse moyenne par mode (métro ~35 km/h, tram ~20 km/h, bus ~15 km/h)
- `_get_current_delay(line_ref) -> float` : retard moyen observé sur la tranche horaire

**Critère d'acceptation** : `plan_transit_trip("Villeurbanne", "Confluence, Lyon")`
retourne un `TransitItinerary` avec au moins 1 segment, durée > 0, retard > 0.

### T3 — Helper DB + cache (0.5j)

**Fichiers** : `src/data/db_query.py`, `src/data/data_loader.py`, `dashboard/components/data_cache.py`

- `db_query.get_transit_options(origin_lieu_id, dest_lieu_id)` : JOIN lieux_transports
  O ∩ D pour lignes directes
- `data_loader.load_transit_itinerary(origin, destination)` : wrapper fail-loud
- `data_cache.cached_transit_itinerary` : TTL 30s (Streamlit cache)
- Réutiliser `get_cadence_for_line()` et `get_bus_delay_segments()` existants

**Critère d'acceptation** : helpers appelables, fail loud si DB indispo
(`DashboardDataError`).

### T4 — Widget `transit_trip.py` (1.5j)

**Fichier** : `dashboard/components/widgets/usager/transit_trip.py` (nouveau)

Affichage du `TransitItinerary` :

```
┌─────────────────────────────────────────────────────────┐
│ 🚌 Transport en commun — Villeurbanne → Confluence      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🚶 3 min à pied → arrêt Charpennes (100m)              │
│                                                         │
│  🚇 Métro A  ───────────────────────────── ~12 min      │
│  Charpennes → Bellecour                                 │
│  Fréquence : toutes les ~4 min                          │
│  Retard moyen observé : +0.8 min                        │
│                                                         │
│  ⬇ Correspondance Bellecour (~2 min)                    │
│                                                         │
│  🚇 Métro D  ───────────────────────────── ~6 min       │
│  Bellecour → Confluence                                 │
│  Fréquence : toutes les ~5 min                          │
│  Retard moyen observé : +1.1 min                        │
│                                                         │
│  🚶 1 min à pied → destination (80m)                    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ 🕐 Durée totale : ~26 min  │  🚶 Marche : 180m          │
│ ⏱ Attente estimée : ~5 min │  🔄 1 correspondance       │
│ ⚠️ Retard cumulé : +1.9 min │  📊 Confiance : 82%       │
├─────────────────────────────────────────────────────────┤
│ ℹ️ Fréquences estimées — horaires exacts : version      │
│    future (GTFS). Retards = moyenne 7j sur cette        │
│    tranche horaire.                                     │
└─────────────────────────────────────────────────────────┘
```

**KPI cards** (4 colonnes st.metric) :
- 🕐 Durée totale
- 🚶 Marche totale
- 🔄 Correspondances
- ⚠️ Retard cumulé

**Détails par segment** : expander avec cadence, retard, confiance.

**Disclaimer** (toujours affiché) :
> *Fréquences estimées à partir des cadences observées. Pas d'horaires exacts
> (données GTFS non encore ingérées). Retards = moyenne sur 7 jours glissants
> à cette tranche horaire.*

**Critère d'acceptation** : widget affiche un itinéraire TC lisible avec
lignes, arrêts, fréquences, retards. Message d'erreur clair si aucun trajet
trouvé.

### T5 — Câblage page `Usager_1_Mon_Trajet.py` (0.5j)

**Fichier** : `dashboard/pages/Usager_1_Mon_Trajet.py`

- Ajouter `has_tc = any("Transport en commun" in m for m in modes)`
- Section `if has_tc:` entre météo et Vélov :
  ```python
  if has_tc:
      st.markdown("### 🚌 Trajet transport en commun")
      render_transit_trip(
          origin=search["origin"],
          destination=search["destination"],
      )
  ```
- Retirer toute référence à `Marche` dans les conditions
- Importer `render_transit_trip` dans `__init__.py`

**Critère d'acceptation** : clic "Trouver mon trajet" avec TC sélectionné
affiche l'itinéraire TC.

### T6 — Vélov : cards stations avec dispo temps réel (1j)

**Fichier** : `dashboard/components/widgets/usager/velov_trip.py` (modifié)

**Problème** : les données vélos/docks dispo existent déjà dans `VelovSegment`
(`n_bikes_depart`, `n_docks_arrive`) et dans `VelovItinerary`
(`origin_alternatives`, `dest_alternatives`). Mais l'affichage les enterre dans
les popups Folium et l'expander "Détail segments". L'usager doit cliquer 2 fois
pour savoir si la borne a des vélos.

**Solution** : ajouter 2 **station cards prominentes** entre le résumé KPIs et
la carte, affichées directement (pas dans un expander).

```
┌─────────────────────────────────────────────────────────┐
│ 🕐 12.3 min  │  📏 3.2 km  │  🚲 15 km/h  │  ✅ OK     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │ 🟢 BORNE DÉPART       │  │ 🔴 BORNE ARRIVÉE     │     │
│  │ Charpennes            │  │ Confluence            │     │
│  │                       │  │                       │     │
│  │  🚲 12 vélos dispo    │  │  🚲 3 vélos           │     │
│  │  ├── 8 mécaniques     │  │  🅿️ 18 places dispo  │     │
│  │  └── 4 électriques    │  │                       │     │
│  │  🅿️ 8 places dispo   │  │  ✅ Station OK        │     │
│  │                       │  │                       │     │
│  │  📍 120m à pied (2min)│  │  📍 80m à pied (1min) │     │
│  │  ✅ Station OK        │  │                       │     │
│  └──────────────────────┘  └──────────────────────┘     │
│                                                         │
│  [carte Folium]                                         │
│  [détail segments]                                      │
└─────────────────────────────────────────────────────────┘
```

**Données déjà disponibles** (via `VelovSegment` + `origin_station`/`dest_station` dans `plan_velov_trip()`) :

| Donnée | Source | Champ |
|--------|--------|-------|
| Nom station | `VelovSegment.from_label` / `to_label` | Smart routing |
| Vélos disponibles | `VelovSegment.n_bikes_depart` | `silver.velov_clean` |
| Docks disponibles | `VelovSegment.n_docks_arrive` | `silver.velov_clean` |
| Statut (OK/FAIBLE/VIDE/PLEINE) | `origin_alternatives[0].status` | Smart routing |
| Distance à pied | `VelovSegment.distance_m` | Haversine |
| Vélos méca vs élec | **À ajouter** | `silver.velov_clean` |

**Sous-tâches** :
1. **`_render_station_cards(itin)`** : nouvelle fonction, 2 colonnes `st.columns(2)`,
   chaque card avec : nom, vélos (méca + élec si dispo), docks, statut coloré, distance à pied.
2. **Enrichir `VelovSegment`** : ajouter `n_bikes_mechanical` et `n_bikes_electrical`
   (optionnels, None si pas dans la source). GBFS Vélov fournit `num_bikes_available_types.mechanical`
   et `num_bikes_available_types.ebike` — vérifier si `silver.velov_clean` les expose.
3. **Couleur statut** : vert (OK, ≥5 vélos/docks), orange (FAIBLE, 1-4), rouge (VIDE/PLEINE, 0).
4. **Câblage** : insérer `_render_station_cards(itin)` entre `_render_velov_summary()` et la carte.

**Critère d'acceptation** : après "Trouver mon trajet" avec Vélov sélectionné,
2 cards station visibles immédiatement sans clic, avec vélos dispo, places dispo,
statut coloré, distance à pied.

### T7 — Tests (1j)

**Fichiers** : `tests/routing/test_transit_trip.py`, `tests/persona/test_transit_widget.py`, `tests/persona/test_velov_station_cards.py`

| Catégorie | Tests | Description |
|-----------|-------|-------------|
| Routing TC direct | 5 | Villeurbanne→Bellecour (M_A direct), Part-Dieu→Confluence, etc. |
| Routing TC correspondance | 5 | Bron→Croix-Rousse (pas de ligne directe) |
| Routing TC impossible | 3 | Lieux sans TC, même lieu O/D, lieu inexistant |
| Cadence + retard | 4 | Weekday HPM vs dimanche, tranche sans données |
| Widget TC smoke | 3 | Render sans crash, message erreur, disclaimer présent |
| Multiselect UI | 3 | 3 options, pas de Marche, TC par défaut |
| Vélov station cards | 5 | Card départ OK, card arrivée PLEINE, méca+élec, 0 vélos rouge, distance à pied |
| Régression Vélov/Voiture | 3 | Modes existants toujours fonctionnels |

**Cible** : ~31 tests verts, 0 régression sur les 218 existants.

---

## Estimation effort

| Tâche | Effort | Dépendances |
|-------|--------|-------------|
| T1 — UI multiselect | 0.5j | — |
| T2 — `plan_transit_trip()` | 2j | — |
| T3 — Helpers DB + cache | 0.5j | T2 |
| T4 — Widget `transit_trip.py` | 1.5j | T2, T3 |
| T5 — Câblage page | 0.5j | T1, T4 |
| T6 — Vélov station cards | 1j | — |
| T7 — Tests | 1j | T2, T4, T5, T6 |
| **Total** | **7j** | |

Parallélisation possible : T1 (UI), T2 (routing TC), T6 (Vélov cards) en
parallèle. T3+T4 séquentiels après T2. T5+T7 en fin.

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|------------|--------|------------|
| Correspondance introuvable (21 lieux trop sparse) | Moyenne | Trajet "pas de résultat" | Fallback : afficher lignes disponibles O et D séparément + suggestion hub |
| Cadence absente pour une ligne/tranche | Moyenne | Estimation imprécise | Fallback : cadence moyenne toutes tranches. Afficher confiance basse. |
| Retard = 0 (pas de données SIRI pour cette ligne) | Faible | UX trompeuse | Afficher "retard : données insuffisantes" au lieu de "0 min" |
| Temps de trajet inter-arrêts imprécis | Haute | Durée totale approximative | Vitesse moyenne par mode (métro 35, tram 20, bus 15 km/h). Afficher "~" systématiquement. |

---

## Fichiers impactés

### Modifiés

| Fichier | Changement |
|---------|-----------|
| `dashboard/components/widgets/usager/search_bar.py` | Multiselect 3 options, retirer Marche |
| `dashboard/pages/Usager_1_Mon_Trajet.py` | Section `if has_tc:`, retirer refs Marche |
| `dashboard/components/widgets/usager/__init__.py` | Export `render_transit_trip` |
| `src/routing/pathfinder_multimodal.py` | `plan_transit_trip()` + dataclasses + `n_bikes_mechanical`/`n_bikes_electrical` sur VelovSegment |
| `src/data/db_query.py` | `get_transit_options()` |
| `src/data/data_loader.py` | `load_transit_itinerary()` |
| `dashboard/components/data_cache.py` | `cached_transit_itinerary()` |
| `dashboard/components/widgets/usager/velov_trip.py` | `_render_station_cards()` — cards bornes départ/arrivée avec dispo temps réel |
| `src/config.py` | Version → `0.7.0` |
| `pyproject.toml` | Version → `0.7.0` |

### Nouveaux

| Fichier | Rôle |
|---------|------|
| `dashboard/components/widgets/usager/transit_trip.py` | Widget affichage itinéraire TC |
| `tests/routing/test_transit_trip.py` | Tests routing TC |
| `tests/persona/test_transit_widget.py` | Tests widget TC |
| `tests/persona/test_velov_station_cards.py` | Tests cards stations Vélov |

### Non impactés (vérification régression)

- `dashboard/components/widgets/usager/itinerary.py` — inchangé (voiture)
- `src/routing/pathfinder.py` — inchangé (Dijkstra voiture)

---

## Critères de validation sprint

- [x] Multiselect affiche 3 modes : TC, Vélov, Voiture. Pas de Marche. ✅ `st.segmented_control` (commit `a909d5a`)
- [x] TC sélectionné par défaut ✅ `default="🚌 Transport en commun"`
- [x] Clic "Trouver mon trajet" avec TC → affiche itinéraire avec lignes concrètes ✅ `render_transit_trip()`
- [x] Trajet direct affiché quand ligne commune existe (ex: Villeurbanne → Bellecour via M_A) ✅ `plan_transit_trip()`
- [x] Correspondance simple affichée quand pas de ligne directe ✅ hub search 21 lieux
- [x] Fréquence affichée par segment ("~toutes les X min") ✅ `cadence_min` dans `TransitSegment`
- [x] Retard moyen affiché par segment (données SIRI 7j) ✅ `delay_avg_min`
- [x] Disclaimer visible : "fréquences estimées, pas horaires exacts" ✅ `_render_transit_disclaimer()`
- [x] Marche d'accès aux arrêts affichée (distance_m du référentiel) ✅ `distance_walk_to_m`/`distance_walk_from_m`
- [x] **Vélov** : 2 station cards (départ + arrivée) visibles immédiatement après recherche ✅ `_render_station_cards()`
- [x] **Vélov** : vélos disponibles + places disponibles affichés avec couleur statut ✅ `_render_single_station_card()`
- [x] **Vélov** : mécaniques vs électriques séparés si données GBFS disponibles ✅ `n_bikes_mechanical`/`n_bikes_electrical` dans `VelovSegment`
- [x] **Vélov** : distance à pied vers chaque borne affichée ✅
- [x] ~249 tests verts (218 existants + ~31 nouveaux), 0 régression ✅ **251 passed, 4 skipped, 14 deselected** (+33 vs Sprint 13+)
- [x] ruff clean ✅ 8 erreurs cosmétiques pré-existantes (RUF001/002, B905, E741, W291)
- [x] Modes Vélov et Voiture fonctionnent comme avant (régression 0) ✅

---

## Hors scope (Phase 2 — sprint futur)

- Ingestion GTFS TCL (stops.txt, stop_times.txt, routes.txt, trips.txt)
- Horaires théoriques exacts ("prochain départ à 14:03")
- Router Raptor multi-correspondances
- Couverture tous arrêts TCL (~3000 vs 21 lieux actuels)
- Prédiction ML retard bus (XGBoost delay — pilier ML #2 Phase 3)
- Carte Folium avec tracé TC (shapes.txt GTFS nécessaire)
