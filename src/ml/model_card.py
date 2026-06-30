"""Générateur de Fiches Modèles (Model Cards) — Documentation MLOps automatisée.

Génère automatiquement un document de type "Model Card" au format Markdown
à l'issue de chaque session d'entraînement XGBoost. Cette approche s'inspire
du framework standard "Model Cards for Model Reporting" (Mitchell et al. 2019).

**Contenu généré** :
- Métadonnées (date, type de modèle, version, hash des hyperparamètres)
- Cas d'usage prévu (Intended use) et limitations inhérentes au modèle
- Données d'entraînement (taille du dataset, période couverte, schéma de données)
- Métriques d'évaluation de la performance (MAE, RMSE, R², par validation croisée)
- Suivi de la dérive (Data Drift) si un rapport PSI est disponible
- Recommandations pour le ré-entraînement futur

**Résultat produit** :
Sauvegarde locale sous `models/{model_name}_v{version}_{date}.md` et
téléchargement automatique vers MLflow en tant qu'artefact (directement
consultable via l'interface UI du Model Registry).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_xgboost_card(
    *,
    model_name: str = "xgboost_speed",
    model_version: str,
    horizon_minutes: int,
    metrics: dict,
    params: dict,
    dataset_stats: dict,
    drift_report: dict | None = None,
    feature_cols: list[str] | None = None,
) -> str:
    """Génère un Model Card au format Markdown.

    Args:
        model_name: nom du modèle.
        model_version: version semver (ex. "1.2.0").
        horizon_minutes: horizon de prédiction (60 = H+1h).
        metrics: dict avec mae, rmse, r2.
        params: hyperparamètres du training.
        dataset_stats: stats de gold.xgb_training_set.
        drift_report: rapport PSI (optionnel).
        feature_cols: liste des features (optionnel).

    Returns:
        Contenu Markdown du Model Card.
    """
    now = datetime.now(UTC).isoformat()
    feature_cols = feature_cols or []
    feature_table = "\n".join(f"| `{c}` | numérique |" for c in feature_cols)

    drift_section = ""
    if drift_report:
        drift_section = f"""
## Drift monitoring )

- **Dataset drift** : `{drift_report.get("dataset_drift")}`
- **Drift share** : `{drift_report.get("drift_share", 0.0) * 100:.1f}%`
- **N ref / current** : `{drift_report.get("n_ref")}` / `{drift_report.get("n_current")}`
- **Computed at** : `{drift_report.get("computed_at")}`
- **Modèle** : `{drift_report.get("model_name")}` (horizon {drift_report.get("horizon_min")}min)
"""

    return f"""# Model Card — {model_name} v{model_version}

> Généré automatiquement le {now} MLOps).
> Hash params : `{json.dumps(params, sort_keys=True)}`

## Métadonnées

| Champ | Valeur |
|-------|--------|
| **Modèle** | `{model_name}` |
| **Version** | `{model_version}` |
| **Horizon** | H+{horizon_minutes}min |
| **Date training** | {now} |
| **Framework** | XGBoost (xgboost 2.x) |
| **Schema features** | v0.3.1 |

## Intended use

Prédiction de la vitesse trafic (km/h) à un horizon donné, par canal
(channel_id = identifiant LYO0xxxx). Usage principal : alimentation
du dashboard Streamlit (`gold.trafic_predictions` lu par la carte
trafic et le module de recommandation multimodal).

## Limitations

- Valide uniquement pour Lyon intra-muros (zones couvertes par
  gold.dim_spatial_grid_mapping).
- Pas de garantie hors fenêtre d'entraînement (2 jours rolling).
- Pas adapté aux événements exceptionnels (manifestations, grèves,
  accidents majeurs) — re-training recommandé après chaque
  perturbation structurelle.

## Training data

| Champ | Valeur |
|-------|--------|
| **Source** | `gold.xgb_training_set` (matérialisé quotidien 02h30) |
| **N rows** | `{dataset_stats.get("n_rows", "N/A")}` |
| **N channels** | `{dataset_stats.get("n_channels", "N/A")}` |
| **Période** | `{dataset_stats.get("min_t", "N/A")}` → `{dataset_stats.get("max_t", "N/A")}` |
| **Target mean** | `{dataset_stats.get("mean_target", 0.0):.2f}` km/h |
| **Target std** | `{dataset_stats.get("std_target", 0.0):.2f}` km/h |

## Features ({len(feature_cols)})

| Feature | Type |
|---------|------|
{feature_table}

## Hyperparamètres

```json
{json.dumps(params, indent=2)}
```

## Metrics

| Metric | Valeur |
|--------|--------|
| **MAE** | `{metrics.get("mae", 0.0):.3f}` km/h |
| **RMSE** | `{metrics.get("rmse", 0.0):.3f}` km/h |
| **R²** | `{metrics.get("r2", 0.0):.3f}` |

{drift_section}

## Recommandations

- **Re-training** : quotidien via `dag_daily_speed_train` (03h00).
- **Rollback** : si MAE > 8 km/h (x2 baseline) sur la prod pendant
  > 24h, envisager transition vers le modèle Staging précédent.
- **Drift** : si ``dataset_drift = True`` pendant > 3 jours consécutifs,
  investiguer le pipeline d'ingestion Bronze (changement API Grand
  Lyon, données manquantes, etc.).
- **Promotion** : transition vers Production automatique dans
  `train_one()` (MLflow `register_model` + `transition_to_production`).

## Reproduce

```bash
# Local
python -c "from src.models.xgboost_speed import XGBoostSpeedModel; m = XGBoostSpeedModel(); m.train_one(60)"

# Airflow
docker compose exec airflow-scheduler airflow dags trigger dag_daily_speed_train
```
"""


def save_card(
    card_md: str,
    model_name: str,
    model_version: str,
    output_dir: Path | str = "/opt/lyonflow/data/models",
) -> Path:
    """Sauvegarde le Model Card en .md. Retourne le Path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    path = output_dir / f"{model_name}_v{model_version}_{date_str}.md"
    path.write_text(card_md, encoding="utf-8")
    logger.info("Model Card saved to %s", path)
    return path
