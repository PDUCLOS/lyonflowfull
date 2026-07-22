# Schémas drawio — LyonFlow

> **6 schémas visuels** pour comprendre l'architecture globale de la plateforme MLOps.
> Tous ouvrables dans [app.diagrams.net](https://app.diagrams.net) (drag&drop du fichier) ou dans Draw.io Desktop.

## Index

| # | Fichier | Sujet | Sources `CLAUDE.md` couvertes |
|---|---------|-------|-------------------------------|
| 01 | `01_flux_donnees_medallion.drawio` | Architecture Medallion (Bronze → Silver → Gold + OSM) | Section "Pipeline de Données" |
| 02 | `02_infra_vps.drawio` | Infrastructure VPS 51.83.159.224 (Docker + disques) | Section "Déploiement" + "Stack VPS" |
| 03a | `03_piliers_ml.drawio` | **4 piliers ML** : Trafic / Bus / Vélov / Recommandation | Section "4 Piliers ML" |
| 03b | `03_schema_postgres_colonnes.drawio` | Schéma détaillé des colonnes Postgres — 8 pages (lineage table-à-table + 7 ERD par schéma, ~970 mxCell) | `docs/POSTGRES_DATABASE_REFERENCE.md`, `docs/DICTIONNAIRE_COLONNES.md` |
| 04 | `04_pipeline_airflow.drawio` | DAGs par catégorie + scheduling timeline | Section "Scheduling Airflow" |
| 05 | `05_dashboard_personas.drawio` | 18 pages × 3 personas (59 widgets) | Section "Dashboard — Architecture 3 personas" |
| 06 | `06_routing_pgrouting.drawio` | Zoom routage multimodal : pgRouting voiture + smart Vélov | Section "Pilier 4 — Recommandation trajet multimodale" |

## Légende couleurs

| Couleur | Domaine |
|---------|---------|
| Orange (#ffe6cc) | Bronze / Ingestion / Sources externes |
| Gris (#f5f5f5) | Silver / Transformations |
| Jaune (#fff2cc) | Gold / Bus / Multimodal |
| Bleu (#dae8fc) | Trafic / Voiture / API |
| Vert (#d5e8d4) | Vélov / Airflow / Maintenance |
| Violet (#e1d5e7) | OSM pgRouting / Élu / MLflow |
| Rose (#f8cecc) | Widgets dashboard |
| Noir | Headers de section |

## Utilisation

### Ouvrir un schéma
- **Web** : https://app.diagrams.net → File → Open from Device → choisir le `.drawio`
- **Desktop** : [drawio-desktop](https://github.com/jgraph/drawio-desktop/releases) → File → Open
- **VS Code** : extension `hediet.vscode-drawio`

### Éditer
Tous les fichiers sont en XML brut (format mxGraphModel), versionnables et mergeables proprement.
Un node = une `mxCell vertex`, une flèche = une `mxCell edge`.

### Exporter
Dans drawio : File → Export as → PNG / SVG / PDF. Recommandé pour inclusion dans un doc Word/PDF ou pour partage institutionnel (RNCP 38777).

## Maintenance

| Événement | Action |
|-----------|--------|
| Nouveau DAG ajouté | Mettre à jour `04_pipeline_airflow.drawio` (catégorie + scheduling) |
| Nouvelle page dashboard | Mettre à jour `05_dashboard_personas.drawio` |
| Nouveau pilier ML | Mettre à jour `03_piliers_ml.drawio` |
| Nouveau service Docker | Mettre à jour `02_infra_vps.drawio` |
| Modification schema DB gold/silver | Mettre à jour `01_flux_donnees_medallion.drawio` |

Date de dernière mise à jour : **2026-07-06** — `04` (DAG `collect_vigilance_meteo` + 6e table silver `air_quality_clean`) et `05` (composant `velov_safety_banner`) alignés sur migration_045 (2026-07-05), déjà couverte par `01` et `03b`.