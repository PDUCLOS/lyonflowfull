# Audit complet Dashboard — Sprint 15+ (v0.7.1)

> **Date** : 2026-06-20  
> **Périmètre** : 18 pages × 3 personas · 51 widgets  
> **Méthode** : analyse statique du code source (pas de rendu live)  
> **Sévérité** : 🔴 Critique · 🟠 Important · 🟡 Mineur · ✅ OK

---

## Table des matières

1. [Synthèse exécutive](#1-synthèse-exécutive)
2. [Persona Pro TCL (6 pages)](#2-persona-pro-tcl)
3. [Persona Usager (2 pages)](#3-persona-usager)
4. [Persona Élu (5 pages)](#4-persona-élu)
5. [Problèmes transversaux](#5-problèmes-transversaux)
6. [Mécanisme `is_widget_visible()` — Extension proposée](#6-mécanisme-is_widget_visible--extension-proposée)
7. [Pattern de chargement différé (button-gate)](#7-pattern-de-chargement-différé-button-gate)
8. [Inventaire coût de rendu par widget](#8-inventaire-coût-de-rendu-par-widget)
9. [Priorité d'implémentation](#9-priorité-dimplémentation)

---

## 1. Synthèse exécutive

### Constats majeurs

| # | Problème | Sévérité | Impact |
|---|----------|----------|--------|
| 1 | **Pro_3** : 3 widgets lourds (Folium + 2× Plotly) chargent en séquentiel à chaque auto-refresh 30s | 🔴 | Page inutilisable sur VPS 12 Go — chaque cycle complet ~8-15s |
| 2 | **Pro_1** : 2 pydeck maps dans des `st.tabs` — **les deux s'exécutent** à chaque run (tabs Streamlit ne diffèrent PAS le calcul) | 🔴 | Double rendu GPU/CPU inutile toutes les 30s |
| 3 | **Widgets Sprint 15+ non câblés** : `mode_comparison` et `mode_summary` sont construits mais **jamais appelés** dans Usager_1 | 🟠 | Feature livrée mais invisible pour l'usager |
| 4 | **Lisibilité** : 23+ widgets utilisent des `font-size` inline de 0.70rem à 0.85rem (illisibles sur écran standard) | 🟠 | Textes microscopiques sur alertes, KPI sublabels, badges, segments |
| 5 | **Pas de `is_widget_visible()` effectif** : le mécanisme existe dans `PersonaManager` + `personas.yaml` mais aucune page ne l'appelle | 🟡 | Gating par persona non opérationnel |
| 6 | **Calculs itinéraire non cachés** : `render_velov_trip()` et `render_itinerary_result()` recalculent à chaque rerun | 🟡 | Lent à chaque auto-refresh 60s quand résultats affichés |

### Chiffres clés

- **Widgets lourds** (>500ms estimé) : 11 sur 51
- **Widgets à font-size < 0.9rem** : 23+
- **Widgets Sprint 15+ à câbler** : 2 (mode_comparison, mode_summary)
- **Pages nécessitant du button-gating** : 3 (Pro_1, Pro_3, Usager_1)

---

## 2. Persona Pro TCL

### 2.1. Pro_1_PCC_Live — Vue 4 quadrants temps réel

**Fichier** : `dashboard/pages/Pro_1_PCC_Live.py`  
**Auto-refresh** : 30s  
**Widgets** : 6 (network_map, traffic_map, alerts, otp_heatmap_mini, bottleneck_ranking, line_kpis)

#### 🔴 P1-1. Double rendu pydeck dans `st.tabs`

**Constat** : lignes 46-57 — `render_network_map()` et `render_traffic_map()` sont dans deux tabs, mais **Streamlit exécute le contenu des deux tabs** à chaque run, quel que soit l'onglet actif. Les deux maps pydeck (WebGL) se calculent toutes les 30s.

**Solution** : remplacer par un button-gate `session_state` (voir [§7](#7-pattern-de-chargement-différé-button-gate)). Afficher la carte bus par défaut, carte trafic sur clic.

```python
# AVANT (exécute les deux)
tab_bus, tab_traffic = st.tabs(["🚌 Bus GPS", "🚗 Charge trafic"])
with tab_bus:
    render_network_map(height=320)
with tab_traffic:
    render_traffic_map(height=320, ...)

# APRÈS (un seul rendu)
map_choice = st.radio("Carte", ["🚌 Bus GPS", "🚗 Charge trafic"],
                       horizontal=True, key="pro1_map_choice")
if map_choice == "🚌 Bus GPS":
    render_network_map(height=320)
else:
    render_traffic_map(height=320, ...)
```

#### 🟠 P1-2. Alertes illisibles (0.75rem)

**Constat** : lignes 77-81 — description et action des alertes en `font-size:0.75rem`. Sur un écran 1080p, ≈ 9.6px — au-dessous du seuil de lisibilité WCAG.

**Solution** : passer description à `0.9rem`, action à `0.88rem`.

```
Fichier: dashboard/pages/Pro_1_PCC_Live.py
Ligne 77: font-size:0.75rem → font-size:0.9rem
Ligne 80: font-size:0.75rem → font-size:0.88rem
```

#### 🟠 P1-3. Bottleneck ranking illisible (0.75rem)

**Constat** : lignes 108-115 — ranking en `0.85rem` (OK) mais détail en `0.75rem` (trop petit).

**Solution** : passer à `0.85rem`.

```
Fichier: dashboard/pages/Pro_1_PCC_Live.py
Ligne 112: font-size:0.75rem → font-size:0.85rem
```

#### 🟡 P1-4. OTP Heatmap comprimée (280px)

**Constat** : `render_otp_heatmap_mini(height=280)` — heatmap Plotly à 280px de hauteur, les labels horaires se chevauchent.

**Solution** : passer à `height=350`, ou ajouter un bouton "Voir en plein écran" qui renvoie vers Pro_2.

#### 🟡 P1-5. line_kpis charge toutes les lignes

**Constat** : ligne 122 — `render_line_kpis()` sans limit charge les 155 lignes TCL. Rendu lourd sous le fold.

**Solution** : `render_line_kpis(top_n=20)` par défaut + bouton "Voir toutes les lignes".

---

### 2.2. Pro_3_Correlation — Corrélation bus × trafic

**Fichier** : `dashboard/pages/Pro_3_Correlation.py`  
**Auto-refresh** : 30s  
**Widgets** : 7 (line_selector, correlation_matrix, segment_table, cause_analysis, **bus_traffic_spatial**, **coherence_scatter**, **multimodal_heatmap**)

#### 🔴 P3-1. Triple widget lourd sans gate — page la plus critique

**Constat** : lignes 88-105 — trois widgets Sprint 13+/15+ s'empilent séquentiellement :
1. `render_bus_traffic_spatial()` — Plotly scatter + KPI + top 20 (requête MV `gold.mv_bus_traffic_spatial`)
2. `render_coherence_scatter()` — 3 charts Plotly + 4 KPI + drift table (2 requêtes PostGIS)
3. `render_multimodal_heatmap()` — Folium map HTML + rectangles + 4 KPI + top 15 table (requête MV `gold.mv_multimodal_grid`)

**Tous trois se rechargent à chaque auto-refresh 30s.** Temps estimé total : 5-15s selon charge VPS.

**Solution** : button-gate avec `st.session_state` pour chacun. Afficher un résumé léger (1-2 KPI) + bouton "Charger l'analyse détaillée".

```python
# Pattern recommandé pour chaque widget lourd
st.markdown("##### Corrélation bus × trafic spatialisée")
if st.button("📊 Charger l'analyse spatiale", key="load_bus_spatial"):
    st.session_state["show_bus_spatial"] = True
if st.session_state.get("show_bus_spatial"):
    render_bus_traffic_spatial(line_id=target_line)
    if st.button("Masquer", key="hide_bus_spatial"):
        st.session_state["show_bus_spatial"] = False
```

> **Important** : un simple `st.button()` retourne `True` uniquement au clic — au prochain auto-refresh (30s), le widget disparaît. Il faut impérativement utiliser `st.session_state` pour persister le choix.

#### 🟠 P3-2. Sublabels KPI à 0.75rem dans les 3 widgets

**Constat** : `bus_traffic_spatial.py`, `coherence_scatter.py`, `multimodal_heatmap.py` — tous ont des sublabels KPI en `0.75rem`.

**Solution** : passer à `0.88rem` dans les 3 fichiers.

```
dashboard/components/widgets/pro_tcl/bus_traffic_spatial.py : 0.75rem → 0.88rem (4 occurrences)
dashboard/components/widgets/pro_tcl/coherence_scatter.py : 0.75rem → 0.88rem (6 occurrences)
dashboard/components/widgets/pro_tcl/multimodal_heatmap.py : 0.75rem → 0.88rem (4 occurrences)
```

---

### 2.3. Pro_2_Heatmap_OTP

**Fichier** : `dashboard/pages/Pro_2_Heatmap_OTP.py`  
**Widgets** : otp_heatmap (version pleine)

#### ✅ OK

Version pleine de la heatmap avec hauteur suffisante. Pas de problème majeur identifié.

---

### 2.4. Pro_4_Simulateur

**Fichier** : `dashboard/pages/Pro_4_Simulateur.py`  
**Widgets** : line_selector, frequency_slider, otp_projection, hastus_export

#### ✅ Déjà bon

L'export Hastus est déjà derrière un bouton. Le simulateur est interactif par nature.

---

### 2.5. Pro_6_Pipeline_Mgmt

**Fichier** : `dashboard/pages/Pro_6_Pipeline_Mgmt.py`

#### 🟠 P6-1. Health checks bloquants

**Constat** : les health checks (connectivité DB, Airflow, MLflow, MinIO) s'exécutent séquentiellement au chargement de la page. Spinner 5-10s pendant lequel rien ne s'affiche.

**Solution** : afficher d'abord les DAG KPIs (données cachées), puis les health checks dans un expander "🩺 Diagnostic connectivité" (le calcul s'exécute quand même, mais l'utilisateur n'attend pas).

---

### 2.6. Pro_7_Model_Monitoring

**Fichier** : `dashboard/pages/Pro_7_Model_Monitoring.py`

#### 🟡 P7-1. 9 requêtes SQL séquentielles

**Constat** : chaque section (XGBoost, GNN, Vélov, drift) fait 2-3 requêtes SQL non batchées.

**Solution** : regrouper en 1-2 requêtes avec CTE ou créer une vue matérialisée `gold.mv_model_monitoring_summary`.

---

## 3. Persona Usager

### 3.1. Usager_1_Mon_Trajet — Page principale

**Fichier** : `dashboard/pages/Usager_1_Mon_Trajet.py`  
**Auto-refresh** : 60s  
**Widgets** : search_bar, weather, velov_widget, traffic_widget, velov_trip, itinerary_result, transit_trip, traffic_map_compact, velov_map_compact, lieux_velov_map

#### 🟠 U1-1. Widgets Sprint 15+ non câblés (mode_comparison, mode_summary)

**Constat** : `render_mode_comparison()` et `render_mode_summary()` sont :
- ✅ Implémentés dans `dashboard/components/widgets/usager/`
- ✅ Exportés dans `__init__.py`
- ✅ Cache prêt dans `data_cache.py` (`cached_eco_impact`)
- ❌ **Jamais importés ni appelés dans `Usager_1_Mon_Trajet.py`**

Le comparateur de modes (temps/coût/éco) et le résumé modal — la feature phare du Sprint 15+ pour l'usager — sont construits mais invisibles.

**Solution** : câbler après la barre de recherche, avant les résultats par mode. Affichage conditionnel quand `results_loaded` :

```python
# Après ligne 69 (if st.session_state.get("results_loaded"):)
# Ajout : comparateur de modes
from dashboard.components.widgets.usager import render_mode_comparison, render_mode_summary
from dashboard.components.data_cache import cached_eco_impact

if len(modes) >= 2:
    st.markdown("### ⚖️ Comparaison des modes")
    impacts = {}
    for mode in modes:
        impacts[mode] = cached_eco_impact(mode=mode, distance_km=dist_km)
    render_mode_comparison(
        impacts=impacts,
        optimize_for=search.get("optimize_for", "temps"),
    )
```

> **Note** : la `search_bar` a déjà un radio "Optimiser pour" (temps/coût) ajouté au Sprint 15+. Il suffit de passer cette valeur à `render_mode_comparison()`.

#### 🟠 U1-2. Calculs itinéraire non cachés

**Constat** : `render_velov_trip()` (ligne 137) et `render_itinerary_result()` (ligne 182) recalculent à chaque rerun, y compris à chaque auto-refresh 60s. Le calcul d'itinéraire voiture fait un Dijkstra sur le graphe H3.

**Atténuation existante** : `render_itinerary_result()` est déjà derrière un bouton "🚗 Calculer l'itinéraire" (ligne 176) — bon pattern. **Mais** `render_velov_trip()` se lance automatiquement dès que le mode Vélov est sélectionné.

**Solution** : 
1. Ajouter un bouton gate pour `render_velov_trip()` identique au pattern voiture
2. Stocker le résultat dans `st.session_state` pour éviter le recalcul à chaque refresh

```python
# Pattern recommandé
if st.button("🚲 Calculer le trajet Vélov", key="velov_calc_btn"):
    result = render_velov_trip(origin=..., destination=..., ...)
    st.session_state["velov_trip_result"] = result
```

#### 🟠 U1-3. Fonts illisibles sur les widgets usager

| Widget | Fichier | Taille actuelle | Taille recommandée | Éléments |
|--------|---------|-----------------|--------------------|----|
| velov_widget | `velov_widget.py` | 0.7rem | 0.88rem | Texte prédiction |
| velov_widget | `velov_widget.py` | 0.85rem | 0.95rem | Nom station |
| velov_trip | `velov_trip.py` | 0.7-0.75rem | 0.88rem | Labels station cards |
| mode_comparison | `mode_comparison.py` | 0.7rem | 0.88rem | Badge gagnant |
| traffic_widget | `traffic_widget.py` | 0.75rem | 0.88rem | Label état trafic |
| alert_card | `alert_card.py` | 0.85-0.86rem | 0.92rem | Description + action |
| transit_trip | `transit_trip.py` | 0.7-0.75rem | 0.88rem | Badges + segments |
| itinerary | `itinerary.py` | 0.8-0.85rem | 0.92rem | Segment cards |

#### 🟡 U1-4. Deux cartes Folium sous le fold

**Constat** : lignes 192-199 — `render_lieux_velov_map()` et `render_velov_map_compact()` en séquence sous le fold. Deux rendus Folium HTML (lourds).

**Solution** : fusionner en une seule carte avec toggle layers, ou mettre la deuxième derrière un bouton.

---

### 3.2. Usager_2_Alertes

**Fichier** : `dashboard/pages/Usager_2_Alertes.py`

#### 🟡 U2-1. alert_card font illisible

Même problème que U1-3 : descriptions à 0.85rem. Passer à 0.92rem.

---

## 4. Persona Élu

### 4.1. Elu_1_Synthese — Synthèse exécutive

**Fichier** : `dashboard/pages/Elu_1_Synthese.py`  
**Auto-refresh** : 300s  
**Widgets** : kpi_cards, executive_summary, **network_health_gauge** (Sprint 15+), trend_chart, top_decisions

#### 🟠 E1-1. network_health_gauge : 5 sous-requêtes lourdes

**Constat** : `render_network_health_gauge()` (câblé ligne 42) fait 5 requêtes d'availability check (PostgreSQL, Airflow, MLflow, SIRI, Vélov) pour calculer un score 0-100. Sous-jauges Plotly à 180px de hauteur.

**Impact** : modéré grâce au refresh 300s (vs 30s Pro TCL). Mais le premier chargement bloque.

**Solution** : 
1. Cacher le résultat `@st.cache_data(ttl=300)` (le widget lui-même, pas juste les données)
2. Réduire les 5 requêtes à 1 seule appel à `gold.fn_network_health_score()` (la fonction SQL existe déjà via migration 019)

#### 🟡 E1-2. Sous-jauges trop petites (180px)

**Constat** : les 5 sous-jauges Plotly sont à `height=180` — les labels se tronquent.

**Solution** : passer à `height=220` ou afficher en 2 rangées de 3+2 au lieu de 5 en ligne.

---

### 4.2. Elu_2_Bottlenecks — Bottlenecks prioritaires

**Fichier** : `dashboard/pages/Elu_2_Bottlenecks.py`

#### 🟠 E2-1. Grille 7 colonnes illisible

**Constat** : `bottleneck_ranking.py` — grille 7 colonnes à `0.85rem` avec détails à `0.75rem`. Sur écran < 1440px, les colonnes wrappent et le tableau devient illisible.

**Solution** :
1. Passer les détails à `0.85rem` minimum
2. Utiliser `st.dataframe()` avec `column_config` au lieu de HTML brut — gestion native du scroll horizontal
3. Ou : cacher les colonnes secondaires (ROI, voyageurs) dans un expander par ligne

---

### 4.3. Elu_3_Avant_Apres

**Fichier** : `dashboard/pages/Elu_3_Avant_Apres.py`

#### 🟠 E3-1. Cards avant/après non adaptatives

**Constat** : les cartes avant/après utilisent des `st.columns([1,1])` avec contenu HTML inline. Sur mobile ou petit écran, les colonnes se compressent au point de rendre les chiffres illisibles.

**Solution** : utiliser `st.metric()` natif pour les KPIs (auto-responsive) + cards HTML uniquement pour le commentaire.

---

### 4.4. Elu_4_Simulateur

#### ✅ OK

Interactif par nature (sliders + projection). Pas de problème majeur.

---

### 4.5. Elu_5_Rapport

**Fichier** : `dashboard/pages/Elu_5_Rapport.py`

#### 🟡 E5-1. delta_kpis : labels à 0.7rem

**Constat** : `delta_kpis.py` — labels à `0.7rem`, valeurs à `1.4rem`. Contraste de taille excessif, labels quasi invisibles.

**Solution** : labels à `0.85rem`, valeurs à `1.3rem` (ratio plus équilibré).

---

## 5. Problèmes transversaux

### 5.1. 🟠 Fonts inline non centralisables

**Constat** : les `font-size` sont en `style="..."` inline dans chaque widget HTML. Les styles inline ont une spécificité CSS supérieure à toute règle centrale dans `theme.py` — **sauf avec `!important`**.

**Options** :

| Option | Effort | Risque | Recommandation |
|--------|--------|--------|----------------|
| A. Éditer chaque widget (23+ fichiers) | Élevé (~2h) | Faible | ✅ Propre mais long |
| B. Ajouter un `font-size: 0.88rem !important` global dans `theme.py` pour `.lyonflow-card *` | Faible (1 ligne) | Moyen (peut casser des layouts) | ⚠️ Quick win mais risque effets de bord |
| C. Créer des classes CSS dans `theme.py` (`lyf-label`, `lyf-sublabel`, `lyf-kpi-value`) et migrer progressivement | Moyen (~1h setup + migration widget par widget) | Faible | ✅ **Recommandé** — investissement moyen, maintenable |

**Recommandation** : Option C. Ajouter dans `theme.py` :

```css
.lyf-sublabel { font-size: 0.88rem !important; opacity: 0.7; }
.lyf-label    { font-size: 0.95rem !important; }
.lyf-value    { font-size: 1.3rem !important; font-weight: 700; }
.lyf-badge    { font-size: 0.82rem !important; padding: 0.15rem 0.5rem; border-radius: 12px; }
```

Puis migrer les widgets progressivement de `style="font-size:0.75rem"` vers `class="lyf-sublabel"`.

### 5.2. 🟡 Auto-refresh + button-gate : piège `st.button()`

**Constat critique** : `st.button()` retourne `True` uniquement au moment du clic. Au prochain auto-refresh (30s Pro, 60s Usager), le bouton repasse à `False` et **le widget disparaît**.

**Pattern correct** :

```python
# ✅ Persiste entre refreshes
if st.button("Charger", key="load_x"):
    st.session_state["show_x"] = True

if st.session_state.get("show_x"):
    render_heavy_widget()
    if st.button("Masquer", key="hide_x"):
        st.session_state["show_x"] = False
```

```python
# ❌ Widget disparaît après 30s
if st.button("Charger"):
    render_heavy_widget()  # visible 1 seul cycle
```

Usager_1 utilise déjà ce pattern correct (ligne 65-68 avec `results_loaded`). À répliquer partout.

### 5.3. 🟡 `st.tabs` et `st.expander` ne diffèrent PAS le calcul

**Constat** : dans Streamlit, les corps des `st.tabs` et `st.expander` s'exécutent **à chaque run**, que l'onglet soit actif ou l'expander ouvert ou non. Utiliser des tabs pour "cacher" un widget lourd ne réduit **aucun** temps de calcul.

**Conséquence** : les 2 maps pydeck de Pro_1 (dans `st.tabs`) se calculent toutes les deux à chaque refresh 30s. Le seul moyen de différer est le pattern `session_state` + `st.radio` ou bouton gate.

---

## 6. Mécanisme `is_widget_visible()` — Extension proposée

### État actuel

- `PersonaManager.is_widget_visible(widget_name)` existe (`src/persona/manager.py:149`)
- `personas.yaml` a des listes `hidden_widgets` par persona (ex: usager cache `otp_heatmap`, `correlation_matrix`, etc.)
- **Aucune page n'appelle `is_widget_visible()`** — Pro_1 a un commentaire "câblage préparé" (ligne 31-32) mais le code n'est pas implémenté

### Proposition : activer + étendre

**Phase 1** — Activer le gate existant dans les pages qui ont des widgets cross-persona :

```python
pm = PersonaManager()
if pm.is_widget_visible("multimodal_heatmap"):
    render_multimodal_heatmap()
```

**Phase 2** — Étendre `personas.yaml` avec les nouveaux widgets Sprint 15+ :

```yaml
# Usager : ajouter les widgets Sprint 15+ visibles
usager:
  hidden_widgets:
    # ... existants ...
    # NE PAS ajouter mode_comparison ni mode_summary (visibles pour usager)

# Pro TCL : masquer les widgets purement usager
pro_tcl:
  hidden_widgets:
    # ... existants ...
    - mode_comparison
    - mode_summary

# Élu : permettre certains widgets Pro en lecture seule
elu:
  hidden_widgets:
    # ... existants ...
    - bus_traffic_spatial  # trop technique pour l'élu
    - coherence_scatter    # TomTom = opérationnel, pas décisionnel
```

**Phase 3** — Ajouter un niveau `deferred_widgets` pour le button-gating :

```yaml
pro_tcl:
  deferred_widgets:
    - multimodal_heatmap
    - coherence_scatter
    - bus_traffic_spatial
```

Le code page lirait : si widget dans `deferred_widgets`, afficher un bouton "Charger" au lieu du rendu direct.

---

## 7. Pattern de chargement différé (button-gate)

### Widgets candidats au chargement différé

| Widget | Page | Renderer | Coût estimé | Auto-refresh |
|--------|------|----------|-------------|-------------|
| `multimodal_heatmap` | Pro_3 | Folium HTML | 🔴 Élevé (MV + Folium render + 15 rectangles) | 30s |
| `coherence_scatter` | Pro_3 | 3× Plotly | 🔴 Élevé (2 requêtes PostGIS + 3 charts) | 30s |
| `bus_traffic_spatial` | Pro_3 | Plotly scatter | 🟠 Moyen (1 MV + scatter + top 20) | 30s |
| `traffic_map` (Pro_1) | Pro_1 | pydeck WebGL | 🟠 Moyen (requête gold + WebGL) | 30s |
| `network_map` | Pro_1 | pydeck WebGL | 🟠 Moyen (requête gold + WebGL) | 30s |
| `lieux_velov_map` | Usager_1 | Folium HTML | 🟡 Modéré (référentiel + markers) | 60s |
| `velov_trip` | Usager_1 | Folium + calcul | 🟠 Moyen (scoring stations + route + Folium) | 60s |
| `network_health_gauge` | Elu_1 | 5× Plotly gauge | 🟠 Moyen (5 health checks) | 300s |

### Implémentation recommandée

Créer un helper `dashboard/components/deferred_widget.py` :

```python
def deferred_render(
    widget_key: str,
    label: str,
    render_fn: Callable,
    *args, **kwargs,
) -> None:
    """Affiche un bouton. Au clic, persiste dans session_state et rend le widget."""
    state_key = f"show_{widget_key}"
    if st.button(f"📊 {label}", key=f"btn_{widget_key}"):
        st.session_state[state_key] = True
    if st.session_state.get(state_key):
        render_fn(*args, **kwargs)
        if st.button("Masquer", key=f"hide_{widget_key}"):
            st.session_state[state_key] = False
            st.rerun()
```

Utilisation :

```python
deferred_render(
    "multimodal_heatmap",
    "Charger la vue multimodale grille 0.01°",
    render_multimodal_heatmap,
)
```

---

## 8. Inventaire coût de rendu par widget

### Légende coût

- 🟢 **Léger** (<100ms) : texte, KPI cards, labels
- 🟡 **Modéré** (100-500ms) : Plotly simple, tables < 100 rows
- 🟠 **Lourd** (500ms-2s) : pydeck map, Plotly multi-chart, calculs Dijkstra
- 🔴 **Très lourd** (>2s) : Folium HTML render, requêtes PostGIS lourdes, multi-chart + KPI

| Widget | Renderer | Coût | Cache TTL | Note |
|--------|----------|------|-----------|------|
| search_bar | st.selectbox | 🟢 | — | — |
| weather_widget | st.markdown HTML | 🟢 | 300s | — |
| traffic_widget | st.markdown HTML | 🟢 | 30s | — |
| velov_widget | st.markdown HTML | 🟢 | 30s | — |
| alert_card | st.markdown HTML | 🟢 | — | — |
| alert_ticker | st.markdown HTML | 🟢 | 30s | — |
| mode_summary | st.markdown HTML | 🟢 | 600s | Sprint 15+ — **non câblé** |
| mode_comparison | st.markdown HTML | 🟡 | 600s | Sprint 15+ — **non câblé** |
| line_kpis | st.dataframe | 🟡 | 30s | 155 lignes si non limité |
| correlation_matrix | Plotly heatmap | 🟡 | 60s | — |
| segment_table | st.dataframe | 🟡 | 60s | — |
| cause_analysis | st.markdown HTML | 🟢 | — | — |
| otp_heatmap_mini | Plotly heatmap | 🟡 | 30s | 280px compressé |
| otp_heatmap (plein) | Plotly heatmap | 🟡 | 30s | — |
| delta_kpis | st.markdown HTML | 🟢 | — | Labels 0.7rem |
| executive_summary | st.markdown HTML | 🟢 | 300s | — |
| trend_chart | Plotly line | 🟡 | 300s | — |
| bottleneck_ranking | st.markdown HTML | 🟡 | 300s | 7 colonnes |
| bottleneck_map | Folium HTML | 🔴 | 300s | — |
| network_health_gauge | 5× Plotly gauge | 🟠 | 300s | Sprint 15+ — 5 health checks |
| bus_traffic_spatial | Plotly scatter | 🟠 | 60s | Sprint 15+ |
| coherence_scatter | 3× Plotly | 🔴 | 30s | Sprint 13+ — 2 requêtes PostGIS |
| multimodal_heatmap | Folium HTML | 🔴 | 30s | Sprint 15+ — MV + rectangles |
| network_map | pydeck WebGL | 🟠 | 30s | Double rendu avec traffic_map |
| traffic_map | pydeck WebGL | 🟠 | 30s | Double rendu avec network_map |
| traffic_map_compact | pydeck WebGL | 🟠 | 30s | — |
| velov_map_compact | pydeck WebGL | 🟠 | 30s | — |
| lieux_velov_map | Folium HTML | 🟠 | 600s | — |
| velov_trip | Folium + scoring | 🟠 | ❌ non caché | Recalcul à chaque rerun |
| itinerary_result | Folium + Dijkstra | 🔴 | ❌ non caché | Derrière bouton ✅ |
| transit_trip | st.markdown HTML | 🟡 | — | — |

---

## 9. Priorité d'implémentation

### P0 — Critique (impact immédiat sur utilisabilité)

| # | Action | Fichier(s) | Effort |
|---|--------|-----------|--------|
| 1 | **Button-gate les 3 widgets lourds de Pro_3** | `Pro_3_Correlation.py` | 30 min |
| 2 | **Remplacer `st.tabs` par `st.radio` sur Pro_1** (supprime le double rendu pydeck) | `Pro_1_PCC_Live.py` | 15 min |
| 3 | **Câbler `mode_comparison` + `mode_summary` dans Usager_1** | `Usager_1_Mon_Trajet.py` | 30 min |

### P1 — Important (lisibilité + performance)

| # | Action | Fichier(s) | Effort |
|---|--------|-----------|--------|
| 4 | Créer classes CSS `lyf-sublabel/label/value` dans `theme.py` | `theme.py` | 15 min |
| 5 | Migrer les 23+ widgets de `style="font-size:0.7Xrem"` vers classes CSS | 23 fichiers widgets | 1h |
| 6 | Button-gate `velov_trip` dans Usager_1 | `Usager_1_Mon_Trajet.py` | 15 min |
| 7 | Limiter `line_kpis` à top 20 par défaut | `Pro_1_PCC_Live.py` | 5 min |
| 8 | Augmenter OTP heatmap mini à 350px | `Pro_1_PCC_Live.py` | 2 min |

### P2 — Amélioration (qualité de vie)

| # | Action | Fichier(s) | Effort |
|---|--------|-----------|--------|
| 9 | Activer `is_widget_visible()` dans toutes les pages | 18 fichiers pages | 45 min |
| 10 | Étendre `personas.yaml` avec les widgets Sprint 15+ | `config/personas.yaml` | 10 min |
| 11 | Cacher `network_health_gauge` via la fn SQL existante | `network_health_gauge.py` | 15 min |
| 12 | Fusionner les 2 cartes Vélov de Usager_1 en une seule | `Usager_1_Mon_Trajet.py` | 30 min |
| 13 | Passer `delta_kpis` labels de 0.7rem à 0.85rem | `delta_kpis.py` | 2 min |
| 14 | Passer `bottleneck_ranking` détails à 0.85rem | `bottleneck_ranking.py` | 2 min |
| 15 | Créer helper `deferred_render()` centralisé | `dashboard/components/deferred_widget.py` | 20 min |

### Effort total estimé

| Priorité | Nombre d'actions | Effort |
|----------|-----------------|--------|
| P0 (critique) | 3 | ~1h15 |
| P1 (important) | 5 | ~1h30 |
| P2 (amélioration) | 7 | ~2h |
| **Total** | **15** | **~5h** |

---

> **Avertissement** : cet audit est basé sur l'analyse statique du code source. Les temps de rendu sont estimés, pas mesurés. Pour confirmer les sévérités, un test de rendu live sur le VPS avec Chrome DevTools (onglet Performance) donnerait des métriques précises par widget.
