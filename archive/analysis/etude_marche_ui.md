# LyonFlowFull — Étude Marché, Interface & Modèle Économique

**Généré**: 2026-06-05

---

## 1. Marché

### Taille et croissance

- Smart City Platform Market: **$225B (2025) → $462B (2032)**, CAGR 10.8%
- Transport intelligent = **29.1% du marché** smart city, plus forte croissance 2026-2033
- Intelligent Traffic Management: marché en forte accélération avec adoption IA
- France: **~40 métropoles** avec poste central de régulation trafic (réseau Cerema)
- Municipales 2026: mobilité = enjeu stratégique n°1 pour les élus

### Contexte local Lyon

- SYTRAL Mobilités: **262 communes, 1.9M habitants**, réseau TCL
- Keolis Bus Lyon opère le réseau
- SYTRAL prépare une **nouvelle application de mobilité**
- Grand Lyon SmartData: plateforme open data mature (OnlyMoov, Optimod/Opticities)
- Données trafic, SIRI Lite, GTFS, Vélov, chantiers, météo = tout en open data

### Concurrents / Solutions existantes

| Solution | Type | Prix | Ce qu'elle fait | Ce qu'elle fait PAS |
|----------|------|------|----------------|---------------------|
| TomTom Traffic API | API payante | $$$ | Trafic temps réel, prédiction, routing | Pas de multimodal, pas d'analyse infrastructure |
| HERE Traffic | API payante | $$$ | Trafic, incidents, routing | Pas de GNN, pas de bus delay |
| Google Maps Platform | API payante | $$$ | Routing, ETA, trafic | Boîte noire, pas de prédiction par segment |
| Waze/Google | Consumer | Gratuit | Crowdsource, alertes | Pas d'analyse structurelle |
| OnlyMoov (Lyon) | Info trafic | Gratuit | État routes Lyon | Pas de prédiction, pas de ML |
| Urban SDK | SaaS B2G | $$$ | Dashboard géospatial IA | US-focused, propriétaire |
| Cerema outils | Institutionnel | Public | Études, méthodologies | Pas de temps réel, pas de ML |

### Avantage concurrentiel LyonFlowFull — ce que PERSONNE ne fait

1. **GNN + XGBoost ensemble** — prédiction spatiale (propagation congestion) + réactivité. Aucun concurrent open source ne combine les deux
2. **Croisement bus/trafic → diagnostic infrastructure** — corrélation retard bus + congestion routière pour identifier bottlenecks infra
3. **Recommandation basée sur prédictions réelles** — pas "prends le vélo" mais "prends le vélo parce que le T3 aura 8min de retard et Vélov a 12 vélos dispo (prévu 8 dans 30min)"
4. **Open source + données publiques** — zéro coût API, reproductible pour toute métropole française avec open data
5. **VPS gratuit** — pas de coût cloud, autonomie totale

---

## 2. Interface — Design en 3 niveaux

### Problèmes actuels

- Folium avec 2400 markers = lent
- Rerun Streamlit complet à chaque clic = UX cassée
- 9 pages indépendantes = l'utilisateur cherche l'info
- Pas de vue "situation globale" en un coup d'oeil

### Niveau 1 — Situation (5 secondes)

> "Est-ce que Lyon roule bien maintenant et dans 1h?"

- Score global 0-100 (vert/orange/rouge)
- Mini-carte heatmap agrégée
- 3 KPI: vitesse moyenne réseau, nb bottlenecks actifs, nb lignes bus en retard
- Alerte si dégradation prévue

### Niveau 2 — Exploration (30 secondes)

> "Où sont les problèmes et pourquoi?"

- Carte pleine page deck.gl/Pydeck (WebGL, fluide 2400+ points)
- Layers toggle: trafic / bus retard / vélov / bottlenecks / pistes cyclables / métro
- Timeline slider: maintenant → H+30min → H+1h → H+3h
- Clic segment → panneau détail (vitesse, prédiction, historique 24h, bus corrélé)

### Niveau 3 — Action (2 minutes)

> "Quel trajet recommander / quel diagnostic poser?"

- Recommandation trajet: origine/destination → scoring multimodal avec prédictions
- Diagnostic infrastructure: bottlenecks classés par sévérité, alternatives identifiées
- Export rapport PDF pour décideurs

### Pages restructurées

| # | Page | Contenu | Cible |
|---|------|---------|-------|
| 0 | **Accueil — Situation** | Score global, mini-carte, KPIs, alertes | Tous |
| 1 | **Carte Trafic** | deck.gl, layers, timeline, prédictions GNN+XGBoost | Opérateur |
| 2 | **Bus & Retards** | Carte retards par ligne, accumulation, corrélation trafic | Opérateur |
| 3 | **Bottlenecks Infra** | Zones rouge (bus+trafic), pistes cyclables bleues, métro violet | Décideur |
| 4 | **Vélo'v** | Stations, prédictions H+30/H+1h, alternatives proches | Usager |
| 5 | **Recommandation Trajet** | Planificateur multimodal, scoring, conseil | Usager |
| 6 | **Monitoring ML** | Métriques modèles, drift, backtesting, GNN vs XGBoost | Tech |
| 7 | **Pipeline Status** | DAGs, tables, freshness, qualité données | Tech |
| 8 | **RGPD** | Conformité, données collectées, rétention | Légal |

### Choix techniques UI

| Aspect | Choix | Raison |
|--------|-------|--------|
| Framework | Streamlit | Prototypage rapide, écosystème Python |
| Carte principale | Pydeck/deck.gl | WebGL, 100k points fluide, layers natifs |
| Carte bus/détail | Folium | Popups riches, SVG arrows, petits volumes |
| Charts | Plotly | Interactif, dark theme, export image |
| Thème | Dark | Control room, lisibilité couleurs carte |
| Caching | @st.cache_data | Éviter requery DB à chaque rerun |
| Refresh | st.rerun() 5 min | Données live sans action utilisateur |

---

## 3. Modèle Économique

### Positionnement: Open-Core + Service

Le code est open source (GitHub public), la valeur est dans le **déploiement, l'adaptation et l'expertise**.

### 3 sources de revenus

#### A. Déploiement as-a-Service pour collectivités (€€€)

> "Votre métropole a les mêmes données open data que Lyon. On déploie LyonFlowFull chez vous en 4 semaines."

| Offre | Cible | Prix indicatif | Contenu |
|-------|-------|---------------|---------|
| **Setup** | Métropole française | 15-30k€ one-shot | Adaptation aux sources données locales, déploiement VPS/cloud, formation |
| **Maintenance** | Idem | 500-1500€/mois | Monitoring, mise à jour modèles, support L2 |
| **Sur-mesure** | Métropole + | Sur devis | Features spécifiques (parking, covoiturage, ZFE) |

**Argument commercial**: TomTom Traffic API = 3-10k€/mois pour du trafic seul. LyonFlowFull = setup 20k€ + 1k€/mois pour trafic + bus + vélo + recommandation + diagnostic infra. **ROI en 3-6 mois.**

**Marché adressable France**: ~40 métropoles avec poste de régulation trafic × 20k€ setup = **800k€ potentiel rien qu'en setup**.

#### B. Conseil data / aide à la décision (€€)

> "Vos données montrent que le T3 accumule 12min de retard sur Cours Gambetta entre 17h et 19h, corrélé à 87% avec la congestion routière. Recommandation: couloir bus dédié ou réaménagement carrefour."

| Offre | Cible | Prix | Contenu |
|-------|-------|------|---------|
| **Audit mobilité** | Collectivité, AOM | 5-15k€ | Diagnostic bottlenecks, rapport avec données, recommandations infra |
| **Étude d'impact** | Aménageur | 3-8k€ | Simulation avant/après aménagement (nouvelle piste cyclable, fermeture voie, etc.) |

**Différenciateur**: les cabinets de conseil mobilité (EGIS, Cerema, Setec) facturent 50-200k€ pour des études sans ML. LyonFlowFull fournit des diagnostics data-driven à 10× moins cher.

#### C. API SaaS pour développeurs / apps mobilité (€)

> "Intégrez nos prédictions trafic + bus + vélov dans votre app."

| Endpoint | Prix | Contenu |
|----------|------|---------|
| /predict/traffic | 0.001€/appel | Prédiction vitesse par segment, 4 horizons |
| /predict/bus-delay | 0.001€/appel | Prédiction retard par ligne |
| /predict/velov | 0.0005€/appel | Prédiction dispo station |
| /recommend | 0.005€/appel | Recommandation trajet multimodale |
| **Pack 10k appels/mois** | 29€/mois | Starter pour apps en dev |
| **Pack 100k appels/mois** | 199€/mois | Production |
| **Illimité** | 499€/mois | Enterprise |

### Coûts de fonctionnement

| Poste | Coût | Notes |
|-------|------|-------|
| VPS actuel | **0€** | Gratuit (avantage clé) |
| Domaine + SSL | ~15€/an | Let's Encrypt gratuit |
| APIs données | **0€** | Toutes publiques/gratuites |
| Stockage DB | Inclus VPS | PostgreSQL local |
| Monitoring | **0€** | Evidently open source |
| Total mensuel | **~1€** | Quasi-nul |

### Marge brute

- Offre Setup collectivité: ~85% de marge (le coût = temps de travail)
- Offre Maintenance: ~90% de marge (automatisé)
- API SaaS: ~95% de marge (coût infra quasi-nul)
- Conseil: ~80% de marge (expertise + données automatiques)

### Comparaison coût vs concurrence

```
Scénario: Métropole 500k habitants, 500 capteurs trafic, 200 arrêts bus

TomTom Traffic API:        5 000€/mois = 60 000€/an
HERE Traffic:              4 000€/mois = 48 000€/an  
Urban SDK:                 3 000€/mois = 36 000€/an
Étude Cerema/EGIS:        80 000€ one-shot (pas de temps réel)

LyonFlowFull:
  Setup:                  25 000€ one-shot
  Maintenance:             1 000€/mois = 12 000€/an
  Total année 1:          37 000€
  Total année 2+:         12 000€/an

Économie vs TomTom: 23 000€ année 1, 48 000€/an ensuite
+ diagnostic infra + recommandation = inclus (pas dispo chez TomTom)
```

### Roadmap commerciale

| Phase | Horizon | Action |
|-------|---------|--------|
| **0 — Certification** | Maintenant | Projet complet, dashboard démo, documentation |
| **1 — Vitrine** | +3 mois | Dashboard public Lyon en lecture seule, article Medium/blog, GitHub stars |
| **2 — Premier client** | +6 mois | Approcher métropole pilote (Grenoble? Saint-Étienne? Bordeaux?) via réseau Cerema |
| **3 — API** | +9 mois | FastAPI publique, documentation Swagger, plan tarifaire |
| **4 — Scale** | +12 mois | Template déploiement multi-villes, Terraform/Ansible automatisé |

### Pitch en 1 phrase

> **LyonFlowFull**: la première plateforme open source qui prédit le trafic routier ET les retards bus pour diagnostiquer les problèmes d'infrastructure urbaine — 10× moins cher que TomTom, avec des insights que personne d'autre ne fournit.

---

## Sources

- [Smart City Platforms Market 2033 — Grand View Research](https://www.grandviewresearch.com/industry-analysis/smart-city-platforms-market-report)
- [Intelligent Traffic Management 2026 — EIN Presswire](https://www.einnews.com/amp/pr_news/900715626/intelligent-traffic-management-system-market-2026-improving-urban-mobility)
- [Cerema Mobil'inPulse janvier 2026](https://www.cerema.fr/fr/actualites/mobilite-intelligente-retour-interventions-du-cerema-au-0)
- [Municipales 2026 Mobilité — Mobhilis](https://mobhilis.fr/municipales2026-mobilite-un-enjeu-local-strategique/)
- [SYTRAL nouvelle app TCL — Tribune de Lyon](https://tribunedelyon.fr/transports/a-lyon-sytral-et-tcl-preparent-une-nouvelle-application-de-mobilite/)
- [TomTom Traffic APIs](https://www.tomtom.com/products/traffic-apis/)
- [Traffic Management Dashboards — InetSoft](https://www.inetsoft.com/info/traffic-management-dashboard/)
- [Urban SDK — Geospatial AI](https://www.urbansdk.com/)
- [Streamlit vs Dash — dash-resources.com](https://dash-resources.com/dash-plotly-vs-streamlit-what-are-the-differences/)
- [Smart Mobility Report 2026 — StartUs Insights](https://www.startus-insights.com/innovators-guide/smart-mobility-report/)
