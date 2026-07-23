# Présentation — LyonFlowFull

> Supports de présentation pour la certification **RNCP 38777 — Architecte en IA**
> (Bloc 4 Jedha : Industrialisation et MLOps).

## Sommaire

| Fichier | Sujet | Contexte |
|---------|-------|----------|
| [`soutenance-bloc4.html`](./soutenance-bloc4.html) | Soutenance Bloc 4 — 12 slides | RNCP 38777, oral de certification |

## `soutenance-bloc4.html`

Diaporama **12 slides** (1280×720, fond sombre, accent vert `#bef264`),
basé sur le référentiel de compétences Jedha Bloc 4.
Ouvrir directement dans un navigateur (`file://…`) — aucune dépendance
locale (Google Fonts + FontAwesome chargés via CDN).

### Index des slides

| # | Titre | Compétence Bloc 4 |
|---|-------|-------------------|
| 1 | Couverture | — |
| 2 | Un Système en Production Réelle | Chiffres clés (11 services, 8 sources, 3 modèles) |
| 3 | C1 — Besoins & Stratégie Métier | Personas, ROI, accessibilité |
| 4 | C2 — Architecture Algorithmique Hybride | ST-GRU-GNN + XGBoost |
| 5 | C2 — Pipeline de Données Medallion | Bronze / Silver / Gold |
| 6 | C3 — Serving API & Industrialisation | FastAPI + Streamlit + Nginx |
| 7 | C4 — Pipeline CI/CD & Qualité Logicielle | Tests, lint, mypy, Trivy |
| 8 | C5 — Réentraînement Automatisé | Airflow + MLflow + quality gates |
| 9 | C6 — Monitoring & Pilotage Modèle | Evidently, Prometheus/Grafana |
| 10 | Déploiement Frugal & Robuste | VPS 51.83.159.224, backup offsite |
| 11 | Roadmap — Transition Kubernetes | K8s (préparé), cloud (futur), GNN GPU |
| 12 | Merci / Questions | — |

### Notes sur le contenu

- **Statique** : capture d'un état du projet au moment de la rédaction
  (versions exactes : v0.12.1, 620 tests, 11 services Docker, 18 pages
  dashboard × 3 personas).
- **Self-contained** : pas de build, pas de framework JS. Polices et icônes
  via CDN.
- **État du projet au moment de la rédaction** : juillet 2026 (Sprint 21+).

## Maintenance

| Événement | Action |
|-----------|--------|
| Évolution des chiffres clés (tests, services, widgets) | Mettre à jour slides 2, 7 et 9 |
| Nouveau sprint livré | Mettre à jour roadmap slide 11 |
| Refonte de l'identité visuelle | Modifier les variables CSS en haut du `<style>` |

## Convention

Ce dossier `présentation/` est **hors cycle actif** au sens documentationnel
(comme `archive/`) : il n'est pas indexé par `archive/README.md` ni par
`AGENTS.md`. Aucun lien entrant depuis `README.md` n'est obligatoire.
