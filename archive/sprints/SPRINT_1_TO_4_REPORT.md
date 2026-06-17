# LyonFlowFull — Rapport Sprints 1 à 4

**Date** : 2026-06-05
**Branche** : fondation + 3 tracks parallèles
**Statut** : ✅ Tous les livrables complétés, **28/28 tests passent**

---

## 1. Résumé exécutif

LyonFlowFull est maintenant une plateforme multi-persona complète avec :
- **3 personas** distincts (Usager, Pro TCL, Élu) dans un dashboard unifié
- **13 pages** fonctionnelles (3 + 5 + 5) + 2 pages communes (RGPD, À propos)
- **45 widgets** Streamlit réutilisables répartis par persona
- **Architecture Medallion mock** avec données réalistes Lyon
- **Génération PDF** pour rapports Conseil Municipal (WeasyPrint + fallback reportlab)
- **Authentification par mot de passe** par persona (env var)
- **Sélecteur de persona** dans la sidebar (3 modes)

**Métriques** :
| Élément | Nombre |
|---------|--------|
| Fichiers Python | 84 |
| Fichiers YAML | 1 (`config/personas.yaml`) |
| Templates HTML | 1 (`src/reporting/templates/synthese_mensuelle.html`) |
| Lignes Python | ~6 200 |
| Tests pytest | 28 (100% passants) |
| Widgets | 45 (12 usager + 18 pro_tcl + 15 elu) |
| Pages | 15 (13 personas + 2 communes) |

---

## 2. Architecture livrée

### 2.1 Le cerveau : `config/personas.yaml`

C'est l'unique source de vérité. Modifier ce fichier change le comportement
de toute l'app :
- Définition des 3 personas (id, label, icône, couleurs, description)
- Authentification (auth_required, password_env)
- Pages accessibles (`navigation:`)
- Widgets visibles / cachés par persona
- Thème (densité, refresh interval)
- Filtres par défaut (mode_transport, horizon, périmètre)

### 2.2 Backend `src/persona/`

| Module | Rôle |
|--------|------|
| `personas_loader.py` | Charge le YAML, expose les configs |
| `manager.py` | State management du persona courant + `PersonaManager` |
| `auth.py` | Vérification mot de passe (env var) |

### 2.3 Frontend `dashboard/components/`

- `persona_switcher.py` — Sélecteur 3 cartes ou pills
- `persona_guard.py` — Vérifie persona + auth, lève `st.stop()` si KO
- `navigation.py` — Sidebar custom avec navigation par persona
- `theme.py` — Injection CSS selon couleur primaire du persona
- `widgets/{usager,pro_tcl,elu}/` — 45 widgets métier

### 2.4 Mock data `src/data/mock/`

Données réalistes Lyon sans dépendance DB :
- `usager.py` — 12 lignes TCL, 8 stations Vélov, 3 alertes, 4 favoris
- `pro_tcl.py` — 10 lignes, 25 segments avec classification, OTP 7j×24h, KPIs, alertes prédites
- `elu.py` — 5 KPIs × 12 mois, 10 bottlenecks avec ROI, 5 aménagements passés, 5 projets

### 2.5 Reporting `src/reporting/`

- `pdf_renderer.py` — HTML→PDF via WeasyPrint (fallback reportlab)
- `templates/synthese_mensuelle.html` — Template de base

---

## 3. Track Usager (Sprint 2)

**Pages** : Mon Trajet · Alertes · Favoris

| Widget | Description |
|--------|-------------|
| `search_bar` | Recherche géolocalisée avec auto-complétion |
| `recommendation_card` | Top reco (mode, durée, coût, CO2, probabilité) |
| `alternative_card` | 2-3 alternatives en cartes compactes |
| `why_explainer` | Top 3 raisons de la reco (accordéon) |
| `weather_widget` | Météo compacte + impact vélo |
| `velov_widget` | Dispo Vélov des 3 stations proches |
| `traffic_widget` | Trafic résumé + prédictions H+30min, H+1h, H+3h |
| `alert_card` | Carte alerte (titre, action) |
| `alert_timeline` | Frise chronologique verticale |
| `alert_settings` | Réglages (types, fenêtre, mode notif) |
| `favorite_list` | Liste des trajets favoris |
| `recurrent_trip_card` | Carte trajet récurrent |

**Tests** : 8/8 passants.

---

## 4. Track Pro TCL (Sprint 3)

**Pages** : PCC Live · Heatmap OTP · Corrélation bus/trafic · Simulateur · Export

### 4.1 L'USP technique : la matrice de corrélation

C'est le **différenciateur clé** de LyonFlowFull. Pour chaque segment, on
croise **bus retard / trafic bouché** → 4 diagnostics :

| Bus | Trafic | Diagnostic | Action |
|-----|--------|------------|--------|
| 🟢 OK | 🟢 Fluide | ✅ RAS | - |
| 🟢 OK | 🔴 Bloqué | 🔵 Voie bus OK | Étendre à d'autres tronçons |
| 🔴 Retard | 🟢 Fluide | 🟡 Exploitation | Ajuster fréquence |
| 🔴 Retard | 🔴 Bloqué | 🔴 Infrastructure | Couloir bus dédié (ROI 18 mois) |

C'est ce croisement qu'aucun concurrent (TomTom, HERE, Waze) ne fait.

### 4.2 Autres widgets

| Widget | Description |
|--------|-------------|
| `network_map` | Carte Pydeck bus GPS colorés par retard |
| `alert_ticker` | Ticker CSS horizontal défilant |
| `otp_heatmap` | Heatmap Plotly lignes × heures |
| `otp_heatmap_mini` | Version compacte pour PCC Live |
| `line_selector` | Selecteur simple / multi-lignes |
| `line_kpis` | 4 KPI cards denses par ligne (OTP, retard, fréq, charge) |
| `line_comparison` | Tableau comparaison N lignes |
| `otp_filters` | Filtres période, jours, météo |
| `segment_table` | Table interactive des segments |
| `cause_analysis` | Panneau "pourquoi ce retard" + recommandation |
| `frequency_slider` | Slider ajout bus / plage horaire |
| `otp_projection` | Projection OTP avant/après + IC 95% |
| `before_after_chart` | Graphique Plotly comparatif |
| `report_builder` | Sélecteur période + lignes + sections |
| `format_selector` | Excel / PDF / SAEIV / Hastus / API |
| `saeiv_export` | Bouton export JSON SAEIV |
| `export_button` | Bouton générique |

**Tests** : 8/8 passants.

---

## 5. Track Élu (Sprint 4)

**Pages** : Synthèse · Bottlenecks · Avant/Après · Simulateur · Rapport CM

### 5.1 Le bloc À annoncer

Le persona Élu doit pouvoir dire au conseil municipal :
> *« Lyon devient la 1ère métropole française à diagnostiquer ses
> bottlenecks de mobilité en croisant retards bus et trafic routier via
> open data et intelligence artificielle. »*

Le widget `news_section` génère 4 blocs de communication (annonce majeure,
résultat chiffré, engagement, perspective) avec deltas réels.

### 5.2 Génération PDF

`src/reporting/pdf_renderer.py` :
- `render_html_template(sections)` → HTML complet
- `generate_pdf(html)` → bytes PDF

Fallback chain :
1. WeasyPrint (recommandé, dépendance système libpango)
2. reportlab (fallback universel)
3. RuntimeError explicite si aucun des deux

**Tests** : 11/11 passants (7 widget + 4 PDF dont génération effective).

---

## 6. Sécurité

- ✅ Aucune credential en dur — toutes via `os.getenv()`
- ✅ Variables d'env attendues : `PERSONA_PRO_TCL_PASSWORD`, `PERSONA_ELU_PASSWORD`
- ✅ Aucun mot de passe par défaut
- ✅ Pas de f-string SQL (pas de DB pour l'instant, mais la règle est en place)
- ✅ Pages communes (RGPD, À propos) accessibles à tous
- ✅ Pages protégées : `apply_persona_guard()` en début, lève `st.stop()` si KO

---

## 7. Comment lancer

```bash
cd /Users/patriceduclos/Documents/Lyonfull

# 1. Installer les dépendances
pip install streamlit pyyaml pandas plotly pydeck folium streamlit-folium \
            weasyprint reportlab openpyxl pytest --break-system-packages

# 2. (Optionnel) Configurer les mots de passe des personas protégés
export PERSONA_PRO_TCL_PASSWORD="votre_mot_de_passe_pro"
export PERSONA_ELU_PASSWORD="votre_mot_de_passe_elu"

# 3. Lancer
streamlit run dashboard/Accueil.py

# 4. (Tests)
pytest tests/ -v
```

---

## 8. Dette technique restante (pour Sprint 5)

1. **Data binding réel** : tout est en mock. Branche Sprint 5 = brancher
   PostgreSQL Gold layer (lignes TCL, OTP, prédictions).
2. **Component React custom pour Simulateur d'aménagement** : actuellement
   sélection manuelle sur Folium. Sprint 5 = deck.gl + MapboxDraw pour
   dessiner librement un aménagement.
3. **API FastAPI** : pas encore créée. Les pages appellent du mock.
4. **Auth SSO** : simple mot de passe actuellement. Sprint 5 = SSO OAuth
   (Keycloak/Auth0) pour Pro TCL et Élu.
5. **CD/CI** : pas de pipeline. Sprint 5 = GitHub Actions (lint + test +
   build + deploy).
6. **Mobile responsive** : Streamlit desktop-first. Sprint 5 = wrapper PWA
   ou composants mobile-friendly.
7. **Internationalisation** : 100% français actuellement. Sprint 5 = i18n
   via gettext.

---

## 9. Métriques Sprint 4 → 5

| Métrique | Sprint 1-4 | Sprint 5 cible |
|----------|-----------|----------------|
| Pages fonctionnelles | 13 | 13 (data réelle) |
| Widgets | 45 | 45 (optimisés) |
| Sources DB | 0 (mock) | 8 (bronze) |
| Tests | 28 | 50+ |
| Temps chargement Mon Trajet | ~1s | <500ms |
| Couverture auth | 2/3 personas | 3/3 + SSO |

---

## 10. Prochaines actions recommandées

1. **Setup PostgreSQL + ingestion** (8 sources Bronze, DAGS Airflow)
2. **Brancher les vraies données** dans les widgets existants
3. **Component React Simulateur** (deck.gl + MapboxDraw)
4. **API FastAPI** pour exposer les prédictions
5. **Pipeline CD/CI** (GitHub Actions + déploiement VPS)

---

*LyonFlowFull v0.1.0 · 2026-06-05 · Patrice DUCLOS*
