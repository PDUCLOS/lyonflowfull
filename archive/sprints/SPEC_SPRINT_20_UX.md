# SPEC Sprint 20 — Amélioration UX Dashboard

> **Date** : 2026-06-22
> **Version cible** : v0.11.0
> **Branche** : `vps`
> **Prérequis** : Sprint 19 clos (v0.10.1), Sprints 16-18 déployés VPS
> **Effort estimé** : ~4-5 jours (6 axes)
> **Auteur** : Patrice DUCLOS / Claude Opus 4.6

---

## Table des matières

1. [Diagnostic UX actuel](#1-diagnostic-ux-actuel)
2. [Axe A — Loading states systématiques](#2-axe-a--loading-states-systematiques)
3. [Axe B — Thème Plotly unifié](#3-axe-b--theme-plotly-unifie)
4. [Axe C — Pages lourdes : lazy loading + pagination](#4-axe-c--pages-lourdes--lazy-loading--pagination)
5. [Axe D — Erreurs user-friendly](#5-axe-d--erreurs-user-friendly)
6. [Axe E — Accessibilité (RGAA / WCAG 2.1 AA)](#6-axe-e--accessibilite)
7. [Axe F — Navigation & onboarding](#7-axe-f--navigation--onboarding)
8. [Fichiers à créer / modifier](#8-fichiers)
9. [Tests](#9-tests)
10. [Priorités et plan d'implémentation](#10-priorites)

---

## 1. Diagnostic UX actuel

### 1.1. Ce qui marche

| Composant | État | Qualité |
|-----------|------|---------|
| Auto-refresh par persona | ✅ 18/18 pages | Pro 30s, Usager 60s, Élu 300s |
| Thème CSS par persona | ✅ `theme.py` | Couleurs, fonts Inter, animations fadeInUp |
| Deferred render (button-gate) | ✅ 10 widgets lourds | Persiste dans session_state |
| Navigation sidebar custom | ✅ Groupes, page active | Badge persona + bouton Accueil |
| Cache TTL 4 niveaux | ✅ data_cache.py | REALTIME 30s, FAST 60s, SLOW 300s, STATIC 600s |
| Loading state helpers | ✅ `loading_state.py` | loading_wrapper, empty_state, skeleton |
| Dark mode | ✅ CSS variables | bg-card, text-primary, etc. |

### 1.2. Ce qui pose problème

| Problème | Impact | Gravité |
|----------|--------|---------|
| **Loading states non adoptés** | 2/60 widgets utilisent `loading_wrapper`. Les 58 autres = écran blanc pendant le fetch DB | 🔴 Haute |
| **Thème Plotly incohérent** | 4 widgets = `plotly_dark`, 3 widgets = aucun template, 4 = mix transparent | 🟠 Moyenne |
| **Pages surchargées** | Pro_3 = 33 renders, Usager_1 = 30, Elu_1 = 26. Temps de chargement initial = 3-8s | 🔴 Haute |
| **Erreurs techniques exposées** | `st.error(f"⚠️ {e}")` affiche le traceback Python brut à l'usager. 45 `st.error` dans les widgets | 🟠 Moyenne |
| **Zéro accessibilité** | Pas d'attributs ARIA sur les charts Plotly/Folium, pas de texte alternatif, pas de navigation clavier, contraste non vérifié | 🟠 Moyenne |
| **Pas de feedback de fraîcheur** | L'usager ne sait pas si les données datent de 30s ou 30 min. Pas de badge "dernière MAJ" | 🟡 Basse |
| **Onboarding inexistant** | Première visite = mur de widgets. Pas de guided tour, pas de tooltip d'aide | 🟡 Basse |

### 1.3. Métriques cibles

| Métrique | Avant (estimé) | Cible v0.11.0 |
|----------|---------------|---------------|
| Widgets avec loading state | 2/60 (3%) | **60/60 (100%)** |
| Plotly template cohérent | 4/11 (36%) | **11/11 (100%)** |
| Pages avec lazy sections | 2/18 (Pro_3, Pro_7) | **6/18** (les 4 plus lourdes + 2 Élu) |
| `st.error` avec traceback brut | ~45 | **0** (tous via `data_error_to_message()`) |
| ARIA labels sur charts | 0 | **11 charts Plotly + 7 cartes Folium** |
| Badge fraîcheur données | 0/18 pages | **18/18** |

---

## 2. Axe A — Loading states systématiques

### 2.1. Problème

60 widgets, 2 utilisent `loading_wrapper()` (`model_monitoring.py`, `itinerary.py`). Les 58 autres = écran blanc ou contenu qui pop brutalement. Pire : pendant un auto-refresh Pro TCL (30s), les widgets lourds disparaissent puis réapparaissent = clignotement.

### 2.2. Solution

Wrapper systématique de tous les appels `cached_*()` dans les widgets.

**Pattern standard** (à appliquer dans les 58 widgets restants) :

```python
from dashboard.components.loading_state import loading_wrapper, empty_state

def render_my_widget():
    with loading_wrapper("Chargement données trafic…"):
        data = cached_traffic_predictions()

    if not data or (hasattr(data, 'empty') and data.empty):
        empty_state("📊", "Aucune donnée", "Le pipeline n'a pas encore produit de données.")
        return

    # ... rendu normal ...
```

**Anti-clignotement** : le `show_spinner=False` dans `data_cache.py` est correct (le spinner est géré par `loading_wrapper`, pas par Streamlit). Mais il faut s'assurer que le widget ne se re-rend pas si les données n'ont pas changé. Solution : `st.cache_data` + comparaison hash.

### 2.3. Priorisation (par persona)

| Persona | Widgets à migrer | Priorité |
|---------|-----------------|----------|
| Usager | 12 widgets (search_bar, weather, velov_trip, transit_trip, itinerary, alerts, mode_comparison, mode_summary, lieux_velov_map, traffic_map_compact, eco_calculator, bus_traffic_spatial) | 🔴 P1 (UX usager final) |
| Pro TCL | 24 widgets (line_kpis, otp_heatmap, bottlenecks, coherence_scatter, correlation_matrix, backtest_dashboard, source_health_monitor, pipeline_management, frequency_slider, ...) | 🟠 P2 |
| Élu | 18 widgets (network_health_gauge, drift_status_badge, data_quality_badge, trend_chart, before_after_chart, pdf_generator, ...) | 🟡 P3 |

### 2.4. Effort

~2h (patterns identiques × 58 widgets = mécanique). Script de migration automatisable.

---

## 3. Axe B — Thème Plotly unifié

### 3.1. Problème

| Situation | Widgets | Rendu |
|-----------|---------|-------|
| `template="plotly_dark"` | 4 (trend_chart, model_monitoring×2, otp_heatmap, before_after_chart) | Fond noir, texte blanc |
| Aucun template | 3 (network_health_gauge, source_health_monitor, bus_traffic_spatial) | Fond blanc par défaut (clash avec dark mode) |
| `paper_bgcolor="rgba(0,0,0,0)"` | 1 (network_health_gauge) | Transparent, OK |
| Couleurs hardcodées | ~8 widgets | Pas de cohérence inter-widgets |

### 3.2. Solution : template Plotly LyonFlow

Fichier : `dashboard/components/plotly_theme.py`

```python
"""Thème Plotly unifié — cohérent avec le theme.py CSS du dashboard.

Usage dans chaque widget Plotly :
    from dashboard.components.plotly_theme import LYF_TEMPLATE
    fig.update_layout(template=LYF_TEMPLATE)
"""

import plotly.graph_objects as go
from plotly.graph_objects import layout as go_layout

from dashboard.components.colors import COLORS

LYF_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, sans-serif",
            color=COLORS["text_primary"],
            size=13,
        ),
        title=dict(
            font=dict(size=16, color=COLORS["text_primary"]),
            x=0.0,
            xanchor="left",
        ),
        colorway=[
            COLORS.get("chart_1", "#4FC3F7"),
            COLORS.get("chart_2", "#FF8A65"),
            COLORS.get("chart_3", "#81C784"),
            COLORS.get("chart_4", "#CE93D8"),
            COLORS.get("chart_5", "#FFD54F"),
            COLORS.get("chart_6", "#4DD0E1"),
        ],
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.1)",
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.1)",
        ),
        hoverlabel=dict(
            bgcolor=COLORS["bg_card"],
            font_color=COLORS["text_primary"],
            bordercolor=COLORS["border_card"],
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=COLORS["text_secondary"]),
        ),
        margin=dict(l=40, r=20, t=40, b=40),
    ),
)


def apply_lyf_theme(fig: go.Figure) -> go.Figure:
    """Applique le thème LyonFlow à un Figure existant."""
    fig.update_layout(template=LYF_TEMPLATE)
    return fig
```

### 3.3. Migration

Remplacer dans chaque widget :
- `template="plotly_dark"` → `template=LYF_TEMPLATE`
- Supprimer `paper_bgcolor`/`plot_bgcolor` individuels (gérés par le template)
- Widgets sans template → ajouter `template=LYF_TEMPLATE`

### 3.4. Effort

~1h (11 widgets Plotly à migrer, find-replace + vérif visuelle).

---

## 4. Axe C — Pages lourdes : lazy loading + pagination

### 4.1. Problème

| Page | Renders | Temps estimé | Bottleneck |
|------|---------|-------------|------------|
| Pro_3_Correlation | 33 | 5-8s | 10 `deferred_render` + 5 MVs SQL |
| Usager_1_Mon_Trajet | 30 | 3-5s | Folium maps + géocodage + 3 calculs itinéraire |
| Elu_1_Synthese | 26 | 4-6s | network_health_gauge + 3 badges + trend_chart |
| Pro_7_Model_Monitoring | 13 | 3-5s | backtest_dashboard Plotly lourd |

### 4.2. Solution : sections collapsibles + scroll-to-load

**Pattern : `st.expander` par section avec lazy fetch**

Pro_3_Correlation.py (page la plus lourde) :

```python
# Au lieu de 33 renders séquentiels :
with st.expander("📊 Matrice corrélation bus × trafic", expanded=True):
    render_correlation_matrix()

with st.expander("🗺️ Vue multimodale grille 0.01°", expanded=False):
    deferred_render("multimodal_heatmap", "Charger la carte", render_multimodal_heatmap)

with st.expander("🚌 Corrélation spatiale bus × trafic", expanded=False):
    deferred_render("bus_spatial", "Charger", render_bus_traffic_spatial)

# etc.
```

**Problème connu** : `st.expander` ne diffère PAS le calcul (le code Python s'exécute quand même). Le vrai lazy c'est `deferred_render()`. La combo `expander` + `deferred_render` = UX propre (sections repliables) + perf (pas de calcul tant que l'utilisateur n'a pas cliqué).

**Pour les pages Élu** : les badges sont légers (1 requête scalaire chacun), le bottleneck est `trend_chart` + `network_health_gauge`. Mettre `trend_chart` derrière un `deferred_render()`.

### 4.3. Tabs → Sections dans Pro_3

Pro_3 a actuellement un flux linéaire de 33 widgets. Restructurer en tabs Streamlit :

```python
tab1, tab2, tab3, tab4 = st.tabs([
    "Bus × Trafic",
    "Multimodal",
    "Report modal",
    "Météo impact",
])
with tab1:
    render_correlation_matrix()
    deferred_render("bottlenecks", "Charger les bottlenecks", render_bottlenecks)

with tab2:
    deferred_render("multimodal", "Charger la grille", render_multimodal_heatmap)
    deferred_render("bus_spatial", "Charger le spatial", render_bus_traffic_spatial)

with tab3:
    deferred_render("modal_shift", "Charger le report modal", render_modal_shift_alert)

with tab4:
    deferred_render("meteo", "Charger l'impact météo", render_meteo_impact)
```

> **⚠️ Rappel** : `st.tabs` ne diffère PAS le calcul Python. Les 4 tabs sont exécutés au chargement. Le `deferred_render` à l'intérieur est ce qui diffère réellement. L'avantage des tabs = UX de navigation (l'usager voit 4 onglets au lieu de scroller 33 widgets).

### 4.4. Effort

~1 jour (restructurer 4 pages + tester visuellement).

---

## 5. Axe D — Erreurs user-friendly

### 5.1. Problème

45 `st.error()` dans les widgets, dont ~30 affichent le message technique de l'exception :

```python
# Pattern actuel (mauvais UX) :
except DashboardDataError as e:
    st.error(f"⚠️ {e}")
    # → "⚠️ [gold.trafic_predictions] Données pipeline indisponibles —
    #    PostgreSQL ne répond pas. Vérifier POSTGRES_HOST/PORT/PASSWORD
    #    et docker compose up postgres"
```

L'usager (Élu ou Usager lambda) ne sait pas ce qu'est PostgreSQL.

### 5.2. Solution : messages par persona

```python
# dashboard/components/error_display.py

from src.persona.manager import get_current_persona

_MESSAGES = {
    "usager": {
        "db_down": "Les données sont temporairement indisponibles. Réessayez dans quelques minutes.",
        "no_data": "Pas encore de données pour cette période.",
        "geocoding_fail": "Adresse non reconnue. Essayez un lieu connu (Part-Dieu, Bellecour…).",
    },
    "pro_tcl": {
        "db_down": "Pipeline indisponible — vérifier le statut dans Pipeline Management (Pro_6).",
        "no_data": "Aucune donnée pour ce filtre. Vérifier la fenêtre temporelle.",
        "geocoding_fail": "Géocodage échoué. Adresse hors périmètre Lyon Métropole ?",
    },
    "elu": {
        "db_down": "Source de données temporairement inaccessible.",
        "no_data": "Données non disponibles pour la période sélectionnée.",
        "geocoding_fail": "Lieu non trouvé.",
    },
}


def show_error(error_type: str, detail: str = "") -> None:
    """Affiche un message d'erreur adapté au persona courant.

    Args:
        error_type: clé dans _MESSAGES (db_down, no_data, geocoding_fail).
        detail: info technique (affiché seulement pour pro_tcl).
    """
    persona = get_current_persona() or "usager"
    msg = _MESSAGES.get(persona, _MESSAGES["usager"]).get(error_type, str(detail))

    st.error(msg)
    if persona == "pro_tcl" and detail:
        with st.expander("🔧 Détail technique"):
            st.code(detail)
```

### 5.3. Migration

Remplacer les `st.error(f"⚠️ {e}")` par :
```python
from dashboard.components.error_display import show_error

except DashboardDataError as e:
    show_error("db_down", str(e))
```

### 5.4. Effort

~2h (patterns identiques × 45 occurrences).

---

## 6. Axe E — Accessibilité (RGAA / WCAG 2.1 AA)

### 6.1. Contexte

Le dashboard est une **vitrine pour le portfolio RNCP 38777**. L'accessibilité est un différenciant :
- **RGAA** : référentiel français (obligatoire service public, bonne pratique tous)
- **WCAG 2.1 niveau AA** : standard international

### 6.2. Problèmes identifiés

| Critère WCAG | Problème | Widgets impactés |
|-------------|----------|-----------------|
| **1.1.1 Non-text content** | Charts Plotly/Folium sans texte alternatif | 11 Plotly + 7 Folium = 18 |
| **1.4.3 Contrast** | Texte `--text-muted` (#999) sur fond `--bg-card` (#1E1E2E) = ratio ~4.0:1 (seuil AA = 4.5:1) | Toutes les légendes, labels secondaires |
| **2.1.1 Keyboard** | Charts Plotly non navigables au clavier. Folium maps idem | 18 charts |
| **2.4.1 Bypass blocks** | Pas de liens d'évitement ("Aller au contenu principal") | Toutes les pages |
| **3.1.1 Language** | `<html lang="">` pas défini (Streamlit default = en) | Config globale |
| **4.1.2 Name/Role/Value** | Metrics Streamlit n'ont pas de `role="status"` ou `aria-live` | ~30 KPI cards |

### 6.3. Solutions praticables (dans Streamlit)

Streamlit a des **limites structurelles** en accessibilité (pas de contrôle fin du HTML). Voici ce qui est faisable :

#### E.1. Texte alternatif pour les charts

```python
# Wrapper pour Plotly
def plotly_with_alt(fig, alt_text: str, **kwargs):
    """Affiche un chart Plotly avec un texte alternatif sr-only."""
    st.plotly_chart(fig, **kwargs)
    st.markdown(
        f'<p class="sr-only">{alt_text}</p>',
        unsafe_allow_html=True,
    )

# Usage :
plotly_with_alt(
    fig,
    alt_text="Graphique : MAE XGBoost vs TomTom sur 7 jours. "
             "MAE moyen 7.2 km/h, tendance stable.",
    use_container_width=True,
)
```

CSS nécessaire (dans `theme.py`) :
```css
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}
```

#### E.2. Contraste minimum

Ajuster `--text-muted` de `#999999` à `#B0B0B0` (+ratio 5.2:1 sur `#1E1E2E`).
Ajuster `--text-secondary` si nécessaire.

Vérification : `https://webaim.org/resources/contrastchecker/`

#### E.3. Lien d'évitement

```python
# Dans theme.py, injecter en haut du CSS :
<a href="#main-content" class="sr-only sr-only-focusable">
    Aller au contenu principal
</a>
```

```css
.sr-only-focusable:focus {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip: auto;
    white-space: normal;
    padding: 0.5rem 1rem;
    background: var(--primary);
    color: white;
    z-index: 99999;
}
```

#### E.4. Langue du document

```python
# Dans theme.py :
st.markdown('<script>document.documentElement.lang="fr";</script>',
            unsafe_allow_html=True)
```

#### E.5. Tableau de données accessible pour chaque chart

Pour les personas Élu et Usager, ajouter un `st.expander("📋 Données du graphique")` sous chaque chart Plotly avec un `st.dataframe()` des données sources.

```python
with st.expander("📋 Données du graphique"):
    st.dataframe(df[["hour", "mae_kmh", "n_pairs"]], use_container_width=True)
```

Bénéfice double : accessibilité (lecteurs d'écran lisent les tables) + transparence (l'usager vérifie les chiffres).

### 6.4. Effort

~1.5 jours (CSS contraste + sr-only + wrappers charts + 18 alt texts + tableaux données).

---

## 7. Axe F — Navigation & onboarding

### 7.1. Badge fraîcheur données

Chaque page affiche un badge en haut indiquant la fraîcheur des données :

```python
# dashboard/components/freshness_badge.py

def render_freshness_badge() -> None:
    """Badge indiquant l'âge des données affichées."""
    persona = get_current_persona()
    config = get_persona_config(persona)
    refresh_sec = config.get("refresh_interval_sec", 60)

    # Prochaine MAJ
    next_refresh = refresh_sec - (time.time() % refresh_sec)

    st.markdown(
        f"""
        <div class="lyf-freshness-badge">
            🔄 Prochaine MAJ dans <strong>{int(next_refresh)}s</strong>
            · Intervalle : {refresh_sec}s
        </div>
        """,
        unsafe_allow_html=True,
    )
```

CSS dans `theme.py` :
```css
.lyf-freshness-badge {
    font-size: 0.75rem;
    color: var(--text-muted);
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    display: inline-block;
    margin-bottom: 0.5rem;
}
```

### 7.2. Tooltip d'aide contextuelle

Pour les widgets complexes (Granger causality, z-score, PSI), ajouter un `st.info()` ou un `st.popover()` (Streamlit 1.32+) avec une explication en 2 lignes :

```python
with st.popover("ℹ️ Qu'est-ce que le z-score ?"):
    st.markdown(
        "Le **z-score** mesure combien la valeur actuelle s'éloigne de la moyenne. "
        "Un z-score < -2 signifie que la station a significativement moins de vélos "
        "que d'habitude à cette heure."
    )
```

Widgets cibles (les plus techniques) :
- `propagation_map.py` : Granger causality → explication lag cross-corrélation
- `modal_shift_alert.py` : z-score → explication écart-type
- `drift_status_badge.py` : PSI → explication drift
- `backtest_dashboard.py` : MAE/MAPE → explication métriques ML
- `coherence_scatter.py` : TomTom vs GL → explication cross-validation

### 7.3. Effort

~0.5 jour (badge fraîcheur = 1 composant × 18 pages, tooltips = 5 widgets).

---

## 8. Fichiers à créer / modifier

### Fichiers à CRÉER

| Fichier | Axe | Description |
|---------|-----|-------------|
| `dashboard/components/plotly_theme.py` | B | Template Plotly unifié LYF_TEMPLATE |
| `dashboard/components/error_display.py` | D | Messages d'erreur par persona |
| `dashboard/components/a11y.py` | E | Helpers accessibilité (plotly_with_alt, sr-only) |
| `dashboard/components/freshness_badge.py` | F | Badge fraîcheur données |

### Fichiers à MODIFIER (par volume)

| Fichier | Axes | Modifications |
|---------|------|--------------|
| **58 widgets** (`widgets/*/*.py`) | A | Ajouter `loading_wrapper` + `empty_state` |
| **11 widgets Plotly** | B | Remplacer template → `LYF_TEMPLATE` |
| **45 `st.error`** dans widgets | D | Remplacer par `show_error()` |
| **18 charts** (Plotly + Folium) | E | Ajouter texte alternatif sr-only |
| `dashboard/components/theme.py` | E | CSS sr-only + contraste + skip link + `lang="fr"` |
| `dashboard/components/colors.py` | E | Ajuster `text_muted` contraste AA |
| `Pro_3_Correlation.py` | C | Restructurer en tabs (4 onglets) |
| `Elu_1_Synthese.py` | C | Sections collapsibles |
| `Usager_1_Mon_Trajet.py` | C | Sections collapsibles |
| **18 pages** | F | Ajouter `render_freshness_badge()` |
| **5 widgets techniques** | F | Ajouter tooltips aide |

---

## 9. Tests

### Tests unitaires

| Fichier test | Axe | Tests | Description |
|-------------|-----|-------|-------------|
| `tests/dashboard/test_plotly_theme.py` | B | 5 | Template existe, colorway, font, backgrounds |
| `tests/dashboard/test_error_display.py` | D | 9 | 3 personas × 3 types d'erreur |
| `tests/dashboard/test_a11y.py` | E | 6 | sr-only CSS, alt text, lang, skip link |
| `tests/dashboard/test_freshness_badge.py` | F | 3 | Badge rendu, intervalle correct, persona |

### Tests visuels (manuels, checklist)

| Check | Page | Critère |
|-------|------|---------|
| Loading state visible au premier chargement | Usager_1 | Spinner affiché 0.5-2s |
| Empty state si DB down | Usager_1 | Message user-friendly, pas de traceback |
| Plotly charts cohérents (même fond, même police) | Pro_3 | Pas de chart blanc sur fond noir |
| Tabs Pro_3 fonctionnels | Pro_3 | 4 onglets, deferred_render dans chacun |
| Contraste texte lisible | Toutes | Texte muted lisible sans plisser les yeux |
| Badge fraîcheur visible | Toutes | En haut de page, met à jour au refresh |
| Tooltip z-score compréhensible | Pro_3 | Clic popover, 2 phrases claires |

**Total tests automatisés : ~23**

---

## 10. Priorités et plan d'implémentation

### Matrice effort × impact

```
Impact élevé
  │
  │  ★ Axe A (loading)    ★ Axe C (lazy pages)
  │       [2h]                  [1j]
  │
  │  ★ Axe D (erreurs)    ★ Axe B (Plotly)
  │       [2h]                  [1h]
  │
  │                        ★ Axe E (a11y)
  │                             [1.5j]
  │
  │                        ★ Axe F (nav)
  │                             [0.5j]
  │
  └──────────────────────────────── Effort
      faible                     élevé
```

### Ordre recommandé

```
Jour 1 (quick wins, impact max) :
  1. Axe B — plotly_theme.py + migration 11 widgets (1h)
  2. Axe D — error_display.py + migration 45 st.error (2h)
  3. Axe A — loading_wrapper dans 58 widgets (2h)
  → Commit feat(ux): loading states + Plotly theme + error display

Jour 2 (restructuration pages) :
  4. Axe C — Pro_3 tabs + Elu_1/Usager_1 sections collapsibles (1j)
  → Commit feat(ux): lazy loading + page restructuration

Jour 3 (accessibilité) :
  5. Axe E — CSS contraste + sr-only + alt texts + tableaux données (1.5j)

Jour 4 (finitions) :
  6. Axe E fin + Axe F badges + tooltips (1j)
  7. Tests automatisés (23 tests)
  → Commit feat(ux): accessibility + freshness badges + help tooltips
  → Commit test(ux): 23 tests UX

Jour 5 (vérif visuelle + polish) :
  8. Test visuel complet (18 pages × 3 personas = 54 combinaisons)
  9. Fix ajustements post-review
  → Tag v0.11.0
```

### Résultat attendu v0.11.0

| Métrique | Avant | Après |
|----------|-------|-------|
| Widgets | 60 | 60 (pas de nouveau) |
| Fichiers nouveaux | — | 4 (plotly_theme, error_display, a11y, freshness_badge) |
| Tests | 507 | ~530 (+23) |
| Loading states | 2/60 | **60/60** |
| Plotly cohérent | 4/11 | **11/11** |
| Erreurs user-friendly | 0/45 | **45/45** |
| ARIA/alt text | 0 | **18 charts** |
| Contraste AA | Non | **Oui** |
| Badge fraîcheur | 0/18 | **18/18** |

---

## Annexe — Inventaire widgets Plotly

| Widget | Template actuel | Cible |
|--------|----------------|-------|
| `trend_chart.py` | `plotly_dark` | `LYF_TEMPLATE` |
| `model_monitoring.py` (2 charts) | `plotly_dark` | `LYF_TEMPLATE` |
| `otp_heatmap.py` | `plotly_dark` | `LYF_TEMPLATE` |
| `before_after_chart.py` | `plotly_dark` | `LYF_TEMPLATE` |
| `network_health_gauge.py` | aucun + `rgba(0,0,0,0)` | `LYF_TEMPLATE` |
| `source_health_monitor.py` | aucun | `LYF_TEMPLATE` |
| `bus_traffic_spatial.py` | aucun | `LYF_TEMPLATE` |
| `coherence_scatter.py` | partiel (hovertemplate) | `LYF_TEMPLATE` |
| `backtest_dashboard.py` | partiel | `LYF_TEMPLATE` |
| `meteo_impact.py` | partiel (hovertemplate) | `LYF_TEMPLATE` |
| `modal_shift_alert.py` | partiel (hovertemplate) | `LYF_TEMPLATE` |
| `propagation_map.py` | partiel | `LYF_TEMPLATE` |

## Annexe — Inventaire cartes Folium

| Widget | Alt text à ajouter |
|--------|-------------------|
| `traffic_map_compact.py` | "Carte trafic Lyon — couleurs par vitesse" |
| `itinerary.py` | "Itinéraire voiture — polyline sur rues OSM" |
| `velov_trip.py` | "Trajet Vélov — 3 segments (marche + vélo + marche)" |
| `lieux_velov_map.py` | "Carte stations Vélov proches" |
| `bottleneck_map.py` | "Carte bottlenecks infrastructure" |
| `multimodal_heatmap.py` | "Carte chaleur multimodale — score par cellule 1km" |
| `propagation_map.py` | "Carte propagation congestion — corrélations spatiales" |
