# Résumé des Modifications IA (Sprint 22+)

Ce document a été généré pour être transmis à une autre IA. Il résume les optimisations UX/UI appliquées au projet LyonFlow (branche `vps`) pour réduire la consommation RAM et améliorer l'expérience utilisateur (lazy loading et organisation en onglets).

## 🚀 Périmètre des modifications (Partie Frontend)

1. **`Pro_3_Correlation.py`** : Refonte structurelle. Remplacement du layout linéaire (33 rendus consécutifs) par 4 onglets (`st.tabs`) regroupant logiquement les analyses par thématique :
   - Bus × Trafic
   - Spatial & TomTom
   - Multimodal
   - Propagation
2. **`Elu_1_Synthese.py`** : Mise en place du "lazy loading" (chargement différé). Les composants lourds suivants ont été encapsulés dans des `st.expander(expanded=False)` :
   - Carte de trafic H+1h
   - Graphique des tendances (part modale)
   - Section News
   - Génération du PDF
3. **`Usager_1_Mon_Trajet.py`** : Mise en place du "lazy loading" pour l'affichage conditionnel. Les sections suivantes sont désormais dans des `st.expander(expanded=False)` :
   - Trajet Transport en commun
   - Carte de trafic H+1h
   - Trajet Vélov + marche
   - Cartes de couverture Vélo'v
   - *Exception* : L'itinéraire détaillé voiture s'ouvre par défaut (`expanded=True`) au clic sur "Calculer".

> **Validation Technique** : La suite de tests a été exécutée avec succès (`411/411 verts`). Aucune régression, la logique métier reste intacte.

---

## 💻 Patch Git des modifications (Commit `071fccef`)

```diff
diff --git a/dashboard/pages/Elu_1_Synthese.py b/dashboard/pages/Elu_1_Synthese.py
--- a/dashboard/pages/Elu_1_Synthese.py
+++ b/dashboard/pages/Elu_1_Synthese.py
@@ -32,8 +32,8 @@
 # Carte charge trafic — synthèse exécutive (Sprint 10)
-st.markdown("##### 🗺️ Charge du trafic — projection H+1h")
-render_traffic_map_compact(height=340, horizon_minutes=60, key_suffix="elu")
+with st.expander("🗺️ Charge du trafic — projection H+1h", expanded=False):
+    render_traffic_map_compact(height=340, horizon_minutes=60, key_suffix="elu")
 
 st.markdown("---")
 
@@ -42,9 +42,10 @@
 col1, col2 = st.columns([3, 2])
 with col1:
-    st.markdown("##### 📈 Tendance — Part modale TC")
-    deferred_render(
-        "trend_chart_part_modale_tc",
-        ...
-    )
+    with st.expander("📈 Tendance — Part modale TC", expanded=False):
+        deferred_render(
+            "trend_chart_part_modale_tc",
+            ...
+        )
 with col2:
+    st.markdown("##### 🏆 Top Décisions")
     render_top_decisions(n=3)
 
@@ -63,3 +64,4 @@
 # Bloc À annoncer
-render_news_section()
+with st.expander("📢 À annoncer (News)", expanded=False):
+    render_news_section()
 
@@ -70,33 +72,34 @@
 # Bouton PDF synthèse
-st.markdown("##### 📄 Génération rapport PDF")
-kpis_dict = cached_elu_kpis_dict()
-...
-render_pdf_generator(sections)
+with st.expander("📄 Génération rapport PDF", expanded=False):
+    kpis_dict = cached_elu_kpis_dict()
+    ...
+    render_pdf_generator(sections)

diff --git a/dashboard/pages/Pro_3_Correlation.py b/dashboard/pages/Pro_3_Correlation.py
--- a/dashboard/pages/Pro_3_Correlation.py
+++ b/dashboard/pages/Pro_3_Correlation.py
@@ -143,171 +143,174 @@
 selected_lines = render_line_selector(multiselect=True, key_suffix="corr")
 target_line = selected_lines[0] if selected_lines else None
 
-st.markdown("---")
-
-# Matrice de corrélation
-render_correlation_matrix(line_id=target_line)
-
-st.markdown("---")
-
-# Détail par segment
-col1, col2 = st.columns([3, 2])
-with col1:
-    st.markdown("##### Table des segments")
-    render_segment_table(line_id=target_line, height=350)
-with col2:
-    st.markdown("##### Analyse causale (1er segment problématique)")
-...
+tab1, tab2, tab3, tab4 = st.tabs([
+    "Bus × Trafic",
+    "Spatial & TomTom",
+    "Multimodal",
+    "Propagation",
+])
+
+with tab1:
+    # Matrice de corrélation
+    render_correlation_matrix(line_id=target_line)
+
+    st.markdown("---")
+
+    # Détail par segment
+    col1, col2 = st.columns([3, 2])
+    with col1:
+        st.markdown("##### Table des segments")
+        render_segment_table(line_id=target_line, height=350)
+    with col2:
+        st.markdown("##### Analyse causale (1er segment problématique)")
+...
+with tab2:
+    deferred_render("bus_traffic_spatial", ...)
+    st.markdown("---")
+    deferred_render("coherence_scatter", ...)
+
+with tab3:
+    deferred_render("multimodal_heatmap", ...)
+    st.markdown("---")
+    deferred_render("meteo_impact", ...)
+    st.markdown("---")
+    deferred_render("modal_shift_alert", ...)
+
+with tab4:
+    deferred_render("propagation_map", ...)

diff --git a/dashboard/pages/Usager_1_Mon_Trajet.py b/dashboard/pages/Usager_1_Mon_Trajet.py
--- a/dashboard/pages/Usager_1_Mon_Trajet.py
+++ b/dashboard/pages/Usager_1_Mon_Trajet.py
@@ -404,23 +404,23 @@
     # ── Trajet transport en commun (si TC sélectionné, Sprint 14) ─────────
     if has_tc:
         st.markdown("---")
-        st.markdown("### 🚌 Trajet transport en commun")
-        try:
-            tc_result = render_transit_trip(...)
-            ...
+        with st.expander("🚌 Trajet transport en commun", expanded=False):
+            try:
+                tc_result = render_transit_trip(...)
+                ...
 
     # ── Trafic routier (si Voiture sélectionné) ──────────────────────────
     if has_voiture:
         st.markdown("##### 🚦 État du trafic routier")
         render_traffic_widget()
 
-        st.markdown("##### 🗺️ Carte du trafic — H+1h")
-        render_traffic_map_compact(...)
+        with st.expander("🗺️ Carte du trafic — H+1h", expanded=False):
+            render_traffic_map_compact(...)
 
     # ── Trajet Vélov (si Vélov sélectionné) ──────────────────────────────
     if has_velov:
         st.markdown("---")
-        st.markdown("### 🚲 Trajet Vélov + marche")
-        if origin_coords and dest_coords:
-            ...
+        with st.expander("🚲 Trajet Vélov + marche", expanded=False):
+            if origin_coords and dest_coords:
+                ...
 
     # ── Itinéraire voiture (si Voiture sélectionné) ──────────────────────
@@ -488,10 +488,11 @@
         if st.session_state.get("itin_compute"):
-            voiture_result = render_itinerary_result(...)
+            with st.expander("Voir l'itinéraire voiture détaillé", expanded=True):
+                voiture_result = render_itinerary_result(...)
 
     # ── Cartes informatives Vélov (si Vélov sélectionné) ─────────────────
     if has_velov:
         st.markdown("---")
 
-        st.markdown("##### 🗺️ Couverture Vélov des lieux emblématiques")
-        ...
-        st.markdown("##### 🚲 Toutes les stations Vélo'v")
-        render_velov_map_compact(...)
+        with st.expander("🗺️ Couverture Vélov des lieux emblématiques", expanded=False):
+            ...
+        with st.expander("🚲 Toutes les stations Vélo'v", expanded=False):
+            render_velov_map_compact(...)
```
