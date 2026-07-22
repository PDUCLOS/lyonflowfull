# LyonFlow — Widgets : calculs, affichage et fichiers de transformation

> Documentation exhaustive des **59 widgets** (`dashboard/components/widgets/{usager,pro_tcl,elu}/`) : ce qu'affiche chaque widget, le calcul réel qu'il fait (formules exactes citées depuis le code), et la chaîne de fichiers qui va du widget jusqu'à la table/vue PostgreSQL source.
>
> Chaîne type : `widget.py` → `cached_xxx()` (`dashboard/components/data_cache.py`, cache Streamlit TTL) → `load_xxx()` (`src/data/data_loader.py`) → `get_xxx()` (`src/data/db_query.py`, requête SQL) → table/vue `gold.*` / `silver.*` / `referentiel.*`.
>
> Certains widgets **court-circuitent ce cache** et appellent directement `db_query`/le moteur de routing (`src/routing/pathfinder*.py`) — signalé explicitement à chaque fois que constaté.
>
> Voir aussi : [`DASHBOARD_PAGES.md`](DASHBOARD_PAGES.md) (logique des 18 pages), [`POSTGRES_DATABASE_REFERENCE.md`](POSTGRES_DATABASE_REFERENCE.md) (schéma DB), [`DICTIONNAIRE_COLONNES.md`](DICTIONNAIRE_COLONNES.md) (colonnes détaillées).

---

## Sommaire

1. [Persona Usager](#persona-usager--14-widgets) — 14 widgets, pages Usager_1/2 (Usager_3/4/5 n'utilisent aucun widget de ce dossier)
2. [Persona Pro TCL](#persona-pro-tcl--25-widgets) — 25 widgets, pages Pro_1/2/3/4/6/7
3. [Persona Élu](#persona-élu--19-widgets) — 19 widgets, pages Elu_1 à Elu_5

---

# Persona Usager — 14 widgets

**Constat préalable** : les 14 widgets de `dashboard/components/widgets/usager/` ne sont utilisés que par **2 des 5 pages Usager** :
- **Usager_1_Mon_Trajet.py** utilise 11 widgets : `search_bar`, `weather_widget`, `velov_widget`, `traffic_widget`, `velov_trip`, `itinerary`, `lieux_velov_map`, `velov_map`, `mode_comparison`, `mode_summary`, `transit_trip`.
- **Usager_2_Alertes.py** utilise les 3 restants : `alert_card`, `alert_settings`, `alert_timeline`.
- **Usager_3_Notre_Modele.py**, **Usager_4_Sources_Donnees.py**, **Usager_5_Statut_Service.py** construisent leurs propres graphiques Plotly inline et n'importent aucun widget de ce dossier (ils lisent directement `cached_xgb_accuracy_summary`, `cached_predictions_vs_actuals`, `cached_source_health`, `cached_recent_alerts`).

### `alert_card.py` — Page : Usager_2
**Affichage :** carte HTML avec bordure colorée selon sévérité, icône, titre, description, bloc "Action".
**Calcul :** aucun — pure fonction de rendu, lookup de couleur `STATUS_COLORS.get(sev, ...)`.
**Source de données :** `cached_recent_alerts(hours=6, limit=30)` → `load_recent_alerts()` → `get_recent_alerts()` (`src/data/db_query.py`). **Point notable** : malgré le nom, la requête lit **`silver.chantiers_actifs`** (chantiers en cours), pas une table `gold.alerts`. Les champs `severity` (toujours `'Warning'`) et `action` (toujours `'Déviation potentielle'`) sont codés en dur dans la requête SQL.
**Fichier(s) :** `dashboard/components/widgets/usager/alert_card.py` ; `dashboard/components/data_cache.py::cached_recent_alerts` → `src/data/data_loader.py::load_recent_alerts` → `src/data/db_query.py::get_recent_alerts` (table `silver.chantiers_actifs`).

### `alert_settings.py` — Page : Usager_2
**Affichage :** 6 checkboxes, 1 slider double (fenêtre de notification), 1 radio (mode notification).
**Calcul :** aucun. Les valeurs vont dans `st.session_state` mais ne pilotent **aucun filtrage réel** des alertes affichées ailleurs — pur shell UI non câblé.
**Source de données :** aucune.
**Fichier(s) :** `dashboard/components/widgets/usager/alert_settings.py`.

### `alert_timeline.py` — Page : Usager_2
**Affichage :** frise verticale, une ligne par alerte (heure, point coloré, titre/description).
**Calcul :** tri `sorted(alerts, key=lambda a: a.get("timestamp",""), reverse=True)` + parsing défensif de l'heure.
**Source de données :** même chaîne que `alert_card.py` (`silver.chantiers_actifs`).
**Fichier(s) :** `dashboard/components/widgets/usager/alert_timeline.py`.

### `itinerary.py` — Page : Usager_1
**Affichage :** radio 3 alternatives voiture, 4 metrics (durée/distance/vitesse/confiance), carte Folium (polylines colorées par vitesse, marqueurs), expander détail par segment.
**Calcul :** `_speed_to_color()` (seuils ≥40 vert → &lt;8 rouge foncé) ; `_fmt_route_label()` construit `"8.0 km · 24 min · Rue A → Rue B"` ; centre de carte = moyenne simple lat/lon. Le calcul d'itinéraire lui-même est délégué à pgRouting.
**Source de données :** **contourne `data_cache.py`**. (1) `_resolve_address()` → requête SQL directe sur `referentiel.lieux_lyon` (`LIKE` sur le nom). (2) `compute_itinerary_alternatives()` (`src/routing/pathfinder.py`) → `pgr_ksp` (k=3) sur `osm.ways`/`osm.ways_vertices_pgr`. Confiance = `0.5 + 0.5 × coverage_ratio` (% d'arêtes OSM avec capteur Grand Lyon à proximité, `_compute_pgrouting_confidence()`).
**Fichier(s) :** `dashboard/components/widgets/usager/itinerary.py` ; `src/routing/pathfinder.py::compute_itinerary_alternatives/_compute_pgrouting_confidence` ; requête directe `referentiel.lieux_lyon`.

### `lieux_velov_map.py` — Page : Usager_1
**Affichage :** carte Folium — 21 lieux emblématiques reliés en pointillé à leurs bornes Vélov les plus proches.
**Calcul :** `_distance_color()` (seuils &lt;100m vert / &lt;300m orange / sinon rouge) ; temps de marche = `distance_m/1000/4.5*60` (4,5 km/h) ; centre carte = moyenne des lat/lon. Le classement des bornes (rank) est déjà fait côté SQL.
**Source de données :** **contourne `data_cache.py`** — appel direct `get_lieux_with_velov(k=1)` → vue **`referentiel.v_lieux_velov_proches`**.
**Fichier(s) :** `dashboard/components/widgets/usager/lieux_velov_map.py` ; `src/data/db_query.py::get_lieux_with_velov` → `referentiel.v_lieux_velov_proches`.

### `mode_comparison.py` — Page : Usager_1
**Affichage :** 3 cartes TC/Voiture/Vélov, gagnant mis en avant (badge "RECOMMANDÉ"), insight CO2, bouton "Voir le détail".
**Calcul (substantiel) :** `_compute_recommendation()` :
```python
if critere == "temps":
    scores[mode] = duration if duration > 0 else 9999.0
else:  # "cout"
    scores[mode] = duration + cost / 0.30   # 1 min ~ 0.30€ (CEREMA 2023, ~18€/h)
winner = min(feasible, key=lambda k: feasible[k])
```
`_render_insight()` : `saved_co2 = voiture_co2 - winner_co2` (affiché si positif et gagnant≠voiture) ; équivalence calories `kcal // 50`.
**Source de données :** aucun appel DB propre — reçoit le dict `results` construit par la page (lui-même alimenté par `cached_traffic()` pour la vitesse voiture + `calculate_impact()` Python pur pour coût/CO2/calories).
**Fichier(s) :** `dashboard/components/widgets/usager/mode_comparison.py` ; `src/routing/eco_calculator.py::calculate_impact` ; `dashboard/components/data_cache.py::cached_traffic`.

### `mode_summary.py` — Page : Usager_1
**Affichage :** bandeau mode + 4-5 `st.metric` (Durée/Coût/CO2/Distance/[Calories]).
**Calcul :** aucun calcul propre — affiche le dict `impact` déjà calculé, seule transformation : `int((penalty-1.0)*100)` pour le % de majoration congestion.
**Source de données :** `impact` vient de `calculate_impact()` (`src/routing/eco_calculator.py`, Python pur, sans DB), appelé en amont par la page.
**Fichier(s) :** `dashboard/components/widgets/usager/mode_summary.py`.

### `search_bar.py` — Page : Usager_1
**Affichage :** 2 selectbox (origine/destination), radio horaire, `st.segmented_control` mode transport, radio critère.
**Calcul :** aucun calcul de trajet — construction de la liste d'options (`icône + nom`) et normalisation `critere = "temps" if critere_label.startswith("⏱") else "cout"`.
**Source de données :** `cached_lyon_addresses_with_coords()` → `load_lyon_addresses_with_coords()` (cache process 60s additionnel) → `get_lieux_lyon_with_coords()` → `SELECT name, lon, lat, type FROM referentiel.lieux_lyon WHERE is_active = TRUE`.
**Fichier(s) :** `dashboard/components/widgets/usager/search_bar.py` ; `dashboard/components/data_cache.py::cached_lyon_addresses_with_coords` → `src/data/db_query.py::get_lieux_lyon_with_coords`.

### `traffic_widget.py` — Page : Usager_1
**Affichage :** bandeau fraîcheur, 3 metrics (vitesse moyenne/état/bouchons), card prédiction H+1h, expander top bouchons.
**Calcul :** rien dans le widget — tout est calculé en amont dans `load_traffic()` : vitesse moyenne = `city_df[city_df.vitesse_limite_kmh<=50]["speed_kmh"].mean()` ; seuils congestion (`≥35` fluide, `≥25` modéré, `≥15` dense, sinon bloqué) ; jam severity `max(0,int((30-speed)/5))` min de retard estimé ; fraîcheur via seuils `FRESHNESS_LIVE_MAX_S`/`FRESHNESS_STALE_MAX_S`.
**Source de données :** `cached_traffic()` → `load_traffic()` → `get_latest_traffic()` (`gold.traffic_features_live`, fenêtre 2h) + `get_traffic_bottlenecks()` (agrégat `AVG/MIN(speed_kmh)` par capteur sur 1h) + `get_traffic_predictions(horizon_minutes=60)` (`gold.trafic_predictions`, `horizon_h=1`).
**Fichier(s) :** `dashboard/components/widgets/usager/traffic_widget.py` ; `dashboard/components/data_cache.py::cached_traffic` → `src/data/data_loader.py::load_traffic` → `src/data/db_query.py::get_latest_traffic/get_traffic_bottlenecks/get_traffic_predictions`.

### `transit_trip.py` — Page : Usager_1
**Affichage :** bandeau Direct/Correspondance, 4 metrics (durée/marche/correspondances/retard), cards par segment, disclaimer limites.
**Calcul :** `_estimate_transit_duration_min()` (`src/routing/pathfinder_multimodal.py`) :
```python
duration = walk_to + wait + drive + delay_avg_min + walk_from
# wait = cadence_min / 2.0 (attente moyenne sur fréquence uniforme)
# drive = (distance_m/1000) / vitesse(mode) * 60
```
Confiance réduite si `n_obs < 10` (`max(0.3, confidence-0.2)`), fallback 0.4/0.2 sans données de cadence.
**Source de données :** `cached_transit_itinerary()` → `load_transit_itinerary()` → `plan_transit_trip()` (routing, pas simple SQL) : combine `referentiel.lieux_transports`, `referentiel.lieux_calendrier` (cadences), `gold.bus_delay_segments` (retard 7j glissant), `referentiel.lieux_lyon` (coords).
**Fichier(s) :** `dashboard/components/widgets/usager/transit_trip.py` ; `dashboard/components/data_cache.py::cached_transit_itinerary` → `src/data/data_loader.py::load_transit_itinerary` → `src/routing/pathfinder_multimodal.py::plan_transit_trip/_estimate_transit_duration_min`.

### `velov_map.py` — Page : Usager_1 (`render_velov_map_compact`)
**Affichage :** carte Pydeck (ScatterplotLayer), couleur selon vélos dispo, tooltip + prédiction H+1h.
**Calcul :** `_bikes_to_color()` (seuils 0/&lt;5/&lt;10/sinon) ; jointure pandas stations × dernière prédiction par station (`drop_duplicates` sur `prediction_timestamp` décroissant).
**Source de données :** `get_velov_stations_geo()` **appelé directement** (sans cache) → `silver.velov_clean` (fenêtre 30min) ; `cached_velov_predictions(horizon_minutes=60)` → `gold.velov_predictions` (règle H+1h stricte, `ValueError` sinon).
**Fichier(s) :** `dashboard/components/widgets/usager/velov_map.py` ; `src/data/db_query.py::get_velov_stations_geo` (`silver.velov_clean`) ; `dashboard/components/data_cache.py::cached_velov_predictions` (`gold.velov_predictions`).

### `velov_trip.py` — Page : Usager_1
**Affichage :** 4 metrics, 2 cards station départ/arrivée (statut coloré), alternatives si borne pleine/vide, carte Folium 3 segments (marche/vélo/marche), maillage en pointillé.
**Calcul (substantiel) :** statut borne : `0 vélos→VIDE`, `0 docks→PLEINE`, `<5 l'un des deux→FAIBLE`, sinon `OK` (seuil 5 en affichage). Distance segment vélo = `haversine(depart,arrivee) × 1.3` (facteur détour urbain). Le score/statut de sélection de borne vient en réalité de la vue SQL **`referentiel.v_lieux_velov_smart`** (migration_042/043) :
```sql
score = CASE WHEN bikes=0 THEN -10000 WHEN docks=0 THEN -5000 ELSE -haversine_m(lieu,borne) END
status = CASE WHEN bikes=0 THEN 'VIDE' WHEN docks=0 THEN 'PLEINE'
              WHEN bikes<3 OR docks<3 THEN 'FAIBLE' ELSE 'OK' END
```
(seuil SQL = 3, seuil affichage widget = 5 — les deux coexistent).
**Sécurité (migration_045, 2026-07-05) :** avant les cards, `render_velov_safety_banner()` affiche un bandeau `st.error`/`st.warning` si la pollution est dégradée ou la vigilance canicule active (dept 69) — **avertit sans bloquer** le mode Vélov (décision projet : l'usager reste libre de choisir).
**Source de données :** **contourne `data_cache.py`** — `plan_velov_trip()` (`src/routing/pathfinder_multimodal.py`) → `referentiel.v_lieux_velov_smart` (sur `silver.velov_clean`, fenêtre bornée 15min) + `referentiel.v_velov_neighbors` (maillage &lt;200m) + `referentiel.lieux_lyon`. Bandeau sécurité : `cached_velov_safety_advisory()` → `gold.v_velov_safety_advisory`.
**Fichier(s) :** `dashboard/components/widgets/usager/velov_trip.py` ; `src/routing/pathfinder_multimodal.py::plan_velov_trip` ; vue `referentiel.v_lieux_velov_smart` (`scripts/sql/migration_043_bound_velov_latest_time_window.sql`) ; `dashboard/components/velov_safety_banner.py::render_velov_safety_banner`.

### `velov_widget.py` — Page : Usager_1
**Affichage :** bandeau sécurité (pollution/canicule, migration_045) puis N cards horizontales (station : vélos/docks/statut/prédiction H+1h avec flèche tendance).
**Calcul :** statut (`0→Vide`, `<5→Faible`, sinon `OK`) ; tendance `delta = pred - bikes` → flèche ↗/↘/→.
**Source de données :** `cached_velov_stations()` → `get_velov_stations_geo()` (`silver.velov_clean`) + `cached_velov_predictions()` → `get_velov_predictions()` (`gold.velov_predictions`). Variante page : `load_nearest_velov_stations()` → fonction SQL `referentiel.nearest_velov_stations()`. Bandeau sécurité : `cached_velov_safety_advisory()` → `gold.v_velov_safety_advisory`.
**Fichier(s) :** `dashboard/components/widgets/usager/velov_widget.py` ; `dashboard/components/data_cache.py::cached_velov_stations/cached_velov_predictions/cached_velov_safety_advisory` ; `dashboard/components/velov_safety_banner.py::render_velov_safety_banner`.

### `weather_widget.py` — Page : Usager_1
**Affichage :** card météo (icône/temp/pluie/vent) + conseil vélo coloré, avec bandeau `st.error`/`st.warning` si pollution/canicule (migration_045, 2026-07-05).
**Calcul :** `_wmo_to_label()` (table de correspondance 25 entrées, codes WMO Open-Meteo). Sévérité combinée = `max(sévérité_météo, sévérité_sécurité)` :
- météo : `rain>0.5 OR wind>35 → 2 (déconseillé)` ; `rain>0.1 OR wind>25 → 1 (prudence)` ; sinon `0`
- sécurité (`gold.v_velov_safety_advisory`) : `status="severe"→2`, `"warning"→1`, `"ok"/"unknown"→0` (jamais de faux "ok" — "unknown" = donnée absente, traité neutre)
- `severity==2 → "Vélov déconseillé"` (rouge) ; `severity==1 → "Vélov possible mais prudence"` (orange) ; sinon `"Vélov recommandé"` (vert). Si la sécurité déclenche, la raison (ex. "Pollution dégradée (indice européen 4/6)") s'affiche dans le détail + un `st.error`/`st.warning` dédié en dessous de la carte.
**Source de données :** `cached_weather_hourly()` → `load_weather_hourly()` → `get_weather_hourly()` → `silver.meteo_hourly` (widget prend `df.iloc[0]`, ligne la plus récente). Sécurité : `get_velov_safety_severity()` (`dashboard/components/velov_safety_banner.py`) → `cached_velov_safety_advisory()` → `gold.v_velov_safety_advisory` (JOIN `silver.air_quality_clean` + `bronze.vigilance_meteo`).
**Fichier(s) :** `dashboard/components/widgets/usager/weather_widget.py` ; `dashboard/components/data_cache.py::cached_weather_hourly/cached_velov_safety_advisory` → `src/data/db_query.py::get_weather_hourly/get_velov_safety_advisory` ; `dashboard/components/velov_safety_banner.py::get_velov_safety_severity`.

---

# Persona Pro TCL — 25 widgets

Pages : Pro_1_PCC_Live, Pro_2_Heatmap_OTP, Pro_3_Correlation, Pro_4_Simulateur, Pro_6_Pipeline_Mgmt, Pro_7_Model_Monitoring.

### `alert_ticker.py` — Pro_1
**Affichage :** bandeau défilant (CSS `@keyframes`) de pastilles d'alertes colorées.
**Calcul :** aucun — mapping sévérité→couleur, duplication de liste pour boucler l'animation.
**Source :** `cached_recent_alerts()` → `get_recent_alerts()` → `silver.chantiers_actifs` (même source que côté Usager).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/alert_ticker.py`.

### `backtest_dashboard.py` — Pro_7
**Affichage :** 4 KPI (MAE/MAPE/P90/n_pairs), scatter TomTom vs XGBoost (ligne y=x), courbe MAE 7j, distribution `accuracy_band`, top 10 pires prédictions.
**Calcul :** `mae_kmh = mean(error_abs_kmh)`, `mape_pct = mean(error_pct)`, `p90_kmh = quantile(error_abs_kmh, 0.9)`. Seuils couleur : `MAE_GREEN=5.0`, `MAE_YELLOW=15.0`, `MAE_ALERT=10.0` km/h. Top 10 = `nlargest(10, "error_abs_kmh")`.
**Source :** `cached_xgb_vs_tomtom()` → `gold.mv_xgb_vs_tomtom` ; `cached_xgb_accuracy_summary()` → `gold.v_xgb_accuracy_summary`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/backtest_dashboard.py` ; `src/data/db_query.py::get_xgb_vs_tomtom/get_xgb_accuracy_summary`.

### `before_after_chart.py` — Pro_4
**Affichage :** 2 barres Avant/Après + flèche delta.
**Calcul :** `delta = new_value - base_value`, couleur selon signe. Pas d'accès DB — reçoit les valeurs de `Pro_4_Simulateur.py`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/before_after_chart.py`.

### `bus_traffic_spatial.py` — Pro_3
**Affichage :** 4 KPI (Infra/Exploitation/Voie bus OK/OK), scatter `bus_delay_sec × traffic_speed_kmh` par diagnostic, top 20 zones.
**Calcul :** seuils fixes `DELAY_THRESHOLD=120s`, `SPEED_THRESHOLD=25km/h` ; `nlargest(top_n,"bus_delay_sec")` filtré sur `diagnosis in [infra,operations]`. Coercition NUMERIC (Decimal→float) via `pd.to_numeric`.
**Source :** `cached_bus_traffic_spatial()` → vue matérialisée `gold.mv_bus_traffic_spatial` (JOIN spatial 0.001°≈100m).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/bus_traffic_spatial.py` ; `src/data/db_query.py::get_bus_traffic_spatial/get_bus_traffic_spatial_diagnosis_counts`.

### `cause_analysis.py` — Pro_3
**Affichage :** card diagnostic causal (1 segment) + recommandation.
**Calcul :** mapping statique `diagnosis → (cause, recommandation, couleur)` (4 cas : infra/operations/bus_lane_ok/ok). Pas de calcul numérique.
**Source :** aucune propre — reçoit un dict `segment` construit par `Pro_3_Correlation.py` depuis `cached_infra_bottlenecks(top=500)`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/cause_analysis.py`.

### `coherence_scatter.py` — Pro_3
**Affichage :** KPI par statut cohérence, scatter TomTom vs GL (±10km/h tolérance), top 20 deltas, table capteurs HS.
**Calcul :** `abs_delta = delta_kmh.abs()` puis `nlargest`. Seuils : `|delta|>20→drift`, `>10→minor_drift`, sinon `ok`.
**Source :** `cached_tomtom_coherence()` → `gold.v_coherence_tomtom_vs_grandlyon` (migration 14, `ST_DWithin<200m`) ; `cached_tomtom_gl_drift()` → `gold.v_tomtom_gl_drift`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/coherence_scatter.py`.

### `correlation_matrix.py` — Pro_3
**Affichage :** matrice 2×2 (bus_state × traffic_state), tableau détaillé.
**Calcul :** `_bus_state`: `delay_s>120 → "delayed"` sinon `"on_time"` ; `_traffic_state`: `speed<25 → "jammed"` sinon `"fluid"`.
**Source :** `cached_infra_bottlenecks(top=500)` → table **legacy `gold.infrastructure_bottlenecks`** (JOIN global par heure — remplacée côté Élu par `mv_bus_traffic_spatial` mais encore lue ici).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/correlation_matrix.py` ; `src/data/db_query.py::get_infrastructure_bottlenecks`.

### `frequency_slider.py` — Pro_4
**Affichage :** slider bus ±, selectbox scénario, plage horaire.
**Calcul :** aucun — retourne le dict de sélection utilisateur.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/frequency_slider.py`.

### `line_comparison.py` — Pro_2
**Affichage :** tableau multi-lignes, dégradé couleur sur OTP%/Charge%.
**Calcul :** arrondi 1 décimale des KPIs, pas d'agrégation nouvelle.
**Source :** `cached_line_kpis()` → vue `gold.mv_line_kpis_live`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/line_comparison.py`.

### `line_kpis.py` — Pro_1
**Affichage :** tableau interactif (ProgressColumn OTP/Charge), tri 10 options, slider Top N, détail dépliable par ligne.
**Calcul :** `delay_min = clamp(delay_min, 0, 30)`. Tri via dict `SORT_OPTIONS` puis `head(top_n)`.
**Source :** `cached_line_kpis()` → `gold.mv_line_kpis_live`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/line_kpis.py`.

### `line_selector.py` — Pro_3, Pro_4
**Affichage :** multiselect/selectbox lignes TCL.
**Calcul :** aucun.
**Source :** `cached_tcl_lines()` → référentiel **statique Python** `src/data/tcl_lines.py` (pas une table Gold).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/line_selector.py`.

### `meteo_impact.py` — Pro_3
**Affichage :** 3 KPI "pire condition" par mode, tableau 5 bandes météo × 3 modes, bar chart deltas.
**Calcul :** `_find_worst_band()` — `idxmin()` (trafic/vélov, pire = delta le plus négatif) / `idxmax()` (TCL, pire = delta le plus positif). Deltas déjà calculés côté SQL.
**Source :** `cached_meteo_impact()` → vue matérialisée `gold.mv_meteo_impact` (30j : météo × trafic × TCL × vélov).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/meteo_impact.py`.

### `modal_shift_alert.py` — Pro_3
**Affichage :** 4 KPI (stations alarme/lignes critiques-vigilance/couverture), table stations alarme, bar chart top 10 lignes.
**Calcul :** couleur z-score (`<-2.0` rouge, `<0` jaune, sinon vert), seuil `ANOMALY_Z_THRESHOLD=-2.0`. Le z-score est calculé côté SQL.
**Source :** `cached_velov_transit_coupling()` → vue `gold.mv_velov_transit_coupling` (z-score vélos &lt;300m d'une ligne TC).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/modal_shift_alert.py`.

### `model_monitoring.py` — Pro_7
**Affichage :** statut XGBoost actif/paused, Model Registry MLflow, métriques H+1h, courbe MAE 7j, panel drift PSI, analyse modèle Vélov, panel data quality.
**Calcul :** disponibilité H+1h vérifiée via la **fraîcheur** de `cached_predictions_vs_actuals(limit=1)` — fix documenté CLAUDE.md remplaçant l'ancien check de fichier local (toujours `False`, volume `models/` non monté). `drift_share_pct = drift_share*100`. `width = confidence_high - confidence_low` (Vélov).
**Source :** MLflow Tracking Server (registre/métriques) + `cached_latest_drift_report()` → `gold.model_drift_reports` + `cached_predictions_vs_actuals()` → **`gold.trafic_predictions` (live, confirmé)** + `cached_velov_predictions()` → `gold.velov_predictions`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/model_monitoring.py` ; `src/data/db_query.py::get_latest_drift_report/get_traffic_predictions`.

### `multimodal_heatmap.py` — Pro_3
**Affichage :** 4 KPI (Saturé/Tendu/Vélov rare/Fluide), carte Folium grille 0.01°, top 15 cellules.
**Calcul :** seuils `SCORE_THRESHOLDS={saturated:7.0, tendu:4.0}` sur `score_multimodal` (0-10, calculé en SQL) ; `nlargest(15,"score_multimodal")` filtré `score>=4.0`.
**Source :** `cached_multimodal_grid()` → vue matérialisée `gold.mv_multimodal_grid` (Axe 1).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/multimodal_heatmap.py`.

### `network_map.py` — Pro_1
**Affichage :** carte Pydeck bus GPS colorés par retard.
**Calcul :** `_delay_to_color()` (0min vert, ≤3 jaune, ≤6 orange, &gt;6 rouge) ; fraîcheur `age_min>5` → warning.
**Source :** `cached_buses_positions()` → `silver.tcl_vehicles_clean` (fenêtre 30min).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/network_map.py`.

### `otp_filters.py` — Pro_2
**Affichage :** 3 selectbox/multiselect (période/jours/météo).
**Calcul :** aucun. **Note** : les filtres "jours"/"météo" ne sont pas reliés à la heatmap — seule `period` (→`days`) est effective.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/otp_filters.py`.

### `otp_heatmap.py` — Pro_1 (mini), Pro_2
**Affichage :** heatmap Plotly lignes×24h ; variante mini = top 15 pires lignes.
**Calcul :** moyenne horaire par ligne sur les dates sélectionnées, tri par moyenne globale (pires en premier si pas de sélection).
**Source :** `cached_otp_heatmap_data()` → vue matérialisée `gold.mv_otp_heatmap`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/otp_heatmap.py`.

### `otp_projection.py` — Pro_4
**Affichage :** 3 metrics (OTP actuel/projeté/IC95%), card impact.
**Calcul :** modèle linéaire codé en dur : `delta = buses_added*2.5` (ajout) ou `*3.0` (retrait) ; `new_otp = clamp(base+delta, 60, 98)` ; IC arbitraire ±2pts ; gain voyageurs = `abs(delta)*1500` (hypothèse "1500 voyageurs/point OTP").
**Source :** aucune propre — reçoit `simulation` (de `frequency_slider`) et `base_otp` (de `cached_line_kpis()`).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/otp_projection.py`.

### `pipeline_management.py` — Pro_6
**Affichage :** 4 KPI DAGs, liste DAGs (Trigger/Clear/Fail), 6 health checks, fraîcheur sources Bronze, feed alertes.
**Calcul :** comptages simples (`n_success/n_running/n_failed`, `n_ok/n_stale`).
**Source :** DAGs → **API REST Airflow** (`src/data/airflow_client.py`, pas PostgreSQL) ; fraîcheur Bronze → `get_bronze_source_counts()` ; health checks → `src/monitoring/health_checks.py::run_all_checks()` ; alertes → `cached_recent_alerts()` → `silver.chantiers_actifs`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/pipeline_management.py`.

### `propagation_map.py` — Pro_3
**Affichage :** 4 KPI, carte Folium `AntPath` (flèches directionnelles), top 20 paires, popover Granger.
**Calcul (le plus élaboré de tous les widgets Pro TCL — vrai calcul statistique en Python/numpy) :**
- Corrélation croisée laggée : scan des lags ±3 pas (±15min), `r = dot(aa,bb)/sqrt(ss_aa×ss_bb)` (Pearson) par lag, conservation du `best_r`/`best_lag`. `lag>0` → B leader de A.
- Test de causalité de **Granger** (`statsmodels.tsa.stattools.grangercausalitytests`) sur le top N paires, deux directions testées, `significant = min_p < 0.05`.
- Classification intensité : `strong≥0.7, medium≥0.5, weak≥0.3, sinon noise`.
**Source :** `cached_congestion_propagation_pairs()` → vue matérialisée `gold.mv_congestion_propagation_pairs` (~50k paires, basée sur `gold.dim_spatial_adjacency`) ; `cached_traffic_speeds_for_propagation()` → `gold.traffic_features_live` (fenêtre 6h).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/propagation_map.py`.

### `segment_table.py` — Pro_3
**Affichage :** tableau filtrable (multiselect diagnostic).
**Calcul :** `bus_state`/`traffic_state` (mêmes seuils que `correlation_matrix.py`), `delay_min = round(delay_s/60,1)`.
**Source :** `cached_infra_bottlenecks(top=500)` → table **legacy `gold.infrastructure_bottlenecks`** (confirmé par le commentaire en tête de fichier).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/segment_table.py`.

### `sensor_saturation.py` — Pro_6
**Affichage :** 4 KPI (OK/Stale/Stuck/No data), tableau trié par priorité (stuck&gt;stale&gt;no_data&gt;ok), ProgressColumn saturation/amplitude.
**Calcul :** `pct_stuck>5%` → alerte ; `pct_stale>10%` → warning. Métriques déjà calculées en SQL.
**Source :** `cached_sensor_saturation()` → vue matérialisée `gold.mv_sensor_saturation`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/sensor_saturation.py`.

### `source_health_monitor.py` — Pro_6
**Affichage :** jauge Plotly score santé global 0-100, compteurs par statut, grille source×statut, barres complétude Silver.
**Calcul :** `_global_score()` = moyenne pondérée `Σ(health_score_i×poids_i)/Σ(poids_i)` (poids : trafic=3, TCL=2, Vélov=2, météo=1, AQ=1, chantiers=1, tomtom=1, predictions=2).
**Source :** `cached_source_health()` → vue `gold.v_source_health` ; `cached_data_completeness()` → vue `gold.v_data_completeness`.
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/source_health_monitor.py`.

### `traffic_map.py` — Pro_1
**Affichage :** carte Pydeck (live vs prédit H+1h), couleur ratio vitesse/limite, 4 KPI (fluidité/segments/dégradation/amélioration).
**Calcul :** `_ratio_to_rgb()` (&lt;0.3 rouge → sinon vert) ; `n_degrade=count(delta<-5)`, `n_improve=count(delta>5)`. Colonnes NUMERIC (Decimal psycopg2) coercées via `_coerce_numeric_columns` (`src/data/data_loader.py`) — **fix du crash `TypeError: Expected numeric dtype`** documenté CLAUDE.md.
**Source :** `cached_traffic_live_vs_predicted()` → JOIN `gold.traffic_features_live` (live) × `gold.trafic_predictions` (horizon_h=1).
**Fichier(s) :** `dashboard/components/widgets/pro_tcl/traffic_map.py` ; `src/data/data_loader.py::_coerce_numeric_columns`.

**Points notables croisés Pro TCL :** `correlation_matrix.py` et `segment_table.py` lisent encore `gold.infrastructure_bottlenecks` (legacy) alors que les widgets Élu sont passés sur `gold.mv_bus_traffic_spatial`. `propagation_map.py` est le seul widget Pro TCL à faire du vrai calcul statistique Python (corrélation laggée + Granger) — tout le reste ne fait que seuiller/formater des valeurs déjà calculées en SQL. `model_monitoring.py` est le seul à combiner PostgreSQL et MLflow Tracking Server.

---

# Persona Élu — 19 widgets

Pages : Elu_1_Synthese, Elu_2_Bottlenecks, Elu_3_Avant_Apres, Elu_4_Simulateur, Elu_5_Rapport.

### `kpi_cards.py` — Elu_1
**Affichage :** 5 cartes KPI (part modale TC, ponctualité, CO₂ évité, bottlenecks actifs, satisfaction) : valeur, delta YTD coloré, cible 2026.
**Calcul :** formatage défensif uniquement. `current = values[-1]`, `delta_ytd = current - values[0]` (delta brut 1er→dernier mois).
**Source :** `cached_elu_kpis_dict()` → `load_elu_kpis_dict()` → `load_kpis_12_months()` → vue `gold.mv_kpis_12_months`.
**Fichier(s) :** `dashboard/components/widgets/elu/kpi_cards.py` ; `src/data/data_loader.py::load_elu_kpis_dict/load_kpis_12_months`.

### `executive_summary.py` — Elu_1
**Affichage :** bloc narratif + bandeau tendance (AMÉLIORATION/DÉGRADATION/STABLE) + 5 mini-KPIs.
**Calcul :** règles sur les deltas YTD : `pm_delta>0 and bn_delta<0 → AMÉLIORATION` ; `pm_delta<0 or ponc_delta<-1 → DÉGRADATION` ; sinon `STABLE`.
**Source :** `cached_elu_kpis_dict()` (même chaîne que `kpi_cards.py`).
**Fichier(s) :** `dashboard/components/widgets/elu/executive_summary.py`.

### `network_health_gauge.py` — Elu_1
**Affichage :** jauge Plotly 0-100 (bandes couleur), bannière diagnostic, 4 sous-jauges (trafic/TCL/vélov/météo), sparkline 24h.
**Calcul :** le score est calculé **côté SQL** par `gold.fn_network_health_score()` (redistribution des poids si source indisponible) — le widget mappe juste `diagnosis→couleur` et fixe les seuils d'affichage des sous-jauges.
**Source :** `cached_network_health_score()` → `SELECT * FROM gold.fn_network_health_score()` ; sparkline : `cached_network_health_history(hours=24)` → table `gold.network_health_history` (`*/15min`).
**Fichier(s) :** `dashboard/components/widgets/elu/network_health_gauge.py` ; `src/data/db_query.py::get_network_health_score` ; `src/data/network_health_history.py::get_network_health_history`.

### `drift_status_badge.py` — Elu_1
**Affichage :** bandeau 1 ligne état drift XGBoost H+1h + popover PSI.
**Calcul :** `mae_kmh` = moyenne **pondérée** par `n_pairs` : `sum(mae×n_pairs)/sum(n_pairs)`. `_diagnose_drift()` cascade de règles sur statuts PSI de 5 colonnes (ex. `error_drift and xgb_drift and not tomtom_drift → critical`). `_classify()` combine ce diagnostic avec seuils MAE bruts (`MAE_GREEN=7.0`, `MAE_YELLOW=12.0` km/h).
**Source :** `cached_xgb_accuracy_summary(hours=24)` → vue `gold.v_xgb_accuracy_summary` ; `cached_latest_drift_report()` → table `gold.model_drift_reports` (rapport Evidently PSI en JSONB).
**Fichier(s) :** `dashboard/components/widgets/elu/drift_status_badge.py`.

### `data_quality_badge.py` — Elu_1
**Affichage :** bandeau santé sources (ex. " 8/8 sources actives, score 94/100").
**Calcul :** `_global_score()` = moyenne **pondérée** par source : poids codés en dur (`trafic_boucles=3, tcl_vehicles=2, velov=2, meteo=1, air_quality=1, chantiers=1, tomtom_traffic=1, trafic_predictions=2`, défaut 1) : `score = Σ(health_score_i×poids_i)/Σ(poids_i)`.
**Source :** `cached_source_health()` → vue `gold.v_source_health`.
**Fichier(s) :** `dashboard/components/widgets/elu/data_quality_badge.py`.

### `data_quality_detail.py` — Elu_1
**Affichage :** drill-down qualité — 3 KPI cards, tableau dernier run, historique 5 derniers runs.
**Calcul :** post-traitement pandas — `groupby("table_name")["checked_at"].max()` (dernier run par table), pire statut parmi sous-checks (`critical > warning > ok`).
**Source :** `cached_quality_report(limit=200)` → table append-only `gold.data_quality_log` (1x/jour, validators `src/transformation/data_quality.py`).
**Fichier(s) :** `dashboard/components/widgets/elu/data_quality_detail.py`.

### `trend_chart.py` — Elu_1
**Affichage :** courbe 12 mois + ligne cible 2026.
**Calcul :** aucun — trace directement `history` et `target_2026`.
**Source :** `cached_elu_kpis_dict()` → `gold.mv_kpis_12_months`.
**Fichier(s) :** `dashboard/components/widgets/elu/trend_chart.py`.

### `top_decisions.py` — Elu_1
**Affichage :** N cartes "décisions à arbitrer" (zone, lignes, voyageurs/j, gain, coût, ROI).
**Calcul :** aucun propre — affiche les champs déjà calculés par `load_bottlenecks_top()` (voir `bottleneck_ranking.py`).
**Source :** `cached_bottlenecks_top()` → `load_bottlenecks_summary()` → vue matérialisée `gold.mv_bus_traffic_spatial`.
**Fichier(s) :** `dashboard/components/widgets/elu/top_decisions.py`.

### `news_section.py` — Elu_1
**Affichage :** 4 cartes suggestions de communication politique.
**Calcul :** aucun — **textes 100% codés en dur**, pas dérivés de la DB.
**Source :** aucune.
**Fichier(s) :** `dashboard/components/widgets/elu/news_section.py`.

### `pdf_generator.py` — Elu_1, Elu_5
**Affichage :** bouton génération PDF + téléchargement.
**Calcul :** aucun — délègue à `src/reporting/pdf_renderer.py` (WeasyPrint, fallback reportlab).
**Source :** ne lit pas la DB — reçoit un dict `sections` déjà construit par la page appelante.
**Fichier(s) :** `dashboard/components/widgets/elu/pdf_generator.py` ; `src/reporting/pdf_renderer.py::generate_pdf/render_html_template`.

### `bottleneck_map.py` — Elu_2
**Affichage :** carte Folium, CircleMarker par bottleneck (rayon = rang), couleur par diagnostic (rouge=infra/orange=operations/vert=bus_lane_ok/gris=ok).
**Calcul :** aucun propre — lit les champs pré-calculés par `load_bottlenecks_top()`.
**Source :** `cached_bottlenecks_top()` → `gold.mv_bus_traffic_spatial` (MV spatiale 0.001°≈100m, `*/15min`).
**Fichier(s) :** `dashboard/components/widgets/elu/bottleneck_map.py`.

### `bottleneck_ranking.py` — Elu_2
**Affichage :** cartes classées : rang, zone+lignes, diagnostic, voyageurs/j, gain, coût, délai, ROI (coloré vert≤12/jaune≤24/rouge&gt;24 mois).
**Calcul (cœur du module ROI, dans `src/data/data_loader.py::load_bottlenecks_top`)** :
```python
gain_min       = round(avg_bus_delay_s / 60 * 0.5, 1)
cout_M_euros   = {"infra":3.0, "operations":0.8, "bus_lane_ok":0.3, "ok":0.1}[diagnosis]
voyageurs_jour = int(n_observations * 80 * 0.45)          # = n_obs * 36
gain_annuel    = voyageurs_jour * (gain_min/60) * 15 * 2 * 250   # 15€/h, aller-retour, 250j ouvrés
roi_mois       = round(cout_M_euros*1_000_000 / gain_annuel * 12, 1) if gain_annuel > 0 else 999
delai_mois     = max(3, int(cout_M_euros * 6))            # heuristique 1M€ ≈ 6 mois
```
**Vérifié conforme à CLAUDE.md** : gain=`delay/60*0.5` , coût=f(diagnostic) , ROI unifié , voyageurs=`n_obs×36` . Point non documenté dans CLAUDE.md : `delai_mois`.
**Source :** `cached_bottlenecks_top()` → `gold.mv_bus_traffic_spatial` (colonnes `bus_delay_sec, traffic_speed_kmh, bus_observations, lat, lon, diagnosis`).
**Fichier(s) :** `dashboard/components/widgets/elu/bottleneck_ranking.py` ; `src/data/data_loader.py::load_bottlenecks_top` (formules ci-dessus).

### `roi_calculator.py` — Elu_2
**Affichage :** sélecteur bottleneck, 2 sliders (valeur temps €/h, jours/an), 3 métriques (gain annuel/ROI/bénéfice net 5 ans).
**Calcul :** reproduit la formule de `bottleneck_ranking.py` mais recalculée en direct avec les sliders :
```python
gain_annuel   = voyageurs_jour * (gain_min/60) * valeur_temps * 2 * jours_an
roi_mois      = cout_euros / gain_annuel * 12 if gain_annuel > 0 else 999
benefice_5ans = gain_annuel * 5 - cout_euros
```
**Source :** `cached_bottlenecks_top()` → `gold.mv_bus_traffic_spatial`.
**Fichier(s) :** `dashboard/components/widgets/elu/roi_calculator.py`.

### `project_selector.py` — Elu_3
**Affichage :** selectbox aménagements passés.
**Calcul :** dédoublonnage d'étiquettes uniquement.
**Source :** `cached_amenagements_passes()` → table `gold.amenagements_history`.
**Fichier(s) :** `dashboard/components/widgets/elu/project_selector.py`.

### `delta_kpis.py` — Elu_3
**Affichage :** N cartes KPI, delta % coloré (Après vs Avant).
**Calcul :** `delta_pct = (apres-avant)/avant*100` (protégé division par zéro).
**Source :** ne lit pas la DB — reçoit `avant`/`apres` de `project_selector.py` (donc en amont de `gold.amenagements_history`).
**Fichier(s) :** `dashboard/components/widgets/elu/delta_kpis.py`.

### `map_painter.py` — Elu_4
**Affichage :** carte Folium, 10 marqueurs de zones nommées, cliquable.
**Calcul :** distance euclidienne au carré au clic pour trouver la zone la plus proche (seuil &lt;0.001≈30m). **Les 10 coordonnées de zones sont codées en dur** (placeholder documenté en attendant un composant React deck.gl).
**Source :** coordonnées codées en dur ; fallback (si Folium absent) utilise `cached_bottlenecks_top()`.
**Fichier(s) :** `dashboard/components/widgets/elu/map_painter.py`.

### `impact_projection.py` — Elu_4
**Affichage :** 4 metrics (Trafic -12%, Bus +18%, Vélo +45%, CO₂ -23%).
**Calcul :** **aucun calcul, aucune donnée réelle** — constantes codées en dur, avec warning explicite ("estimation générique, en attente d'un modèle ML par zone").
**Source :** aucune.
**Fichier(s) :** `dashboard/components/widgets/elu/impact_projection.py`.

### `cost_estimate.py` — Elu_4
**Affichage :** selectbox type aménagement, slider longueur, coût total M€.
**Calcul :** table de coûts unitaires codée en dur :
```
Couloir bus dédié            : 800 €/m
Piste cyclable bidirection.  : 350 €/m
Piste + couloir bus          : 1100 €/m
Réaménagement carrefour      : forfait 1 500 000 €
PEM (pôle échanges)          : forfait 8 000 000 €
```
`cout_total = longueur_km*1000*cout_unitaire` (linéaire) ou forfait direct.
**Source :** aucune — tarifs 100% codés en dur.
**Fichier(s) :** `dashboard/components/widgets/elu/cost_estimate.py`.

### `template_selector.py` — Elu_5
**Affichage :** selectbox 4 templates de rapport.
**Calcul :** aucun — retourne un dict de config statique.
**Fichier(s) :** `dashboard/components/widgets/elu/template_selector.py`.

### `slide_builder.py` — Elu_5
**Affichage :** multiselect 7 types de slides.
**Calcul :** aucun — construit une liste de dicts `{order, type, content:{}}`.
**Fichier(s) :** `dashboard/components/widgets/elu/slide_builder.py`.

**Points notables Élu :** `bottleneck_ranking.py` concentre toute la logique ROI (gain/coût/voyageurs/délai), reprise telle quelle par `top_decisions.py`, `bottleneck_map.py` et recalculée en direct par `roi_calculator.py`. Trois widgets sont des placeholders assumés sans aucune donnée réelle : `news_section.py`, `impact_projection.py`, `cost_estimate.py`, `map_painter.py` (coordonnées en dur).

---

## Tableau récapitulatif page → widgets

| Page | Widgets |
|------|---------|
| Usager_1_Mon_Trajet | search_bar, weather_widget, velov_widget, traffic_widget, velov_trip, itinerary, lieux_velov_map, velov_map, mode_comparison, mode_summary, transit_trip |
| Usager_2_Alertes | alert_card, alert_settings, alert_timeline |
| Usager_3/4/5 | (aucun widget de ce dossier — graphiques Plotly inline + cached_* directs) |
| Pro_1_PCC_Live | alert_ticker, traffic_map/network_map, otp_heatmap (mini), line_kpis |
| Pro_2_Heatmap_OTP | otp_filters, otp_heatmap, line_comparison |
| Pro_3_Correlation | line_selector, correlation_matrix, segment_table, cause_analysis, bus_traffic_spatial, coherence_scatter, multimodal_heatmap, meteo_impact, modal_shift_alert, propagation_map |
| Pro_4_Simulateur | line_selector, frequency_slider, otp_projection, before_after_chart |
| Pro_6_Pipeline_Mgmt | source_health_monitor, sensor_saturation, pipeline_management |
| Pro_7_Model_Monitoring | model_monitoring, backtest_dashboard |
| Elu_1_Synthese | network_health_gauge, drift_status_badge, data_quality_badge, data_quality_detail, executive_summary, kpi_cards, trend_chart, top_decisions, news_section, pdf_generator |
| Elu_2_Bottlenecks | bottleneck_map, bottleneck_ranking, roi_calculator |
| Elu_3_Avant_Apres | project_selector, delta_kpis |
| Elu_4_Simulateur | map_painter, impact_projection, cost_estimate |
| Elu_5_Rapport | template_selector, slide_builder, pdf_generator |
