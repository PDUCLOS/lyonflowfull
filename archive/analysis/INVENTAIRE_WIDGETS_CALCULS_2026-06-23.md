# Inventaire widgets — code, logique, calculs, source de données

**Date** : 2026-06-23 · **Branche** : `vps`
**Objectif** : pour chaque widget Streamlit utilisé, retrouver en 1 clic
le code source (path:line), la logique, les calculs, et la chaîne de
données jusqu'à la table SQL.

**Convention des liens** : tous les liens vers le code pointent vers le
fichier et la ligne précise (`[file.py:42](file.py)`). Compatible GitHub
(navigation en 1 clic).

**Inventaire principal** (résumé par page, table/vue, TTL, DAG) :
[`docs/INVENTAIRE_WIDGETS_2026-06-23.md`](INVENTAIRE_WIDGETS_2026-06-23.md)

---

## 📑 Table des matières

- [0. Widgets transversaux (T1-T3)](#0-widgets-transversaux)
- [1. Usager — Mon trajet (U1-U12)](#1-usager--mon-trajet-usager_1_mon_trajetpy)
- [2. Usager — Alertes (U13-U16)](#2-usager--alertes-usager_2_alertespy)
- [3. Pro TCL — PCC Live (P1-P6)](#3-pro-tcl--pcc-live-pro_1_pcc_livepy)
- [4. Pro TCL — Heatmap OTP (P7-P9)](#4-pro-tcl--heatmap-otp-pro_2_heatmap_otppy)
- [5. Pro TCL — Correlation (P10-P19)](#5-pro-tcl--correlation-pro_3_correlationpy)
- [6. Pro TCL — Simulateur fréquences (P20-P24)](#6-pro-tcl--simulateur-fréquences-pro_4_simulateurpy)
- [7. Pro TCL — Pipeline Management (P25-P26)](#7-pro-tcl--pipeline-management-pro_6_pipeline_mgmtpy)
- [8. Pro TCL — Model Monitoring (P27-P29)](#8-pro-tcl--model-monitoring-pro_7_model_monitoringpy)
- [9. Élu — Synthèse (E1-E11)](#9-élu--synthèse-elu_1_synthesepy)
- [10. Élu — Bottlenecks (E12-E14)](#10-élu--bottlenecks-elu_2_bottleneckspy)
- [11. Élu — Avant/Après (E15-E16)](#11-élu--avantaprès-elu_3_avant_aprespy)
- [12. Élu — Simulateur aménagement (E17-E19)](#12-élu--simulateur-aménagement-elu_4_simulateurpy)
- [13. Élu — Rapport CM (E20-E22)](#13-élu--rapport-cm-elu_5_rapportpy)
- [14-15. Pages communes (A1, R1)](#14-pages-communes)
- [Soucis non résolus](#-soucis-non-résolus-que-je-ne-peux-pas-traiter-seul)

---

## 0. Widgets transversaux

Présents dans 15/15 pages, définis dans
[`dashboard/components/`](../../dashboard/components/).

### T1 — `render_sidebar_navigation`

| Item | Valeur |
|---|---|
| Code | [`navigation.py`](../../dashboard/components/navigation.py) (sidebar) |
| Logique | Menu latéral listant les 15 pages groupées par persona (Usager/Pro_TCL/Élu) |
| Calculs | Aucun — rendu statique depuis `st.sidebar` |
| Loader | `cached_lyon_addresses_with_coords()` (TTL 600s) |
| Source DB | `referentiel.lieux_lyon` (référentiel, 21 lieux emblématiques) |
| DAG | — (statique) |

### T2 — `render_freshness_badge`

| Item | Valeur |
|---|---|
| Code | [`freshness_badge.py`](../../dashboard/components/freshness_badge.py) |
| Logique | Petit bandeau affichant la prochaine MAJ (auto-refresh 30s/60s/300s selon persona) |
| Calculs | `now() + auto_refresh_interval` |
| Loader | `get_settings().last_ingestion_at` (settings statique) |
| Source DB | — (param système) |
| DAG | — (calcul pur) |

### T3 — `render_data_status_banner`

| Item | Valeur |
|---|---|
| Code | [`data_status.py`](../../dashboard/components/data_status.py) |
| Logique | Bandeau erreur/warning si DB ping échoue (fail loud) |
| Calculs | `SELECT 1` sur PostgreSQL via [`_require_db_or_raise()`](../../src/data/data_loader.py) |
| Loader | Direct (ping) |
| Source DB | PostgreSQL live (connexion `POSTGRES_HOST`) |
| DAG | — (live) |

---

## 1. Usager — Mon trajet ([`Usager_1_Mon_Trajet.py`](../../dashboard/pages/Usager_1_Mon_Trajet.py))

### U1 — `render_search_bar()`

| Item | Valeur |
|---|---|
| Code | [`search_bar.py:39`](../../dashboard/components/widgets/usager/search_bar.py#L39) |
| Logique | Sélecteurs en cascade : catégorie → lieu emblématique |
| Calculs | Filtre `referentiel.lieux_lyon` par catégorie (`type = "monument" \| "transport" \| "quartier"`) |
| Loader | `cached_lyon_addresses_with_coords()` ([`data_cache.py:193`](../../dashboard/components/data_cache.py#L193)) |
| Source DB | `referentiel.lieux_lyon` (21 lieux) |
| DAG | — (référentiel) |

### U2 — `render_mode_comparison()`

| Item | Valeur |
|---|---|
| Code | [`mode_comparison.py:40`](../../dashboard/components/widgets/usager/mode_comparison.py#L40) |
| Logique | Tableau comparatif 3 modes (TC/voiture/vélo) avec winner card |
| Calculs | Score composite = `critere="temps" → duration_min` ou `critere="cout" → duration_min + cost_eur/0.30` |
| Loader | (calculé en amont par la page depuis `session_state["trip_<key>"]`) |
| Source DB | `gold.tarif_modes` (référentiel coût TC) |
| DAG | — (calcul runtime) |

### U3 — `render_mode_summary()`

| Item | Valeur |
|---|---|
| Code | [`mode_summary.py:46`](../../dashboard/components/widgets/usager/mode_summary.py#L46) |
| Logique | Card 1 par mode avec durée, distance, CO₂, calories |
| Calculs | Affiche `calculate_impact(mode, distance_km, duration_min, is_congested)` |
| Loader | `cached_mode_impact()` ([`data_cache.py:436`](../../dashboard/components/data_cache.py#L436)) |
| Source DB | — (formule pure `src/routing/eco_calculator.py`) |
| DAG | — (calcul pur) |

### U4 — `render_weather_widget()`

| Item | Valeur |
|---|---|
| Code | [`weather_widget.py:23`](../../dashboard/components/widgets/usager/weather_widget.py#L23) |
| Logique | Card météo (icône + temp + pluie + vent) + score vélo |
| Calculs | `cycling_score = rain<0.1mm + wind<25km/h` (recommandé), seuils ADEME |
| Loader | `cached_weather_hourly()` ([`data_cache.py:175`](../../dashboard/components/data_cache.py#L175)) |
| Source DB | [`silver.meteo_hourly`](../../src/data/db_query.py) (colonnes `temperature_c, rain_mm, wind_kmh, condition_label`) |
| DAG | [`collect_bronze.py:48`](../../dags/bronze/collect_bronze.py) (Open-Meteo, `*/1h`) |

### U5 — `render_velov_widget()`

| Item | Valeur |
|---|---|
| Code | [`velov_widget.py:38`](../../dashboard/components/widgets/usager/velov_widget.py#L38) |
| Logique | 1 card par station (max 3) avec vélos dispo + prédiction H+1h |
| Calculs | `bikes = station.bikes_available`, `pred = lookup[station_id]` (H+1h), `severity = bikes==0 ? critical : bikes<5 ? warning : ok` |
| Loader | `cached_velov_stations()` + `cached_velov_predictions(horizon_minutes=60)` |
| Source DB | `silver.velov_clean` + `gold.velov_predictions` (H+1h) |
| DAG | `*/5min` (bronze) + `*/1h` (retrain_xgboost_velov) |

### U6 — `render_transit_trip()`

| Item | Valeur |
|---|---|
| Code | [`transit_trip.py:41`](../../dashboard/components/widgets/usager/transit_trip.py#L41) |
| Logique | Affiche itinéraire TC (métro/tram/bus) entre 2 lieux du référentiel |
| Calculs | Pathfinding GTFS, durée + distance + n_transfers + hub |
| Loader | `cached_transit_itinerary()` ([`data_cache.py:380`](../../dashboard/components/data_cache.py#L380)) |
| Source DB | GTFS + GTFS-RT (datasource `bronze.tcl_vehicles` + GTFS statique) |
| DAG | `*/5min` (bronze) |

### U7 — `render_traffic_widget()`

| Item | Valeur |
|---|---|
| Code | [`traffic_widget.py:25`](../../dashboard/components/widgets/usager/traffic_widget.py#L25) |
| Logique | 3 métriques (vitesse moyenne / état congestion / bouchons) + bandeau fraîcheur + card prédiction H+1h |
| Calculs | `avg = AVG(speed_kmh WHERE vitesse_limite_kmh <= 50)`, `level` seuils (35/25/15 km/h) |
| Loader | `cached_traffic()` ([`data_cache.py:40`](../../dashboard/components/data_cache.py#L40)) |
| Source DB | `gold.traffic_features_live` + `gold.trafic_predictions` (H+1h) |
| DAG | `*/10min` (transform) + `*/15min` (inference) |

### U8 — `render_traffic_map_compact()`

| Item | Valeur |
|---|---|
| Code | [`gnn_map.py:237`](../../dashboard/components/widgets/pro_tcl/gnn_map.py#L237) |
| Logique | ScatterplotLayer pydeck (1 point par prédiction, couleur = vitesse) |
| Calculs | `color = _speed_to_color(speed_pred)` ([`gnn_map.py:48`](../../dashboard/components/widgets/pro_tcl/gnn_map.py#L48)) seuils (10/20/35 km/h) |
| Loader | `cached_traffic_predictions_for_map()` |
| Source DB | `gold.trafic_predictions` (H+1h) + `gold.dim_spatial_grid_mapping` (fallback lat/lon) |
| DAG | `*/15min` (dag_inference_xgboost) |

### U9 — `render_velov_trip()`

| Item | Valeur |
|---|---|
| Code | [`velov_trip.py:40`](../../dashboard/components/widgets/usager/velov_trip.py#L40) |
| Logique | Itinéraire Vélov (origin → borne la plus proche → dest) avec marche |
| Calculs | `scoring = 0.5*distance + 0.3*dispo + 0.2*alternatives` |
| Loader | (calcul via `src.routing.pathfinder`) |
| Source DB | `silver.velov_clean` + `referentiel.v_velov_neighbors` (borne alt si VIDE) |
| DAG | `*/5min` (bronze) |

### U10 — `render_itinerary_result()`

| Item | Valeur |
|---|---|
| Code | [`itinerary.py:73`](../../dashboard/components/widgets/usager/itinerary.py#L73) |
| Logique | 3 itinéraires alternatifs via pgRouting pgr_ksp (K=3, Yen) |
| Calculs | `pgr_ksp(orig, dest, 3, cost='length_m + traffic*1.4')` |
| Loader | `cached_car_itinerary()` ([`data_cache.py:393`](../../dashboard/components/data_cache.py#L393)) |
| Source DB | `gold.trafic_predictions` (H+1h) + `osm.ways` (pgRouting réseau routier) |
| DAG | `*/15min` (inference) + `*/15min` (refresh_osm_traffic_costs) |

### U11 — `render_lieux_velov_map()`

| Item | Valeur |
|---|---|
| Code | [`lieux_velov_map.py:46`](../../dashboard/components/widgets/usager/lieux_velov_map.py#L46) |
| Logique | Carte Folium : 21 lieux emblématiques + bornes Vélov < 200m |
| Calculs | JOIN spatial PostGIS `ST_DWithin(lieu, borne, 200m)` |
| Loader | (calcul via `pathfinder_multimodal`) |
| Source DB | `referentiel.lieux_lyon` + `silver.velov_clean` |
| DAG | — (référentiel) |

### U12 — `render_velov_map_compact()`

| Item | Valeur |
|---|---|
| Code | [`velov_map.py:79`](../../dashboard/components/widgets/usager/velov_map.py#L79) |
| Logique | ScatterplotLayer pydeck (toutes les stations Vélov) + tooltip H+1h |
| Calculs | Couleur = `_bikes_to_color(bikes_available)` seuils (0/3/5/10 vélos) |
| Loader | `cached_velov_predictions(60)` (H+1h focus Sprint 22+) |
| Source DB | `silver.velov_clean` + `gold.velov_predictions` (H+1h) |
| DAG | `*/5min` + `*/1h` (retrain) |

---

## 2. Usager — Alertes ([`Usager_2_Alertes.py`](../../dashboard/pages/Usager_2_Alertes.py))

### U13 — `render_alert_card(alert)`

| Item | Valeur |
|---|---|
| Code | [`alert_card.py:10`](../../dashboard/components/widgets/usager/alert_card.py#L10) |
| Logique | Card HTML par alerte (line_ref, title, action) |
| Calculs | Aucun — rendu direct |
| Loader | `cached_recent_alerts(hours=6, limit=30)` (côté page) |
| Source DB | `silver.chantiers_actifs` + alertes dynamiques |
| DAG | `*/5min` (transform) + 1×/jour (chantiers) |

### U14 — `render_alert_timeline(alerts)`

| Item | Valeur |
|---|---|
| Code | [`alert_timeline.py:12`](../../dashboard/components/widgets/usager/alert_timeline.py#L12) |
| Logique | Frise chronologique verticale (cards triées par timestamp desc) |
| Calculs | `sorted(alerts, key=lambda a: a.timestamp, reverse=True)` |
| Loader | `cached_recent_alerts()` (côté page) |
| Source DB | idem U13 |
| DAG | idem U13 |

### U15 — `render_alert_settings()`

| Item | Valeur |
|---|---|
| Code | [`alert_settings.py:8`](../../dashboard/components/widgets/usager/alert_settings.py#L8) |
| Logique | Form Streamlit : choix type alertes + fenêtre temporelle |
| Calculs | UI pur |
| Loader | — |
| Source DB | — |
| DAG | — (UI) |

### U16 — `st.metric ×3` (page-level)

| Item | Valeur |
|---|---|
| Code | [`Usager_2_Alertes.py:46`](../../dashboard/pages/Usager_2_Alertes.py#L46) |
| Logique | 3 colonnes : Alertes actives / Critiques / Warnings |
| Calculs | `n_critical = sum(1 for a in alerts if a.severity == "critical")` |
| Loader | `cached_recent_alerts()` |
| Source DB | idem U13 |
| DAG | idem U13 |

---

## 3. Pro TCL — PCC Live ([`Pro_1_PCC_Live.py`](../../dashboard/pages/Pro_1_PCC_Live.py))

### P1 — `render_alert_ticker()`

| Item | Valeur |
|---|---|
| Code | [`alert_ticker.py:15`](../../dashboard/components/widgets/pro_tcl/alert_ticker.py#L15) |
| Logique | Ticker horizontal des alertes (24h) |
| Calculs | `alerts[:10]` (top 10) |
| Loader | `cached_recent_alerts(hours=24, limit=10)` |
| Source DB | `silver.chantiers_actifs` + alertes dynamiques |
| DAG | `*/5min` |

### P2 — `render_network_map()` (Bus GPS)

| Item | Valeur |
|---|---|
| Code | [`network_map.py:36`](../../dashboard/components/widgets/pro_tcl/network_map.py#L36) |
| Logique | ScatterplotLayer pydeck des bus TCL (1 point par bus, tooltip = line/direction) |
| Calculs | `view_state = (lat=45.76, lon=4.84, zoom=11)` |
| Loader | `cached_buses_positions(limit=200)` |
| Source DB | `bronze.tcl_vehicles` → `silver.tcl_vehicles_clean` |
| DAG | `*/5min` (transform_bronze_to_silver) |

### P3 — `render_traffic_map()` (Charge trafic)

| Item | Valeur |
|---|---|
| Code | [`gnn_map.py:167`](../../dashboard/components/widgets/pro_tcl/gnn_map.py#L167) |
| Logique | Carte pydeck avec sélecteur horizon (focus H+1h) |
| Calculs | idem U8 (couleur par vitesse prédite) |
| Loader | idem U8 |
| Source DB | idem U8 |
| DAG | `*/15min` (inference) |

### P4 — Alertes détail (page-level)

| Item | Valeur |
|---|---|
| Code | [`Pro_1_PCC_Live.py:71`](../../dashboard/pages/Pro_1_PCC_Live.py#L71) |
| Logique | Cards HTML alertes (ligne ref, title, action) |
| Calculs | `clean_line_label(line_ref)` (helper db_query pour ActIV:Line:: → "L66") |
| Loader | `cached_recent_alerts(hours=24, limit=10)` |
| Source DB | idem U13 |
| DAG | `*/5min` |

### P5 — `render_otp_heatmap_mini()`

| Item | Valeur |
|---|---|
| Code | [`otp_heatmap.py:178`](../../dashboard/components/widgets/pro_tcl/otp_heatmap.py#L178) |
| Logique | Heatmap Plotly `go.Heatmap` (lignes × heures) |
| Calculs | `z = pivot(lines × hours, values=otp_pct)` (depuis `gold.mv_otp_heatmap`) |
| Loader | `cached_otp_heatmap_data()` |
| Source DB | `gold.mv_otp_heatmap` (155 lignes × 24h × N jours) |
| DAG | quotidien 05h00 (refresh_lieux_calendrier) |

### P6 — `render_line_kpis()` + Top bottlenecks (page-level)

| Item | Valeur |
|---|---|
| Code | [`line_kpis.py:61`](../../dashboard/components/widgets/pro_tcl/line_kpis.py#L61) |
| Logique | Tableau Streamlit (155 lignes TCL) avec tri + slider top N + cards par ligne |
| Calculs | KPIs = `otp_pct, avg_delay_min, frequency_min, load_pct` (vue matérialisée) |
| Loader | `cached_line_kpis()` + `cached_bottlenecks_top()` |
| Source DB | `gold.mv_line_kpis_live` + vue bottlenecks (vue calculée runtime) |
| DAG | `*/5min` (transform) + quotidien 05h00 (refresh) |

---

## 4. Pro TCL — Heatmap OTP ([`Pro_2_Heatmap_OTP.py`](../../dashboard/pages/Pro_2_Heatmap_OTP.py))

### P7 — `render_otp_filters()`

| Item | Valeur |
|---|---|
| Code | [`otp_filters.py:8`](../../dashboard/components/widgets/pro_tcl/otp_filters.py#L8) |
| Logique | Sélecteur période (Aujourd'hui / 7j / 30j) + slider top N |
| Calculs | `days = {"Aujourd'hui": 1, "7 derniers jours": 7, "30 derniers jours": 30}` |
| Loader | — |
| Source DB | — (filtre client-side) |
| DAG | — (UI) |

### P8 — `render_otp_heatmap()`

| Item | Valeur |
|---|---|
| Code | [`otp_heatmap.py:96`](../../dashboard/components/widgets/pro_tcl/otp_heatmap.py#L96) |
| Logique | Heatmap Plotly (lignes × heures, colorbar % OTP) |
| Calculs | idem P5 + filtre période + top N pires lignes |
| Loader | `cached_otp_heatmap_data()` |
| Source DB | `gold.mv_otp_heatmap` |
| DAG | quotidien 05h00 |

### P9 — `render_line_comparison()`

| Item | Valeur |
|---|---|
| Code | [`line_comparison.py:16`](../../dashboard/components/widgets/pro_tcl/line_comparison.py#L16) |
| Logique | Dataframe Streamlit comparant N lignes sélectionnées |
| Calculs | Filtre `line_kpis` par `line_ids` sélectionnés |
| Loader | `cached_line_kpis(line_ids=tuple)` |
| Source DB | `gold.mv_line_kpis_live` |
| DAG | `*/5min` + quotidien 05h00 |

---

## 5. Pro TCL — Correlation ([`Pro_3_Correlation.py`](../../dashboard/pages/Pro_3_Correlation.py))

**Sprint 22+** : 9 sections lourdes dans des [`st.tabs`](../../dashboard/components/widgets/common) (4 tabs : "Bus × Trafic", "Spatial & TomTom", "Multimodal", "Propagation").

### P10 — `render_line_selector()`

| Item | Valeur |
|---|---|
| Code | [`line_selector.py:14`](../../dashboard/components/widgets/pro_tcl/line_selector.py#L14) |
| Logique | Multiselect des 10 lignes TCL emblématiques |
| Calculs | UI pur |
| Loader | `cached_tcl_lines()` |
| Source DB | `src/data/tcl_lines.py` (référentiel statique 10 lignes) |
| DAG | — (statique) |

### P11 — `render_correlation_matrix()`

| Item | Valeur |
|---|---|
| Code | [`correlation_matrix.py:60`](../../dashboard/components/widgets/pro_tcl/correlation_matrix.py#L60) |
| Logique | Matrice Pearson retards bus × vitesse trafic par segment |
| Calculs | `corr = pearson(delay_seconds, speed_kmh)` par segment_id |
| Loader | `cached_infra_bottlenecks(top=500)` |
| Source DB | `gold.infrastructure_bottlenecks` (vue calculée) |
| DAG | `*/5min` (transform) |

### P12 — `render_segment_table()`

| Item | Valeur |
|---|---|
| Code | [`segment_table.py:26`](../../dashboard/components/widgets/pro_tcl/segment_table.py#L26) |
| Logique | Dataframe Streamlit (segments triés par retard) |
| Calculs | Filtre `cached_infra_bottlenecks(top=500)` par `line_id` |
| Loader | idem P11 |
| Source DB | idem P11 |
| DAG | idem P11 |

### P13 — `render_cause_analysis()`

| Item | Valeur |
|---|---|
| Code | [`cause_analysis.py:10`](../../dashboard/components/widgets/pro_tcl/cause_analysis.py#L10) |
| Logique | Diagnostic visuel (bus delayed + traffic jammed = "infra") |
| Calculs | `diagnosis = "infra" if delay>120s AND speed<25 else "ok"` |
| Loader | (segment passé en arg) |
| Source DB | idem P11 |
| DAG | idem P11 |

### P14 — `render_bus_traffic_spatial()` (Tab 2, button-gate)

| Item | Valeur |
|---|---|
| Code | [`bus_traffic_spatial.py:198`](../../dashboard/components/widgets/pro_tcl/bus_traffic_spatial.py#L198) |
| Logique | Scatter retard bus × vitesse trafic **par zone 0.001° (~100 m)** |
| Calculs | `JOIN spatial ST_DWithin(bus, traffic, 0.001°)` (100m) — corrige le bottleneck global |
| Loader | `cached_bus_traffic_spatial()` + `cached_bus_traffic_spatial_diagnosis_counts()` |
| Source DB | `gold.mv_bus_traffic_spatial` (migration 018) |
| DAG | `*/15min` (Sprint 15+ Axe 3) |

### P15 — `render_coherence_scatter()` (Tab 2, button-gate)

| Item | Valeur |
|---|---|
| Code | [`coherence_scatter.py:269`](../../dashboard/components/widgets/pro_tcl/coherence_scatter.py#L269) |
| Logique | Scatter TomTom vs Grand Lyon (cross-validation) |
| Calculs | `delta_kmh = tomtom_speed - gl_speed`, `status = ok\|minor_drift\|drift\|no_data` |
| Loader | `cached_tomtom_coherence()` + `cached_tomtom_gl_drift()` |
| Source DB | `gold.v_coherence_tomtom_vs_grandlyon` (migration 14) + `gold.v_tomtom_gl_drift` |
| DAG | `*/15min` (TomTom) |

### P16 — `render_multimodal_heatmap()` (Tab 3, button-gate)

| Item | Valeur |
|---|---|
| Code | [`multimodal_heatmap.py:282`](../../dashboard/components/widgets/pro_tcl/multimodal_heatmap.py#L282) |
| Logique | Carte chaleur 0.01° (~1 km) fusionnant trafic + TCL + Vélov + météo |
| Calculs | `score 0-10 = weighted(traffic, tcl, velov, meteo) per cell` |
| Loader | `cached_multimodal_grid(limit=5000)` + `cached_multimodal_grid_diagnosis_counts()` |
| Source DB | `gold.mv_multimodal_grid` (migration 017) |
| DAG | `*/10min` (Sprint 15+ Axe 1) |

### P17 — `render_meteo_impact()` (Tab 3, button-gate)

| Item | Valeur |
|---|---|
| Code | [`meteo_impact.py:242`](../../dashboard/components/widgets/pro_tcl/meteo_impact.py#L242) |
| Logique | Tableau 5 bandes météo × 3 modes (delta vs "fair") |
| Calculs | `delta = avg(fair) - avg(bande_i)` par (mode, bande) |
| Loader | `cached_meteo_impact()` |
| Source DB | `gold.mv_meteo_impact` (migration 022) |
| DAG | quotidien 04h30 |

### P18 — `render_modal_shift_alert()` (Tab 3, button-gate)

| Item | Valeur |
|---|---|
| Code | [`modal_shift_alert.py:190`](../../dashboard/components/widgets/pro_tcl/modal_shift_alert.py#L190) |
| Logique | Alerte report modal Vélov → TC (z-score vélos dispos) |
| Calculs | `z_score = (bikes - mean_7j) / std_7j`, alerte si `z < -2` |
| Loader | `cached_velov_transit_coupling()` + `cached_velov_transit_coupling_summary()` |
| Source DB | `gold.mv_velov_transit_coupling` (migration 023) |
| DAG | `*/15min` (refresh_velov_transit_coupling) |

### P19 — `render_propagation_map()` (Tab 4, button-gate)

| Item | Valeur |
|---|---|
| Code | [`propagation_map.py:870`](../../dashboard/components/widgets/pro_tcl/propagation_map.py#L870) |
| Logique | Carte Folium AntPath animation (propagation congestion entre paires) |
| Calculs | `corr = pearson(speed_i, speed_j lag 5min)` sur 6h × 5min, direction = argmax(\|r\|) |
| Loader | `cached_congestion_propagation_pairs()` + `cached_traffic_speeds_for_propagation(hours=6)` |
| Source DB | `gold.mv_congestion_propagation_pairs` (migration 024 v3) |
| DAG | `*/30min` (Sprint 17 Axe 2) |

---

## 6. Pro TCL — Simulateur fréquences ([`Pro_4_Simulateur.py`](../../dashboard/pages/Pro_4_Simulateur.py))

### P20 — `render_line_selector()`

→ voir P10.

### P21 — `st.metric ×4` (page-level)

| Item | Valeur |
|---|---|
| Code | [`Pro_4_Simulateur.py:48`](../../dashboard/pages/Pro_4_Simulateur.py#L48) |
| Logique | 4 KPIs état actuel de la ligne sélectionnée |
| Calculs | `kpis = cached_line_kpis().get(target_line, {})` |
| Loader | `cached_line_kpis()` |
| Source DB | `gold.mv_line_kpis_live` |
| DAG | `*/5min` + quotidien 05h00 |

### P22 — `render_frequency_slider()`

| Item | Valeur |
|---|---|
| Code | [`frequency_slider.py:10`](../../dashboard/components/widgets/pro_tcl/frequency_slider.py#L10) |
| Logique | Slider ajout/retrait bus + sélecteur période |
| Calculs | UI pur |
| Loader | — |
| Source DB | — |
| DAG | — (UI) |

### P23 — `render_otp_projection()`

| Item | Valeur |
|---|---|
| Code | [`otp_projection.py:10`](../../dashboard/components/widgets/pro_tcl/otp_projection.py#L10) |
| Logique | 3 métriques (OTP actuel, projeté, IC 95%) |
| Calculs | `new_otp = min(98, max(60, base_otp + buses_added * 2.5))` (heuristique simple) |
| Loader | (calcul pur) |
| Source DB | — |
| DAG | — (UI) |

### P24 — `render_before_after_chart()`

| Item | Valeur |
|---|---|
| Code | [`before_after_chart.py:12`](../../dashboard/components/widgets/pro_tcl/before_after_chart.py#L12) |
| Logique | Bar chart Plotly avant/après OTP |
| Calculs | `go.Bar(x=["Avant", "Après"], y=[base, new])` |
| Loader | (calcul pur) |
| Source DB | — |
| DAG | — (UI) |

---

## 7. Pro TCL — Pipeline Management ([`Pro_6_Pipeline_Mgmt.py`](../../dashboard/pages/Pro_6_Pipeline_Mgmt.py))

### P25 — `render_source_health_monitor()`

| Item | Valeur |
|---|---|
| Code | [`source_health_monitor.py:107`](../../dashboard/components/widgets/pro_tcl/source_health_monitor.py#L107) |
| Logique | Indicator Plotly par source (Trafic/TCL/Vélov/Météo) + data completeness |
| Calculs | `health = nb_rows_in_last_1h / nb_expected_rows` (seuils 0.5/0.9) |
| Loader | `cached_source_health()` + `cached_data_completeness()` |
| Source DB | `gold.v_source_health` + `gold.v_data_completeness` (migration 021) |
| DAG | quotidien 04h15 (maintenance DAG) |

### P26 — `render_pipeline_management_page()`

| Item | Valeur |
|---|---|
| Code | [`pipeline_management.py:402`](../../dashboard/components/widgets/pro_tcl/pipeline_management.py#L402) |
| Logique | Liste DAGs Airflow (REST API) + statut + health panel + data freshness + alerts feed |
| Calculs | Appels Airflow REST API (state, duration) |
| Loader | Appels directs à l'API Airflow |
| Source DB | Airflow metadata DB |
| DAG | live (REST API) |

---

## 8. Pro TCL — Model Monitoring ([`Pro_7_Model_Monitoring.py`](../../dashboard/pages/Pro_7_Model_Monitoring.py))

**Toggle** : `LYONFLOW_DASHBOARD_MODEL_MONITORING=true` requis.

### P27 — `render_model_monitoring_page()`

| Item | Valeur |
|---|---|
| Code | [`model_monitoring.py:726`](../../dashboard/components/widgets/pro_tcl/model_monitoring.py#L726) |
| Logique | Page maître : 8 sections (registry, status, metrics, training, drift, velov, DQ, panel) |
| Calculs | MLflow runs + agrégats |
| Loader | `cached_mlflow_models()` + `cached_mlflow_experiment_summary()` + `cached_xgb_accuracy_summary()` + `cached_xgb_vs_tomtom()` |
| Source DB | MLflow Tracking + `gold.predictions_vs_actuals` |
| DAG | `*/30min` (backtest) + quotidien 05h30 (drift) |

### P28 — `render_gnn_map_section()`

| Item | Valeur |
|---|---|
| Code | [`gnn_map.py:266`](../../dashboard/components/widgets/pro_tcl/gnn_map.py#L266) |
| Logique | Bandeau status + carte GNN (toggle `LYONFLOW_DASHBOARD_GNN_MAP`) |
| Calculs | idem P3 |
| Loader | idem P3 + `cached_spatial_mapping()` |
| Source DB | idem P3 + `gold.dim_spatial_grid_mapping` |
| DAG | idem P3 |

### P29 — `render_backtest_dashboard()` (button-gate)

| Item | Valeur |
|---|---|
| Code | [`backtest_dashboard.py:210`](../../dashboard/components/widgets/pro_tcl/backtest_dashboard.py#L210) |
| Logique | 4 KPIs + scatter XGBoost vs TomTom + MAE + distribution + top 10 pires |
| Calculs | `MAE = AVG(\|predicted - actual\|)` sur 7j |
| Loader | `cached_xgb_vs_tomtom()` + `cached_predictions_vs_actuals()` |
| Source DB | `gold.mv_xgb_vs_tomtom` (migration 020) + `gold.predictions_vs_actuals` |
| DAG | `*/30min` |

---

## 9. Élu — Synthèse ([`Elu_1_Synthese.py`](../../dashboard/pages/Elu_1_Synthese.py))

**Sprint 22+** : sections lourdes dans [`st.expander`](../../dashboard/components/widgets/common).

### E1 — `render_network_health_gauge()`

| Item | Valeur |
|---|---|
| Code | [`network_health_gauge.py:184`](../../dashboard/components/widgets/elu/network_health_gauge.py#L184) |
| Logique | Bandeau jauge principale 0-100 + 4 sous-jauges (% congestion, % TCL delayed, % Vélov vide, météo penalty) + sparkline 24h |
| Calculs | SQL: `SELECT * FROM gold.fn_network_health_score()` ([migration 019](../../scripts/sql/migration_019_network_health.sql)) — score = `weighted(100 - pct_congestion, 100 - pct_tcl_delayed, 100 - pct_velov_empty, 100 - meteo_penalty)` avec redistribution poids si source indispo |
| Loader | `cached_network_health_score()` ([`data_cache.py:329`](../../dashboard/components/data_cache.py#L329)) + sparkline via `gold.network_health_history` (migration 030) |
| Source DB | `gold.fn_network_health_score()` (fonction SQL runtime) + `gold.network_health_history` |
| DAG | runtime (fonction) + `*/15min` (record_network_health DAG) |

### E2 — `render_drift_status_badge()`

| Item | Valeur |
|---|---|
| Code | [`drift_status_badge.py:115`](../../dashboard/components/widgets/elu/drift_status_badge.py#L115) |
| Logique | Bandeau compact 1 ligne (modèle stable / attention / drift détecté) |
| Calculs | `drift = abs(mae_24h - mae_7j) / mae_7j` (seuils 5%/15%) |
| Loader | `cached_xgb_accuracy_summary(hours=24)` |
| Source DB | `gold.v_xgb_accuracy_summary` (vue calculée 7j glissants) |
| DAG | quotidien 05h30 (daily_drift_report) |

### E3 — `render_data_quality_badge()`

| Item | Valeur |
|---|---|
| Code | [`data_quality_badge.py:63`](../../dashboard/components/widgets/elu/data_quality_badge.py#L63) |
| Logique | Bandeau compact (sources healthy / stale / dead + score global) |
| Calculs | `health = count(avail) / count(total) * 100` |
| Loader | `cached_source_health()` |
| Source DB | `gold.v_source_health` (migration 021) |
| DAG | quotidien 04h15 |

### E4 — `render_data_quality_detail()`

| Item | Valeur |
|---|---|
| Code | [`data_quality_detail.py:197`](../../dashboard/components/widgets/elu/data_quality_detail.py#L197) |
| Logique | Drill-down data bounds (speed, null ratio, doublons, volume) |
| Calculs | 6 checks × 4 sources = 24 résultats (gold.data_quality_log) |
| Loader | `cached_quality_report(limit=200)` |
| Source DB | `gold.data_quality_log` (migration 025, append-only) |
| DAG | quotidien 04h15 |

### E5 — `render_executive_summary()`

| Item | Valeur |
|---|---|
| Code | [`executive_summary.py:14`](../../dashboard/components/widgets/elu/executive_summary.py#L14) |
| Logique | Bloc narratif markdown (synthèse auto-générée) |
| Calculs | Template Jinja + KPIs agrégés |
| Loader | `cached_elu_kpis_dict()` |
| Source DB | vue calculée runtime |
| DAG | runtime |

### E6 — `render_kpi_cards()`

| Item | Valeur |
|---|---|
| Code | [`kpi_cards.py:15`](../../dashboard/components/widgets/elu/kpi_cards.py#L15) |
| Logique | 5 cards KPI (vitesse moyenne, OTP, charge, ROI, etc.) |
| Calculs | KPIs agrégés + delta YTD |
| Loader | `cached_elu_kpis_dict()` + `cached_kpis_12_months()` |
| Source DB | `gold.mv_kpis_12_months` + vue calculée |
| DAG | LIVE + 1×/jour (archive silver-to-minio) |

### E7 — `render_traffic_map_compact()` (expander)

→ voir U8.

### E8 — `render_trend_chart()` (button-gate, expander)

| Item | Valeur |
|---|---|
| Code | [`trend_chart.py:17`](../../dashboard/components/widgets/elu/trend_chart.py#L17) |
| Logique | Scatter Plotly (tendance 12 mois d'un KPI) |
| Calculs | `x=month, y=value` depuis `gold.mv_kpis_12_months` |
| Loader | `cached_elu_kpis_dict()` |
| Source DB | `gold.mv_kpis_12_months` |
| DAG | 1×/jour |

### E9 — `render_top_decisions(n=3)`

| Item | Valeur |
|---|---|
| Code | [`top_decisions.py:14`](../../dashboard/components/widgets/elu/top_decisions.py#L14) |
| Logique | Top N bottlenecks triés par ROI |
| Calculs | `sort by roi_mois ASC, take first N` |
| Loader | `cached_bottlenecks_top()` |
| Source DB | vue bottlenecks runtime |
| DAG | `*/5min` |

### E10 — `render_news_section()` (expander)

| Item | Valeur |
|---|---|
| Code | [`news_section.py:10`](../../dashboard/components/widgets/elu/news_section.py#L10) |
| Logique | 4 cards "À annoncer" (contenu statique hardcodé dans le widget) |
| Calculs | Aucun — texte statique |
| Loader | — |
| Source DB | — (statique) |
| DAG | — (statique) |

### E11 — `render_pdf_generator()` (expander)

| Item | Valeur |
|---|---|
| Code | [`pdf_generator.py:14`](../../dashboard/components/widgets/elu/pdf_generator.py#L14) |
| Logique | Bouton "Générer PDF" → WeasyPrint HTML→PDF (fallback reportlab) |
| Calculs | `render_html_template(sections)` + `generate_pdf(html)` |
| Loader | (UI action) |
| Source DB | — (sections passées par la page) |
| DAG | — (UI) |

---

## 10. Élu — Bottlenecks ([`Elu_2_Bottlenecks.py`](../../dashboard/pages/Elu_2_Bottlenecks.py))

### E12 — `render_bottleneck_map()`

| Item | Valeur |
|---|---|
| Code | [`bottleneck_map.py:15`](../../dashboard/components/widgets/elu/bottleneck_map.py#L15) |
| Logique | Carte Folium : 1 CircleMarker par bottleneck (rayon × voyageurs/jour) |
| Calculs | `radius = sqrt(voyageurs_jour) * scale` |
| Loader | `cached_bottlenecks_top()` |
| Source DB | vue bottlenecks runtime |
| DAG | `*/5min` |

### E13 — `render_bottleneck_ranking()`

| Item | Valeur |
|---|---|
| Code | [`bottleneck_ranking.py:15`](../../dashboard/components/widgets/elu/bottleneck_ranking.py#L15) |
| Logique | Dataframe Streamlit (bottlenecks triés par ROI) |
| Calculs | idem E9 + colonnes explicites |
| Loader | idem E9 |
| Source DB | idem E9 |
| DAG | `*/5min` |

### E14 — `render_roi_calculator()`

| Item | Valeur |
|---|---|
| Code | [`roi_calculator.py:14`](../../dashboard/components/widgets/elu/roi_calculator.py#L14) |
| Logique | Sliders interactifs (investissement, voyageurs/jour) → ROI mois |
| Calculs | `ROI = (gain_min * voyageurs * 250j * 0.30€/min) / cout_M_€ * 1e6 / 1e6` |
| Loader | (calcul pur) |
| Source DB | — (input utilisateur) |
| DAG | — (UI) |

---

## 11. Élu — Avant/Après ([`Elu_3_Avant_Apres.py`](../../dashboard/pages/Elu_3_Avant_Apres.py))

### E15 — `render_project_selector()`

| Item | Valeur |
|---|---|
| Code | [`project_selector.py:14`](../../dashboard/components/widgets/elu/project_selector.py#L14) |
| Logique | Sélecteur aménagement passé (historique) |
| Calculs | `df.iloc[selection_idx]` |
| Loader | `cached_amenagements_passes(limit=50)` |
| Source DB | `gold.amenagements_history` (référentiel) |
| DAG | — (référentiel) |

### E16 — `render_delta_kpis()`

| Item | Valeur |
|---|---|
| Code | [`delta_kpis.py:10`](../../dashboard/components/widgets/elu/delta_kpis.py#L10) |
| Logique | 2 lignes cards (AVANT / APRÈS) + delta |
| Calculs | `delta = apres[k] - avant[k]` par clé |
| Loader | (avant/après passés) |
| Source DB | — (données passées) |
| DAG | — (UI) |

---

## 12. Élu — Simulateur aménagement ([`Elu_4_Simulateur.py`](../../dashboard/pages/Elu_4_Simulateur.py))

### E17 — `render_map_painter()`

| Item | Valeur |
|---|---|
| Code | [`map_painter.py:20`](../../dashboard/components/widgets/elu/map_painter.py#L20) |
| Logique | Carte Folium + sélection zone (futur MapboxDraw Sprint 5) |
| Calculs | UI pur |
| Loader | `cached_bottlenecks_top()` (fallback) |
| Source DB | vue bottlenecks runtime |
| DAG | `*/5min` |

### E18 — `render_impact_projection()`

| Item | Valeur |
|---|---|
| Code | [`impact_projection.py:8`](../../dashboard/components/widgets/elu/impact_projection.py#L8) |
| Logique | Projection impact aménagement (voyageurs, gain temps) |
| Calculs | heuristique simple (couloir bus = +5% OTP, piste cyclable = -3% trafic) |
| Loader | (zone passée) |
| Source DB | — (heuristique) |
| DAG | — (UI) |

### E19 — `render_cost_estimate()`

| Item | Valeur |
|---|---|
| Code | [`cost_estimate.py:8`](../../dashboard/components/widgets/elu/cost_estimate.py#L8) |
| Logique | Estimation coût aménagement (M€) |
| Calculs | heuristique (longueur × largeur × coût unitaire) |
| Loader | (zone passée) |
| Source DB | — (heuristique) |
| DAG | — (UI) |

---

## 13. Élu — Rapport CM ([`Elu_5_Rapport.py`](../../dashboard/pages/Elu_5_Rapport.py))

### E20 — `render_template_selector()`

| Item | Valeur |
|---|---|
| Code | [`template_selector.py:27`](../../dashboard/components/widgets/elu/template_selector.py#L27) |
| Logique | Sélecteur template rapport (synthèse/rapport CM/technique) |
| Calculs | UI pur |
| Loader | — |
| Source DB | — (templates statiques) |
| DAG | — (UI) |

### E21 — `render_slide_builder()`

| Item | Valeur |
|---|---|
| Code | [`slide_builder.py:8`](../../dashboard/components/widgets/elu/slide_builder.py#L8) |
| Logique | Multi-checkboxes (slides à inclure) |
| Calculs | UI pur |
| Loader | — |
| Source DB | — (UI) |
| DAG | — (UI) |

### E22 — `render_pdf_generator()`

→ voir E11.

---

## 14. Pages communes

### A1 — [`A_Propos.py`](../../dashboard/pages/A_Propos.py) (Accueil)

| Item | Valeur |
|---|---|
| Logique | Page markdown statique (présentation projet, 4 piliers ML, 3 personas, stack, auteur) |
| Calculs | Aucun — texte statique |
| Source DB | — (statique) |
| DAG | — (statique) |

### R1 — [`9_RGPD_Conformite.py`](../../dashboard/pages/9_RGPD_Conformite.py) (RGPD)

| Item | Valeur |
|---|---|
| Logique | Page markdown (données traitées, PII, cookies, droits) |
| Calculs | Aucun — texte statique |
| Source DB | — (statique, Sprint 11+ cleanup a viré "Activité RGPD" + "DPO") |
| DAG | — (statique) |

---

## ⚠️ Soucis non résolus que je ne peux pas traiter seul

Patrice, voici la liste honnête de ce que **je ne peux pas vérifier seul** (besoin d'un accès live ou d'un SSH) :

### 1. **État live MLflow (serveur + runs)**
   - Le serveur MLflow tourne-t-il sur le VPS ? (docker ps lyonflow-mlflow)
   - Combien de runs loggés dans `xgboost_speed` et `xgboost_velov` ces 7 derniers jours ?
   - Le `dag_daily_speed_train` a-t-il tourné cette nuit ?
   - Les `model_name` sont-ils bien versionnés (Production/Staging) ?
   - **Action** : SSH + commandes `mlflow.search_runs()`

### 2. **État live des DAGs Airflow**
   - Tous les DAGs schedulés tournent-ils ? (last run, last duration, failed)
   - Le DAG `dag_inference_xgboost` a-t-il tourné il y a < 15 min ?
   - Le DAG `record_network_health` a-t-il tourné il y a < 15 min (pour la sparkline 24h) ?
   - Le DAG `refresh_osm_traffic_costs` a-t-il tourné il y a < 15 min (pgrouting trafic) ?
   - **Action** : SSH + `airflow dags list` + `airflow dags state <dag> <date>`

### 3. **Volumes live des tables DB**
   - `gold.trafic_predictions` : combien de rows pour `horizon_h = 1` ?
   - `gold.velov_predictions` : combien de rows pour `horizon_minutes = 60` ?
   - `gold.traffic_features_live` : combien de rows dans les 2 dernières heures ?
   - `gold.network_health_history` : combien de rows (pour que la sparkline fonctionne) ?
   - **Action** : SSH + `psql` + `SELECT COUNT(*), MAX(<ts_col>) FROM <table>`

### 4. **Doutes / pas vérifié**

| # | Point | Raison du doute |
|---|-------|-----------------|
| D1 | `gold.velov_predictions` schema — la table accepte-t-elle encore `horizon_minutes = 30` ? J'ai viré le code mais pas vérifié si la table SQL a une contrainte CHECK qui rejetterait. | Pas vérifié la migration `create_velov_predictions.sql` |
| D2 | `_is_congested_from_speed` alias rétro-compat (`_is_congested_from_speed = is_congested_from_speed` ligne eco_calculator.py) — doit être viré Sprint 23+ | Pas d'urgence, mais foot-gun |
| D3 | `_minutes_to_hours` (db_query.py) n'est plus utilisé runtime — la fonction peut être virée | Dead code potentiel |
| D4 | `gold.network_health_history` (migration 030) — la sparkline 24h lit cette table, mais est-elle alimentée ? | À vérifier sur VPS |
| D5 | `gold.fn_network_health_score()` — la fonction SQL a-t-elle les 4 sous-scores (`traffic_score, tcl_score, velov_score, meteo_score`) ? Le DAG `record_network_health` log `NULL` pour ces 4 colonnes (cf. docstring DAG) | Migration 031 TODO dans le code |
| D6 | `retrain_xgboost_speed` hourly :25 + `dag_daily_speed_train` 03h00 — DOUBLE retraining pour H+1h. Toggle `LYONFLOW_XGBOOST_TRAINING` permet de skip le 1er mais par défaut les 2 tournent | Gaspillage CPU |

### 5. **Bug latent que j'ai repéré en lisant le code**
   - `dashboard/components/data_cache.py:431` dit "TTL_SLOW largement suffisant : la MV ne change qu'une fois/jour" mais `cached_meteo_impact` (ligne 425) a `ttl=TTL_FAST` (60s) → incohérence. À fixer.
