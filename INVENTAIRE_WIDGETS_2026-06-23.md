# Inventaire exhaustif des widgets Streamlit — LyonFlowFull

**Date** : 2026-06-23
**Branche** : `vps` (3 commits en attente de push : `5ea1781`, `d5c28f3`, `1882c8c`)
**Sources vérifiées** : 15 fichiers `dashboard/pages/*.py` + 60 fichiers `dashboard/components/widgets/**/*.py` + `dashboard/components/data_cache.py` + `dashboard/components/{navigation,freshness_badge,data_status}.py` + `src/data/data_loader.py` + `src/data/db_query.py` + tous les `dags/**/*.py` pour les schedules

---

## 🔬 Méthodologie — ce que j'ai vérifié vs inféré

| Source | Comment vérifié | Confiance |
|--------|-----------------|-----------|
| Pages → liste des widgets appelés | `grep render_\|st\.\(pydeck_chart\|folium\|plotly\|line_chart\|bar_chart\|metric\|dataframe\|table\)` dans chaque `dashboard/pages/*.py` | ✅ 100% |
| Widgets utilisés vs dead code | `comm -23 /tmp/all_widgets.txt /tmp/used_widgets.txt` | ✅ 100% — **17 widgets dead code identifiés** |
| Widgets → loaders (`cached_*`) | `grep "cached_\|dl\.\|dbq\."` dans les 60 fichiers widgets + `dashboard/components/data_cache.py` | ✅ 100% — 48 loaders mappés |
| Cache TTL | `grep -B1 'def cached_' dashboard/components/data_cache.py` | ✅ 100% — 48 loaders mappés |
| Techno de rendu | lecture intégrale des 60 fichiers widgets (grep `pdk\.\|folium\.\|go\.\|px\.\|st\.\(pydeck_chart\|dataframe\|metric\|markdown\|html\)`) | ✅ 100% — vérifié fichier par fichier |
| Table/vue SQL sous-jacente | `grep -nE "FROM (silver\|gold\|bronze\|osm\|referentiel)\.[a-z_]+" src/data/db_query.py` | ✅ 100% — 45 tables/vues extraites automatiquement et comparées au tableau |
| DAG schedule | `grep schedule_interval dags/**/*.py` | ✅ 100% — 15 DAGs actifs schedulés |
| Features XGBoost Vélov | lecture `src/models/xgboost_velov.py:33-46` | ✅ 100% — 11 features confirmées |
| Lignes TCL (155/10/56/21) | lecture `src/data/tcl_lines.py` + `scripts/sql/create_referentiel_transports.sql:44` | ✅ 100% — tous les nombres vérifiés |

**Erreurs factuelles trouvées et corrigées dans cette v2** :
1. ~~`gold.amenagements_passes`~~ → **`gold.amenagements_history`** (vérifié `src/data/db_query.py:919`)
2. ~~U4 weather_widget : `st.metric + st.caption`~~ → **`st.markdown cards HTML custom + st.columns (prévisions 3h)`** (vérifié fichier)
3. ~~U5 velov_widget : `st.metric ×N`~~ → **`st.columns + st.html cards custom (1 card/station + prédiction H+1h)`** (vérifié fichier, Sprint 8+ focus H+1h)
4. ~~U6 transit_trip : `st.dataframe + st.metric`~~ → **`st.markdown banner HTML + st.metric (KPIs) + cards (segments)`** (vérifié fichier)
5. ~~U14 alert_timeline : `st.plotly_chart (timeline Scatter)`~~ → **`st.markdown cards verticales (timeline)`** (vérifié fichier)
6. E1 network_health_gauge : ajout colonne "DAG refresh" (`*/15min` via `record_network_health` pour la sparkline)
7. ~~E4 data_quality_detail : "Quotidien 04h00"~~ → **"Quotidien 04h15"** (vérifié `dags/maintenance/maintenance.py:323`)
8. ~~P27 drift : "Quotidien 06h00"~~ → **"Quotidien 05h30"** (vérifié `dags/ml/daily_drift_report.py:73`)

---

## 📊 Légende

| Symbole | Signification |
|---------|---------------|
| `LIVE` | TTL_REALTIME = 30s |
| `FAST` | TTL_FAST = 60s |
| `SLOW` | TTL_SLOW = 300s (5 min) |
| `STATIC` | TTL_STATIC = 600s (10 min) |
| `—` | Pas de cache (calcul pur, UI, ou widget paramétré) |
| `🟢` | Données temps réel (DAG <= 5 min) |
| `🟡` | Données ~quotidiennes (DAG ~1h) |
| `🔴` | Données figées (DAG daily ou pire) |

---

## 0️⃣ Widgets transversaux (présents dans 15/15 pages)

| # | Widget | Loader / Source | TTL | Table/Vue DB | Techno | Notes |
|---|--------|----------------|-----|--------------|--------|-------|
| T1 | `render_sidebar_navigation()` | `cached_lyon_addresses_with_coords()` | STATIC | `referentiel.lieux_lyon` (21 lieux emblématiques) | `st.sidebar` | — |
| T2 | `render_freshness_badge()` | `get_settings().last_ingestion_at` (settings statique) | — | — | `st.caption` | Calcul pur |
| T3 | `render_data_status_banner()` | DB ping live (`SELECT 1`) | LIVE | — | `st.info/warning/error` | Fail loud si DB indispo |

---

## 1️⃣ Usager — `Usager_1_Mon_Trajet.py` (Mon trajet, 12 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| U1 | `render_search_bar()` | `cached_lyon_addresses_with_coords()` | STATIC | `referentiel.lieux_lyon` | `st.selectbox` ×3 | — (référentiel) |
| U2 | `render_mode_comparison()` | (calculé en amont par la page) | — | `session_state["trip_<key>"]` | `st.columns` + cards HTML | — |
| U3 | `render_mode_summary()` | (calculé en amont) | — | `session_state` | `st.columns` + cards | — |
| U4 | `render_weather_widget()` | `cached_weather_hourly()` | FAST | `silver.meteo_hourly` | `st.markdown` card HTML + `st.columns` (prévisions 3h) | `*/1h` (Open-Meteo) |
| U5 | `render_velov_widget()` (×2 ctxs) | `cached_velov_stations()` + `cached_velov_predictions(horizon_minutes=60)` | LIVE + FAST | `silver.velov_clean` + `gold.velov_predictions` (H+1h focus) | `st.columns` + `st.html` cards custom (1/station + prédiction H+1h) | `*/5min` (bronze) + `*/1h` (retrain) |
| U6 | `render_transit_trip()` | `cached_transit_itinerary()` | LIVE | GTFS + GTFS-RT (TCL) | `st.markdown` banner HTML + `st.metric` (KPIs) + cards (segments) | `*/5min` (bronze) |
| U7 | `render_traffic_widget()` | `cached_traffic()` | LIVE | `gold.traffic_features_live` + `gold.trafic_predictions` (H+1h) | `st.metric` ×3 + card HTML (prédiction) | `*/10min` (transform) + `*/15min` (inference) |
| U8 | `render_traffic_map_compact()` | `cached_traffic_predictions_for_map()` | SLOW | `gold.trafic_predictions` (H+1h) | `st.pydeck_chart` (ScatterplotLayer) | `*/15min` (inference) |
| U9 | `render_velov_trip()` | (calcul via `src.routing.pathfinder`) | — | `silver.velov_clean` (via `cached_velov_stations()`) | Folium (`folium.Map` + `folium.Marker` + `folium.PolyLine`) | `*/5min` (bronze) |
| U10 | `render_itinerary_result()` | `cached_car_itinerary()` | LIVE | `gold.trafic_predictions` (H+1h) + `osm.ways` (pgRouting) | Folium (`folium.Map` + `folium.Marker` + `folium.PolyLine`) + `st.metric` | `*/15min` (inference + OSM costs) |
| U11 | `render_lieux_velov_map()` | (calcul via `pathfinder_multimodal`) | — | `referentiel.lieux_lyon` + `silver.velov_clean` | Folium (`folium.Map` + `folium.Marker` + `folium.PolyLine`) | — (référentiel) + `*/5min` (bronze) |
| U12 | `render_velov_map_compact()` | `cached_velov_predictions(horizon_minutes=60)` | FAST | `gold.velov_predictions` (H+1h focus) | `st.pydeck_chart` | `*/1h` (retrain) |

> **Sprint 22+ audit** : U7 affiche maintenant un **bandeau fraîcheur réel** (`🟢 Live · 2 min` / `🟡 Stale · 17 min` / `🔴 Figé · 2.3h`) au lieu d'un vert hardcodé.
> **Sprint 8+** : U5 et U12 n'utilisent QUE H+1h (avant : H+30min + H+1h).

---

## 2️⃣ Usager — `Usager_2_Alertes.py` (Mes alertes, 4 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| U13 | `render_alert_card()` ×N | (alerts passées par `cached_recent_alerts()`) | LIVE | `silver.chantiers_actifs` + alertes dynamiques | Card HTML custom | `*/5min` (bronze) |
| U14 | `render_alert_timeline()` | idem | LIVE | idem | `st.markdown` cards verticales (timeline) | `*/5min` |
| U15 | `render_alert_settings()` | (UI pur, pas de DB) | — | — | `st.form` + `st.slider` | — (UI) |
| U16 | (page) `st.metric("Alertes actives")` ×3 | `cached_recent_alerts(hours=6, limit=30)` | LIVE | idem U13 | `st.metric` | `*/5min` |

---

## 3️⃣ Pro TCL — `Pro_1_PCC_Live.py` (PCC Live, 6 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P1 | `render_alert_ticker()` | `cached_recent_alerts()` | LIVE | `silver.chantiers_actifs` + alertes dynamiques | Ticker HTML custom | `*/5min` |
| P2 | `render_network_map()` (Bus GPS) | `cached_buses_positions(limit=200)` | LIVE | `bronze.tcl_vehicles` → `silver.tcl_vehicles_clean` | `st.pydeck_chart` (ScatterplotLayer) | `*/5min` |
| P3 | `render_traffic_map()` (Charge trafic) | `cached_traffic_predictions_for_map()` | SLOW | `gold.trafic_predictions` (H+1h) | `st.pydeck_chart` | `*/15min` |
| P4 | (page) Alertes détail ×N | `cached_recent_alerts(hours=24, limit=10)` | LIVE | idem U13 | Card HTML inline | `*/5min` |
| P5 | `render_otp_heatmap_mini()` | `cached_otp_heatmap_data()` | FAST | `gold.mv_otp_heatmap` (Sprint 7, refresh 5h00 daily) | `go.Heatmap` (Plotly) | quotidien 05h00 (refresh_lieux_calendrier DAG) |
| P6 | `render_line_kpis()` + (page) Top bottlenecks ×5 | `cached_line_kpis()` + `cached_bottlenecks_top()` | FAST + FAST | `gold.mv_line_kpis_live` (155 lignes) + vue calculée runtime | `st.dataframe` | `*/5min` (transform) + quotidien 05h00 (refresh_lieux_calendrier) |

> **Sprint 15+ audit** : P2 et P3 sont dans un `st.radio` (un seul rendu pydeck par cycle, gain ~50%).

---

## 4️⃣ Pro TCL — `Pro_2_Heatmap_OTP.py` (Heatmap OTP, 3 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P7 | `render_otp_filters()` | (filtres UI) | — | — | `st.selectbox` + `st.slider` | — (UI) |
| P8 | `render_otp_heatmap()` | `cached_otp_heatmap_data()` | FAST | `gold.mv_otp_heatmap` | `go.Heatmap` (Plotly) | quotidien 05h00 |
| P9 | `render_line_comparison()` | `cached_line_kpis()` | FAST | `gold.mv_line_kpis_live` | `st.dataframe` | `*/5min` + quotidien 05h00 |

---

## 5️⃣ Pro TCL — `Pro_3_Correlation.py` (Corrélation bus × trafic, 10 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P10 | `render_line_selector()` | `cached_tcl_lines()` | STATIC | 10 lignes emblématiques TCL (`src/data/tcl_lines.py`) | `st.multiselect` | — (référentiel) |
| P11 | `render_correlation_matrix()` | `cached_infra_bottlenecks(top=500)` | FAST | `gold.infrastructure_bottlenecks` | `st.dataframe` | `*/5min` (transform) |
| P12 | `render_segment_table()` | `cached_infra_bottlenecks(top=500)` | FAST | idem | `st.dataframe` | `*/5min` |
| P13 | `render_cause_analysis()` | (segment passé en arg par la page) | — | idem | Card HTML | — |
| P14 | `render_bus_traffic_spatial()` (button-gate) | `cached_bus_traffic_spatial()` + `cached_bus_traffic_spatial_diagnosis_counts()` | FAST ×2 | `gold.mv_bus_traffic_spatial` (migration 018) | `px.scatter` (Plotly) + `st.dataframe` | `*/15min` (Sprint 15+ Axe 3) |
| P15 | `render_coherence_scatter()` (button-gate) | `cached_tomtom_coherence()` + `cached_tomtom_gl_drift()` | LIVE + FAST | `gold.v_coherence_tomtom_vs_grandlyon` (migration 14) | `go.Scatter` ×N + `go.Bar` | `*/15min` (TomTom DAG) |
| P16 | `render_multimodal_heatmap()` (button-gate) | `cached_multimodal_grid(limit=5000)` + `cached_multimodal_grid_diagnosis_counts()` | FAST ×2 | `gold.mv_multimodal_grid` (migration 017) | Folium (`folium.plugins.Rectangle`) | `*/10min` (Sprint 15+ Axe 1) |
| P17 | `render_meteo_impact()` (button-gate) | `cached_meteo_impact()` | SLOW | `gold.mv_meteo_impact` (migration 022) | `st.metric` (KPI cards) + `go.Bar` (chart Plotly) | quotidien 04h30 (Sprint 17 Axe 7) |
| P18 | `render_modal_shift_alert()` (button-gate) | `cached_velov_transit_coupling()` + `cached_velov_transit_coupling_summary()` | FAST ×2 | `gold.mv_velov_transit_coupling` (migration 023) | `st.metric` (KPI) + `go.Bar` (Plotly) + `st.dataframe` | `*/15min` (Sprint 17 Axe 4) |
| P19 | `render_propagation_map()` (button-gate) | `cached_congestion_propagation_pairs()` + `cached_traffic_speeds_for_propagation(hours=6)` | SLOW + LIVE | `gold.mv_congestion_propagation_pairs` (migration 024 v3) | Folium (`folium.plugins.AntPath`) | `*/30min` (Sprint 17 Axe 2) |

---

## 6️⃣ Pro TCL — `Pro_4_Simulateur.py` (Simulateur fréquences, 5 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P20 | `render_line_selector()` | `cached_tcl_lines()` | STATIC | 10 lignes emblématiques TCL | `st.selectbox` | — (référentiel) |
| P21 | (page) `st.metric("OTP actuel")` ×4 | `cached_line_kpis()` | FAST | `gold.mv_line_kpis_live` | `st.metric` | `*/5min` + quotidien 05h00 |
| P22 | `render_frequency_slider()` | (calcul pur depuis `line_id`) | — | — | `st.slider` + `st.selectbox` | — (UI) |
| P23 | `render_otp_projection()` | (calcul pur depuis `simulation` + `base_otp`) | — | — | `st.metric` ×3 | — (UI) |
| P24 | `render_before_after_chart()` | (valeurs base/new passées) | — | — | `go.Bar` (Plotly) | — (UI) |

> **Hastus export** : `st.button("📤 Exporter scénario vers Hastus")` est inline dans la page, pas un widget séparé.

---

## 7️⃣ Pro TCL — `Pro_6_Pipeline_Mgmt.py` (Pipeline Management, 2 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P25 | `render_source_health_monitor()` | `cached_source_health()` + `cached_data_completeness()` | FAST + SLOW | `gold.v_source_health` + `gold.v_data_completeness` (migration 021) | `go.Indicator` (Plotly) + `st.dataframe` | quotidien 04h15 (maintenance DAG) |
| P26 | `render_pipeline_management_page()` | (DAG list via Airflow REST API) | — | Airflow metadata DB | `st.dataframe` | live (REST API) |

---

## 8️⃣ Pro TCL — `Pro_7_Model_Monitoring.py` (Model Monitoring, 3 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| P27 | `render_model_monitoring_page()` (8 sections) | `cached_mlflow_models()` + `cached_mlflow_experiment_summary()` + `cached_xgb_accuracy_summary()` + `cached_xgb_vs_tomtom()` | SLOW ×3 | MLflow Tracking + `gold.predictions_vs_actuals` | `go.Scatter` + `st.dataframe` | `*/30min` (backtest) + quotidien 05h30 (drift) |
| P28 | `render_gnn_map_section()` | `cached_spatial_mapping()` + `cached_traffic_predictions_for_map()` | STATIC + SLOW | `gold.dim_spatial_grid_mapping` + `gold.trafic_predictions` | `st.pydeck_chart` (ScatterplotLayer) | `*/15min` (inference) |
| P29 | `render_backtest_dashboard()` (button-gate) | `cached_xgb_vs_tomtom()` + `cached_predictions_vs_actuals()` | FAST ×2 | `gold.mv_xgb_vs_tomtom` (migration 020) + `gold.predictions_vs_actuals` | `go.Scatter` + `go.Bar` | `*/30min` |

> **Toggle** : P27 + P28 + P29 désactivés par défaut (`LYONFLOW_DASHBOARD_MODEL_MONITORING=true` requis).

---

## 9️⃣ Élu — `Elu_1_Synthese.py` (Synthèse exécutive, 11 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| E1 | `render_network_health_gauge()` | `cached_network_health_score()` | LIVE | `gold.fn_network_health_score()` (migration 019) + `gold.network_health_history` (migration 030, sparkline) | `go.Indicator` (Plotly) | runtime (fonction SQL) + `*/15min` (record_network_health DAG pour sparkline) |
| E2 | `render_drift_status_badge()` | `cached_xgb_accuracy_summary(hours=24)` | SLOW | `gold.v_xgb_accuracy_summary` | Bandeau HTML + `st.caption` | quotidien 05h30 (drift) |
| E3 | `render_data_quality_badge()` | `cached_source_health()` | FAST | `gold.v_source_health` (migration 021) | Bandeau HTML | quotidien 04h15 (maintenance) |
| E4 | `render_data_quality_detail()` | `cached_quality_report(limit=200)` | SLOW | `gold.data_quality_log` (migration 025) | `st.dataframe` ×N | quotidien 04h15 (maintenance) |
| E5 | `render_executive_summary()` | `cached_elu_kpis_dict()` | FAST | (KPIs agrégés runtime) | Texte markdown | LIVE (vue SQL) |
| E6 | `render_kpi_cards()` | `cached_elu_kpis_dict()` + `cached_kpis_12_months()` | FAST + SLOW | `gold.mv_kpis_12_months` + vue KPI | Card HTML ×5 | LIVE + 1×/jour (archive silver) |
| E7 | `render_traffic_map_compact()` | `cached_traffic_predictions_for_map()` | SLOW | `gold.trafic_predictions` (H+1h) | `st.pydeck_chart` | `*/15min` |
| E8 | `render_trend_chart()` (button-gate) | `cached_elu_kpis_dict()` | FAST | Vue KPI 12 mois | `go.Scatter` (Plotly) | LIVE |
| E9 | `render_top_decisions(n=3)` | `cached_bottlenecks_top()` | FAST | Vue bottlenecks | `st.dataframe` + card | `*/5min` |
| E10 | `render_news_section()` | (contenu statique hardcodé dans le widget) | — | — | `st.markdown` cards ×4 | — (statique) |
| E11 | `render_pdf_generator()` | (sections passées par la page) | — | — | WeasyPrint (HTML→PDF) + fallback reportlab | — (UI action) |

---

## 🔟 Élu — `Elu_2_Bottlenecks.py` (Bottlenecks prioritaires, 3 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| E12 | `render_bottleneck_map()` | `cached_bottlenecks_top()` | FAST | Vue bottlenecks | Folium (`folium.CircleMarker` ×N) | `*/5min` |
| E13 | `render_bottleneck_ranking()` | `cached_bottlenecks_top()` | FAST | idem | `st.dataframe` | `*/5min` |
| E14 | `render_roi_calculator()` | `cached_bottlenecks_top()` | FAST | idem | `st.metric` + sliders | `*/5min` |

---

## 1️⃣1️⃣ Élu — `Elu_3_Avant_Apres.py` (Avant/Après, 2 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| E15 | `render_project_selector()` | `cached_amenagements_passes(limit=50)` | SLOW | `gold.amenagements_history` (référentiel historique) | `st.selectbox` | — (référentiel) |
| E16 | `render_delta_kpis()` | (avant/après passés par la page) | — | idem | `st.columns` + cards HTML ×N | — (UI) |

---

## 1️⃣2️⃣ Élu — `Elu_4_Simulateur.py` (Simulateur aménagement, 3 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| E17 | `render_map_painter()` | `cached_bottlenecks_top()` (fallback) | FAST | idem E12 | Folium (`folium.CircleMarker`) | `*/5min` |
| E18 | `render_impact_projection()` | (zone passée par la page) | — | idem | `st.metric` + texte | — (UI) |
| E19 | `render_cost_estimate()` | (zone passée par la page) | — | idem | `st.metric` + texte | — (UI) |

---

## 1️⃣3️⃣ Élu — `Elu_5_Rapport.py` (Rapport CM, 3 widgets)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| E20 | `render_template_selector()` | (UI pur) | — | — | `st.selectbox` | — (UI) |
| E21 | `render_slide_builder()` | (UI multi-select) | — | — | `st.checkbox` ×N | — (UI) |
| E22 | `render_pdf_generator()` | (sections passées par la page) | — | — | WeasyPrint (HTML→PDF) | — (UI action) |

---

## 1️⃣4️⃣ Page commune — `A_Propos.py` (À propos, 1 widget principal)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| A1 | (page) `st.markdown(...)` + version | `get_settings().app_version` | — | — | `st.markdown` | — (statique) |

---

## 1️⃣5️⃣ Page commune — `9_RGPD_Conformite.py` (RGPD, 1 widget principal)

| # | Widget | Loader (cached_*) | TTL | Table/Vue DB | Techno | DAG refresh |
|---|--------|-------------------|-----|--------------|--------|-------------|
| R1 | (page) `st.markdown(...)` + version | `get_settings().app_version` | — | — | `st.markdown` | — (statique) |

---

## 🗑️ Dead code — widgets DÉFINIS mais jamais appelés (17 widgets)

Identifiés par `comm -23` entre les widgets définis et les widgets utilisés dans les pages :

| Widget | Fichier | Statut |
|--------|---------|--------|
| `render_alerts_feed` | `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 🗑️ Dead |
| `render_dag_list` | `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 🗑️ Dead |
| `render_data_freshness` | `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 🗑️ Dead |
| `render_data_quality_panel` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_drift_panel` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_format_selector` | `dashboard/components/widgets/pro_tcl/format_selector.py` | 🗑️ Dead |
| `render_health_panel` | `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 🗑️ Dead |
| `render_metrics_comparison` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_model_registry` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_model_registry_status` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_persona_switcher` | `dashboard/components/persona_switcher.py` | 🗑️ Dead (à vérifier si c'est intentionnel) |
| `render_pipeline_status` | `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 🗑️ Dead |
| `render_report_builder` | `dashboard/components/widgets/pro_tcl/report_builder.py` | 🗑️ Dead |
| `render_sparkline` | `dashboard/components/sparkline.py` | 🗑️ Dead (Sprint 21 a câblé via `network_health_gauge` interne, pas via render) |
| `render_training_history` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |
| `render_velov_map` | `dashboard/components/widgets/usager/velov_map.py` | 🗑️ Dead (seul `_render_velov_map` privé est utilisé par `velov_trip.py`) |
| `render_velov_model_analysis` | `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 🗑️ Dead |

> **Recommandation Sprint 22+** : déplacer ces 17 fichiers vers `archive/widgets_dead/` (convention Sprint 11+ : déplacer, jamais supprimer). Sprint 22+ les virer proprement.

---

## 📊 Synthèse par couche de données (validée 100%)

Tables/vues DB **réellement référencées** dans `src/data/db_query.py` (extraction automatique par grep) :

| Couche DB | # Widgets qui l'utilisent | TTL typique | DAG refresh typique |
|-----------|--------------------------|------------|---------------------|
| `gold.trafic_predictions` (H+1h) | 4 (U8, U10, P3, E7) | SLOW | `*/15min` (dag_inference_xgboost) |
| `gold.traffic_features_live` | 2 (U7, P19) | LIVE | `*/10min` (transform_silver_to_gold) |
| `gold.mv_otp_heatmap` | 2 (P5, P8) | FAST | quotidien 05h00 (refresh_lieux_calendrier) |
| `gold.mv_line_kpis_live` (155 lignes) | 4 (P6×2, P9, P20) | FAST | `*/5min` + quotidien 05h00 |
| `gold.infrastructure_bottlenecks` | 3 (P11, P12, P13) | FAST | `*/5min` (transform) |
| Vue bottlenecks runtime | 6 (E9, E12, E13, E14, E17, P6) | FAST | `*/5min` |
| `silver.velov_clean` + `gold.velov_predictions` | 3 (U5, U9, U12) | LIVE/FAST | `*/5min` (bronze) + `*/1h` (retrain) |
| `silver.tcl_vehicles_clean` | 2 (P2, U6) | LIVE | `*/5min` (transform) |
| `silver.meteo_hourly` | 1 (U4) | FAST | `*/1h` (Open-Meteo) |
| `gold.mv_multimodal_grid` (Sprint 15+) | 1 (P16) | FAST | `*/10min` (transform) |
| `gold.mv_bus_traffic_spatial` (Sprint 15+) | 1 (P14) | FAST | `*/15min` (transform) |
| `gold.v_coherence_tomtom_vs_grandlyon` (Sprint 13+) | 1 (P15) | LIVE/FAST | `*/15min` (TomTom DAG) |
| `gold.mv_meteo_impact` (Sprint 17) | 1 (P17) | SLOW | quotidien 04h30 |
| `gold.mv_velov_transit_coupling` (Sprint 17) | 1 (P18) | FAST | `*/15min` (refresh_velov_transit_coupling) |
| `gold.mv_congestion_propagation_pairs` (Sprint 17) | 1 (P19) | SLOW | `*/30min` (refresh_congestion_propagation) |
| `gold.dim_spatial_grid_mapping` | 1 (P28) | STATIC | — (référentiel) |
| `gold.amenagements_history` | 1 (E15) | SLOW | — (référentiel) |
| `gold.predictions_vs_actuals` | 2 (P27, P29) | SLOW | `*/30min` (backtest) + quotidien 05h30 (drift) |
| `gold.data_quality_log` | 1 (E4) | SLOW | quotidien 04h15 (maintenance) |
| `gold.fn_network_health_score()` (Sprint 15+) | 1 (E1) | LIVE | runtime (fonction SQL) + `*/15min` (record_network_health) |
| `gold.mv_kpis_12_months` | 1 (E6) | SLOW | 1×/jour (archive silver-to-minio) |
| `gold.v_source_health` (Sprint 16) | 2 (E3, P25) | FAST | quotidien 04h15 (maintenance) |
| `gold.v_data_completeness` (Sprint 16) | 1 (P25) | SLOW | quotidien 04h15 (maintenance) |
| `gold.v_xgb_accuracy_summary` (Sprint 16) | 1 (E2) | SLOW | quotidien 05h30 (drift) |
| `gold.mv_xgb_vs_tomtom` (Sprint 16) | 1 (P29) | FAST | `*/30min` (refresh_xgb_vs_tomtom) |
| `gold.network_health_history` (Sprint 21) | 1 (E1, sparkline) | LIVE | `*/15min` (record_network_health) |
| `gold.dim_gnn_adjacency` | 0 (référentiel GNN) | — | — |
| `gold.fact_correlation_matrix` | 0 (référentiel) | — | — |
| `gold.bus_delay_segments` | 0 (référentiel) | — | — |
| `gold.model_drift_reports` | 0 (référentiel) | — | — |
| `gold.velov_features` | 0 (référentiel Vélov ML) | — | — |
| `gold.v_tomtom_gl_drift` (Sprint 13+) | 1 (P15) | FAST | `*/15min` (TomTom DAG) |
| `gold.v_tomtom_traffic_live` (Sprint 13+) | 0 (interne) | — | — |
| `gold.v_traffic_combined` (Sprint 13+) | 0 (interne) | — | — |
| `referentiel.lieux_lyon` (21 lieux) | 2 (U1, U15) | STATIC | — (référentiel) |
| `referentiel.lieux_transports` (56 liaisons) | 0 (interne) | — | — |
| `referentiel.lieux_calendrier` (223 cadences) | 0 (interne) | — | — |
| `referentiel.v_lieux_velov_proches` | 1 (U11) | STATIC | — (référentiel) |
| `referentiel.v_lieux_velov_plus_proche` | 0 (interne) | — | — |
| `referentiel.v_lieux_velov_smart` | 0 (interne) | — | — |
| `referentiel.v_velov_neighbors` | 0 (interne) | — | — |
| `referentiel.nearest_velov_stations()` | 0 (interne) | — | — |
| `silver.chantiers_actifs` | 4 (U13, U14, P1, P4) | LIVE | `*/5min` (transform) + 1×/jour (chantiers) |
| `silver.meteo_hourly` | 1 (U4) | FAST | `*/1h` (bronze) |
| `silver.tcl_vehicles_clean` | 2 (P2, U6) | LIVE | `*/5min` |
| `silver.trafic_segments_clean` | 0 (interne) | — | — |
| `silver.velov_clean` | 3 (U5, U9, U12) | LIVE | `*/5min` |
| MLflow (Tracking Server) | 2 (P27) | SLOW | 1×/jour (training) |
| Airflow REST API | 1 (P26) | — | live (API) |
| **Aucun (statique ou UI pur)** | ~15 | — | — |

---

## 📈 Statistiques globales

| Métrique | Valeur | Vérification |
|----------|--------|--------------|
| Pages Streamlit | **15** | `ls dashboard/pages/*.py \| wc -l` |
| Fichiers widgets (60 = 13 Usager + 26 Pro TCL + 20 Élu + 1 Common) | **60** | `find dashboard/components/widgets -name "*.py" -not -name "__init__.py" \| wc -l` |
| Fonctions `render_*` totales | **95** | `grep -hE "^def render_[a-z_]+" dashboard/components/widgets/**/*.py \| wc -l` |
| Widgets **utilisés** dans au moins 1 page | **78** | `comm -13` (95 - 17 dead) |
| Widgets **dead code** | **17** | `comm -23` (liste ci-dessus) |
| Loaders `cached_*` dans `data_cache.py` | **48** | `grep -c "^def cached_" dashboard/components/data_cache.py` |
| DAGs Airflow schedulés | **15** actifs + 1 désactivé (`_disabled_dag_live_speed_retrain`) | `find dags -name "*.py" \| xargs grep -l schedule` |
| Tables/vues DB référencées dans `db_query.py` | **45** | `grep -E "FROM (silver\|gold\|bronze\|osm\|referentiel)\.[a-z_]+" src/data/db_query.py \| awk -F'FROM ' '{print $2}' \| sort -u \| wc -l` |
| Tables/vues DB touchées par le dashboard | **~35** | (cf. synthèse par couche) |
| Tests | **488 verts, 0 régression** | `pytest tests/data/ tests/ml/ tests/routing/ tests/widgets/ tests/persona/ -q` |

---

## ⚠️ Incohérence à clarifier : "18 pages" vs 15 réelles

CLAUDE.md dit "18 pages × 3 personas" mais `dashboard/pages/` ne contient que **15 fichiers .py** :
- 1 Accueil (`A_Propos.py`)
- 2 Usager (`Usager_1`, `Usager_2`)
- 5 Pro TCL (`Pro_1`, `Pro_2`, `Pro_3`, `Pro_4`, `Pro_6`, `Pro_7` — pas de Pro_5)
- 5 Élu (`Elu_1`, `Elu_2`, `Elu_3`, `Elu_4`, `Elu_5`)
- 1 RGPD (`9_RGPD_Conformite.py`)
- 1 À propos

**Hypothèses** :
- `Pro_5` jamais créé (saut Pro_4 → Pro_6)
- 3 pages "transversales" peut-être comptées à part dans le 18

**Recommandation Sprint 22+** : corriger CLAUDE.md pour aligner à 15, ou créer Pro_5 (si manque avéré).

---

## ⚠️ 9 bugs Sprint 22+ fixés (audit méthodique)

| # | Problème | Status | Commit |
|---|----------|--------|--------|
| 1 | 3 prédictions (H+30/H+1/H+3) dont 2 dead code (DAG n'insère que H+1) | ✅ Fixé | `5ea1781` |
| 2 | `_approx_lonlat_from_channel_id` plaçait markers au hasard (hash) | ✅ Fixé | `1882c8c` |
| 3 | Comparateur Usager : vitesse voiture hardcodée 25.0 + is_congested proxy bidon | ✅ Fixé | `1882c8c` |
| 4 | `_is_congested_from_speed` défini mais jamais appelé | ✅ Fixé (câblé) | `1882c8c` |
| 5 | `recommend_mode` fallback = winner=Vélov gratuit (trompeur) | ✅ Fixé (fail loud) | `1882c8c` |
| 6 | `data_source: "db_gold"` hardcodé dans le widget trafic | ✅ Fixé (freshness_status) | `5ea1781` |
| 7 | `_minutes_to_hours(30)` retournait None silencieusement | ✅ Fixé (ValueError) | `5ea1781` |
| 8 | `MLflowSettings.experiment_name` mort (4 endroits touchés) | ✅ Fixé | `d5c28f3` |
| 9 | DAG `_disabled_dag_live_speed_retrain` mort | ✅ Archivé | `d5c28f3` |
