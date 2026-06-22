# TODO — LyonFlowFull

> **Date** : 2026-06-22 · **Branche** : `vps` (`a5ed131`) · **597 tests verts, ruff clean**

---

## P1 — Quick wins (2h, aucun risque, pas de test visuel requis)

### P1.1 Axe A finition : 10 widgets DB sans loading_wrapper

**Quoi** : 10 widgets font des requêtes DB (via `cached_*()`) mais n'affichent rien pendant le fetch = écran blanc 0.5-2s.

**Avant** (ex: `elu/drift_status_badge.py:117`) :
```python
def render_drift_status_badge():
    try:
        summary = cached_xgb_accuracy_summary(hours=24)
        drift = get_latest_drift_report()
    except DashboardDataError as e:
        st.error(f"⚠️ Drift status indisponible : {e}")
```

**Après** :
```python
from dashboard.components.loading_state import loading_wrapper

def render_drift_status_badge():
    with loading_wrapper("Chargement drift status…"):
        try:
            summary = cached_xgb_accuracy_summary(hours=24)
            drift = get_latest_drift_report()
        except DashboardDataError as e:
            show_error("db_down", str(e))
```

**Les 10 fichiers** (chemin complet, ligne du `try:` ou du `cached_*` call) :

| # | Fichier | Ligne | Appel DB |
|---|---------|-------|----------|
| 1 | `dashboard/components/widgets/usager/velov_trip.py` | 63 | `plan_velov_trip()` → PostGIS |
| 2 | `dashboard/components/widgets/usager/search_bar.py` | 40 | `cached_lyon_addresses_with_coords()` |
| 3 | `dashboard/components/widgets/elu/executive_summary.py` | ~35 | `cached_executive_summary()` |
| 4 | `dashboard/components/widgets/elu/pdf_generator.py` | ~28 | accès sections data |
| 5 | `dashboard/components/widgets/elu/kpi_cards.py` | ~30 | `cached_elu_kpis()` |
| 6 | `dashboard/components/widgets/elu/drift_status_badge.py` | 117 | `cached_xgb_accuracy_summary()` + `get_latest_drift_report()` |
| 7 | `dashboard/components/widgets/elu/data_quality_badge.py` | 63 | `cached_source_health()` |
| 8 | `dashboard/components/widgets/pro_tcl/correlation_matrix.py` | 62 | `cached_infra_bottlenecks()` |
| 9 | `dashboard/components/widgets/pro_tcl/source_health_monitor.py` | 107 | `cached_source_health()` + `cached_data_completeness()` |
| 10 | `dashboard/components/widgets/usager/mode_comparison.py` | — | reçoit data en param mais fait du calcul |

**Risque** : zéro. Wrap mécanique, pas de changement logique. Tests existants continuent de passer.

**Les 18 widgets légers restants** (`alert_card`, `format_selector`, etc.) n'ont pas de DB call = pas de loading_wrapper nécessaire. **On ne les touche pas.**

---

### P1.2 Axe D finition : 14 st.error bruts → show_error()

**Quoi** : 14 `st.error(f"⚠️ {e}")` affichent des traces Python techniques aux usagers/élus.

**Avant** (pattern identique partout) :
```python
except DashboardDataError as e:
    st.error(f"⚠️ Backtest indisponible : {e}")
```

**Après** :
```python
from dashboard.components.error_display import show_error

except DashboardDataError as e:
    show_error("db_down", str(e))
```

**Les 14 à migrer** (3 `pipeline_management` "Échec clear/mark" = OK tels quels = action feedback pas DB) :

| # | Fichier | Ligne | error_type |
|---|---------|-------|------------|
| 1 | `usager/itinerary.py` | 98 | `geocoding_fail` |
| 2 | `usager/itinerary.py` | 101 | `geocoding_fail` |
| 3 | `usager/velov_trip.py` | 75 | `geocoding_fail` |
| 4 | `elu/pdf_generator.py` | 32 | `generic` |
| 5 | `elu/drift_status_badge.py` | 120 | `db_down` |
| 6 | `elu/data_quality_badge.py` | 66 | `db_down` |
| 7 | `elu/network_health_gauge.py` | 194 | `db_down` |
| 8 | `elu/network_health_gauge.py` | 198 | `no_data` (migration 019 pas appliquée) |
| 9 | `elu/data_quality_detail.py` | 207 | `db_down` |
| 10 | `pro_tcl/model_monitoring.py` | 295 | `db_down` |
| 11 | `pro_tcl/source_health_monitor.py` | 110 | `db_down` |
| 12 | `pro_tcl/pipeline_management.py` | 92 | `db_down` |
| 13 | `pro_tcl/pipeline_management.py` | 235 | `db_down` |
| 14 | `pro_tcl/backtest_dashboard.py` | 220 | `db_down` |

**Cas spécial** : `network_health_gauge.py:198` est un `st.error` multi-ligne qui dit "migration 019 pas appliquée". C'est un message `no_data` (la MV est vide), pas un `db_down`. → `show_error("no_data")`.

**Cas spécial** : `velov_trip.py:75` affiche les coords brutes (`Origin={origin!r} → {origin_coords}`). → Remplacer par `show_error("geocoding_fail")` qui dira "Adresse non reconnue" à l'usager.

**Risque** : zéro. Import `show_error` déjà présent dans 5 de ces fichiers (ajouté Sprint 20). Les 9 autres = ajouter l'import.

---

## P2 — Moyen effort (1.5j, amélioration visible)

### P2.1 Axe C : Pro_3 en tabs (~0.5j)

**Quoi** : Pro_3_Correlation.py = 33 renders linéaires. Restructurer en tabs pour navigation.

**Structure actuelle** (ligne par ligne) :
```
L35  render_sidebar_navigation()
L37  render_freshness_badge()
L40  render_data_status_banner()
L47  render_line_selector()         ← Toujours visible (filtre global)
L53  render_correlation_matrix()    ← Section 1: Bus × Trafic
L60  render_segment_table()
L63  render_cause_analysis()
L96  deferred: bus_traffic_spatial   ← Section 2: Spatial
L109 deferred: coherence_scatter     ← Section 3: TomTom
L123 deferred: multimodal_heatmap    ← Section 4: Multimodal
L137 deferred: meteo_impact          ← Section 5: Météo
L151 deferred: modal_shift_alert     ← Section 6: Report modal
L169 deferred: propagation_map       ← Section 7: Propagation
```

**Structure cible** :
```python
render_line_selector()  # Toujours visible

tab1, tab2, tab3, tab4 = st.tabs([
    "Bus × Trafic",     # correlation_matrix + segment_table + cause_analysis
    "Spatial & TomTom",  # bus_traffic_spatial + coherence_scatter
    "Multimodal",        # multimodal_heatmap + meteo_impact + modal_shift_alert
    "Propagation",       # propagation_map
])
```

**Risque** : moyen. Chaque tab exécute son Python (Streamlit ne lazy-load pas les tabs). Les 6 `deferred_render` à l'intérieur des tabs assurent le vrai lazy. **Tester visuellement avant deploy** — les session_state keys des deferred_render doivent rester uniques.

**Dépendance** : aucune (indépendant de P1).

### P2.2 Elu_1 + Usager_1 sections collapsibles (~0.5j)

**Elu_1_Synthese.py** (26 renders) :
```
L47  render_network_health_gauge()    ← Toujours visible (bandeau)
L51  render_drift_status_badge()      ← Toujours visible (bandeau)
L55  render_data_quality_badge()      ← Toujours visible (bandeau)
L65  render_data_quality_detail()     ← expander "Détail qualité"
L70  render_executive_summary()       ← Toujours visible
L75  render_kpi_cards()               ← Toujours visible
L81  render_traffic_map_compact()     ← expander "Carte trafic"
L89  render_trend_chart()             ← expander "Tendance"
L91  render_top_decisions()
L96  render_news_section()            ← expander "Actualités"
L101 render_pdf_generator()           ← En bas (lourd)
```

Les 3 badges en bandeau + executive_summary + kpi_cards restent toujours visibles. Les widgets lourds (carte, trend, PDF) → `st.expander(expanded=False)`.

**Risque** : faible. `st.expander` exécute quand même le Python. Mais la carte Folium est dans un `st.components.v1.html()` qui skip le render visuel quand collapsed. Net gain RAM ~20%.

### P2.3 Axe F : 5 tooltips aide (~2h)

**Quoi** : `st.popover()` (Streamlit 1.32+) sur les 5 widgets techniques.

**Exemple** (à ajouter dans `propagation_map.py`, dans le render, juste avant le chart) :
```python
with st.popover("ℹ️ Qu'est-ce que la causalité de Granger ?"):
    st.markdown(
        "La **causalité de Granger** teste si les valeurs passées d'un capteur A "
        "aident à prédire les valeurs futures d'un capteur B. Un lien significatif "
        "(p < 0.05) signifie que la congestion se **propage** de A vers B avec un retard."
    )
```

| Widget | Concept | Texte (~2 phrases) |
|--------|---------|----|
| `propagation_map.py` | Granger causality | Causalité = congestion se propage de A→B avec retard |
| `modal_shift_alert.py` | z-score | z < -2 = significativement moins de vélos que d'habitude |
| `drift_status_badge.py` | PSI | PSI > 0.2 = la distribution des prédictions a changé |
| `backtest_dashboard.py` | MAE/MAPE | MAE = erreur moyenne en km/h, MAPE = en % |
| `coherence_scatter.py` | TomTom vs GL | Points proches de la diagonale = sources cohérentes |

**Risque** : zéro. `st.popover` est isolé, ne touche pas au reste du widget.

**Dépendance** : vérifier que Streamlit >= 1.32 est installé (`pip show streamlit`).

### P2.4 VPS : index pgRouting (~15min SSH)

**Quoi** : cold start routing = 10-21s. L'inner query de `pgr_dijkstra` scanne `osm.ways` (101k rows) en filtrant `WHERE cost > 0`.

**Requête dans `osm.route_car()`** (migration_026, L206) :
```sql
SELECT gid AS id, source, target, cost, reverse_cost FROM osm.ways WHERE cost > 0
```

**Index recommandé** :
```sql
CREATE INDEX IF NOT EXISTS idx_ways_source_target ON osm.ways (source, target)
    WHERE cost > 0;
```

> **Note** : `idx_ways_cost` seul n'aide pas — pgRouting scanne toutes les arêtes pour construire le graphe. Un index partiel `(source, target) WHERE cost > 0` aide pgRouting à filtrer. Mais le vrai bottleneck est le `pgr_dijkstra` lui-même (101k edges) — l'index aide peu vs le calcul Dijkstra. **Gain estimé : 10-20%, pas 5x.**

**Alternative** : cache applicatif Streamlit (TTL 30s) absorbe déjà le cold start pour les routes répétées. **Probablement suffisant sans index.**

**Décision** : si cold start > 15s en usage réel → ajouter l'index. Sinon skip.

---

## P3 — Gros effort (2j, valeur portfolio RNCP)

### P3.1 Axe E : Accessibilité RGAA/WCAG 2.1 AA (~1.5j)

**Pourquoi le faire** : différenciant fort pour le portfolio RNCP 38777. Peu de projets data montrent une démarche accessibilité. Jury impressionné. Coût = 1.5j. ROI narratif élevé.

**Pourquoi NE PAS le faire** : invisible pour l'utilisateur VPS (Pro TCL, pas malvoyant). Pas de compliance obligatoire (pas un service public). Effort réel peut dépasser 1.5j (18 alt texts = 18 descriptions à écrire).

**Si tu décides de le faire — les 8 tâches** :

| # | Tâche | Fichier(s) | Code | Effort |
|---|-------|-----------|------|--------|
| 1 | CSS `.sr-only` | `theme.py:~340` | Ajouter classe `position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0)` | 5min |
| 2 | Skip link | `theme.py:~35` | `<a href="#main-content" class="sr-only sr-only-focusable">Aller au contenu</a>` | 10min |
| 3 | `lang="fr"` | `theme.py` | `<script>document.documentElement.lang="fr"</script>` | 2min |
| 4 | Contraste muted | `colors.py` | `text_muted: "#999999"` → `"#B0B0B0"` (ratio 4.0 → 5.2) | 2min |
| 5 | Créer `a11y.py` | nouveau fichier | `plotly_with_alt(fig, alt_text)` wrapper | 15min |
| 6 | 11 charts Plotly alt texts | 11 fichiers | Ajouter `plotly_with_alt(fig, "description...")` | 1h |
| 7 | 7 cartes Folium alt texts | 7 fichiers | `st.markdown('<p class="sr-only">desc</p>')` après chaque carte | 45min |
| 8 | Tableaux données | ~8 charts | `st.expander("📋 Données")` + `st.dataframe(df)` sous chaque chart | 2h |

Tâches 1-4 = 20min, livrables immédiatement. Tâches 5-8 = 4h, besoin de rédiger 18 alt texts.

**Alt texts pré-rédigés** (pour accélérer si tu lances) :

| Chart | Alt text |
|-------|----------|
| `trend_chart` | "Graphique de tendance : évolution de la part modale TC sur 30 jours" |
| `otp_heatmap` | "Heatmap ponctualité : lignes TCL × tranches horaires, couleur = OTP %" |
| `before_after_chart` | "Comparaison avant/après : KPIs trafic pré et post aménagement" |
| `network_health_gauge` | "Jauge santé réseau : score global 0-100, vert > 70" |
| `coherence_scatter` | "Nuage de points : vitesse TomTom vs Grand Lyon, diagonale = cohérence" |
| `bus_traffic_spatial` | "Scatter spatial : corrélation retard bus × congestion par zone 100m" |
| `meteo_impact` | "Barres : delta vitesse/retard/vélos par condition météo vs beau temps" |
| `modal_shift_alert` | "Barres : nombre de stations Vélov en alarme par ligne TC" |
| `model_monitoring` (2) | "Courbe MAE XGBoost sur 24h" / "Distribution résidus prédictions" |
| `backtest_dashboard` | "Scatter : MAE XGBoost vs TomTom par paire capteur-tuile" |
| `propagation_map` (Folium) | "Carte propagation : flèches entre capteurs causalement liés (Granger)" |
| `traffic_map_compact` (Folium) | "Carte trafic Lyon : segments colorés par vitesse (vert > 50, rouge < 20)" |
| `itinerary` (Folium) | "Carte itinéraire voiture : polyline bleue sur réseau routier OSM" |
| `velov_trip` (Folium) | "Carte trajet Vélov : marche grise + vélo bleu + stations markers" |
| `lieux_velov_map` (Folium) | "Carte stations Vélov proches du lieu sélectionné" |
| `bottleneck_map` (Folium) | "Carte bottlenecks : rouge=infra, orange=trafic, bleu=pistes cyclables" |
| `multimodal_heatmap` (Folium) | "Carte chaleur multimodale : rectangles colorés par score 0-10 par km²" |

### P3.2 Tests Sprint 16 : vérifier couverture (~30min)

**Contexte** : `tests/monitoring/test_source_health.py` manque, mais `tests/persona/test_source_health.py` existe déjà. Probablement un doublon de chemin.

**Action** : lancer `pytest tests/persona/test_source_health.py tests/persona/test_dq_badge.py -v` et vérifier que les cas sont couverts. Si oui → pas besoin de créer les fichiers `tests/monitoring/`.

### P3.3 Backup offsite (~30min SSH)

**2 options** :

| Option | Config | Avantage |
|--------|--------|----------|
| A. rclone → Google Drive | `rclone config` sur VPS, ajouter `OFFSITE_HOST=gdrive:lyonflow-backups` | Gratuit 15 Go, déjà un compte Google |
| B. rsync → serveur SSH | `OFFSITE_HOST=user@backup-host:/backups/lyonflow` | Plus rapide, backup incrémental |

**Décision toi** : quel remote tu as ? Si Google Drive = option A. Si serveur SSH dispo = option B.

---

## P4 — Backlog (pas urgent, à faire quand l'envie vient)

### TODOs dans le code

| TODO | Fichier:ligne | Effort | Quand |
|------|--------------|--------|-------|
| JWT auth API | `src/api/main.py:580` | 2h | Avant d'exposer l'API publiquement |
| Quantile regression XGBoost | `src/models/xgboost_speed.py:328` | 1j | Sprint ML futur |
| Batcher Vélov smart lookup | `src/routing/pathfinder_multimodal.py:373` | 2h | Si perf Vélov problème (pas le cas) |
| Sparkline 24h gauge | `elu/network_health_gauge.py:252` | 0.5j | Besoin table historique d'abord |
| 3 templates HTML rapport | `elu/template_selector.py:13,17,21` | 1j | Quand l'Élu en a besoin |
| Modifier schéma bronze→silver | `src/transformation/bronze_to_silver.py:144` | 0.5j | Prochaine migration schéma |

### Infra

| Item | Contexte | Action |
|------|----------|--------|
| DNS `lyonflowfull.fr` | NXDOMAIN depuis Sprint VPS-1 | Renouveler chez registrar ou abandonner (accès par IP suffit pour RNCP) |
| Cert TLS Let's Encrypt | Expiré (lié au DNS mort) | Si DNS renouvelé → `certbot renew`. Sinon self-signed suffit |
| TomTom Niveau 3 | Routing API payante | **Skip** — pgRouting Sprint 18 couvre le besoin. Pas de ROI |
| Axe 2 propagation UI | Code livré Sprint 17, pas dans UI | Ajouter `propagation_map` à une page Élu si demandé |
| Axe 4 report modal UI | Code livré Sprint 17, pas dans UI | Ajouter `modal_shift_alert` à une page Élu si demandé |

---

## Arbre de décision rapide

```
Tu as 2h ?
  → P1.1 + P1.2 (loading_wrapper + st.error). Commit, push, fini.

Tu as 1 jour ?
  → P1 + P2.3 tooltips + P2.4 index (si cold start gênant)

Tu as 2-3 jours ?
  → P1 + P2 complet (tabs Pro_3 + sections Elu_1/Usager_1 + tooltips)

Tu veux impressionner le jury RNCP ?
  → P1 + P3.1 accessibilité (skip P2 tabs, moins visible que l'a11y)

Tu veux juste closer le sprint ?
  → P1 seul. Tag v0.11.0. Reste = Sprint 21.
```
