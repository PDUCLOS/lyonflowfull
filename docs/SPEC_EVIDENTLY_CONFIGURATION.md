# SPEC — Configuration Evidently & Drift Detection

> **Date** : 2026-06-20  
> **Contexte** : Sprint 16 Axe A — Backtest Engine  
> **Statut** : analyse complète + décision technique + plan de tests

---

## Table des matières

1. [Diagnostic de l'existant](#1-diagnostic-de-lexistant)
2. [Décision : PSI primary + Evidently optional](#2-décision--psi-primary--evidently-optional)
3. [API Evidently v0.4 vs v0.7 — Breaking changes](#3-api-evidently-v04-vs-v07--breaking-changes)
4. [Architecture cible](#4-architecture-cible)
5. [Configuration Evidently v0.7](#5-configuration-evidently-v07)
6. [Modifications `drift_detector.py`](#6-modifications-drift_detectorpy)
7. [Modifications `health_checks.py`](#7-modifications-health_checkspy)
8. [Modifications `pyproject.toml` et requirements](#8-modifications-pyprojecttoml-et-requirements)
9. [Plan de tests](#9-plan-de-tests)
10. [Impact Docker / VPS](#10-impact-docker--vps)

---

## 1. Diagnostic de l'existant

### Fichiers drift en place

| Fichier | Rôle | Statut | Dépendance Evidently |
|---------|------|--------|---------------------|
| `src/monitoring/psi.py` | PSI pur Python (quantile buckets) | ✅ Fonctionne | **Aucune** |
| `src/monitoring/drift_detector.py` | Wrapper Evidently DataDriftPreset | ❌ **Cassé** (API v0.4) | `evidently.report.Report` (n'existe plus en v0.7) |
| `src/monitoring/health_checks.py` | `check_drift_evidently()` — lit `gold.model_drift_reports` | ✅ Fonctionne (lit seulement) | Aucune (lit les résultats) |

### Versions Evidently

| Emplacement | Version | API |
|-------------|---------|-----|
| Local (miniforge) | **0.7.21** | Nouvelle (`from evidently import Report`) |
| `requirements-base.txt` | `>=0.4.0` (pas de borne sup) | Ambiguë |
| `requirements-airflow.txt` | `>=0.4,<0.5` (pinné) | Ancienne (`from evidently.report import Report`) |
| Docker VPS (probable) | 0.4.x | Ancienne |

### Ce que `psi.py` fait déjà

```python
# Appel existant — zéro dépendance, déterministe
from src.monitoring.psi import compute_dataset_drift

result = compute_dataset_drift(
    reference=ref_df,
    current=cur_df,
    columns=["xgb_speed_kmh", "error_abs_kmh", "error_pct", ...],
)
# Retourne :
# {
#     "xgb_speed_kmh": {"psi": 0.042, "status": "stable", ...},
#     "error_abs_kmh": {"psi": 0.31, "status": "significant", ...},
#     "_summary": {"drift_share": 0.4, "dataset_drift": False, ...}
# }
```

**Seuils PSI** (standard industrie) :
- `< 0.1` → stable (distributions quasi identiques)
- `0.1 - 0.2` → moderate (shift léger, surveiller)
- `> 0.2` → significant (drift confirmé, action requise)

### Ce que `drift_detector.py` essaie de faire (et échoue)

```python
# ❌ API v0.4 — cassée avec v0.7
from evidently import ColumnMapping              # n'existe plus
from evidently.metric_preset import DataDriftPreset  # déplacé dans evidently.presets
from evidently.report import Report                  # déplacé dans evidently

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=ref, current_data=cur, column_mapping=mapping)
result = report.as_dict()  # n'existe plus, remplacé par snap.dict()
```

---

## 2. Décision : PSI primary + Evidently optional

### Analyse

| Critère | PSI (`psi.py`) | Evidently v0.7 |
|---------|---------------|----------------|
| Dépendances | 0 (numpy + pandas, déjà en place) | **13+ transitives** : litestar, uvicorn, nltk, statsmodels, scikit-learn, cryptography, dynaconf, fsspec, opentelemetry-proto, plotly, pydantic, rich, typer |
| Taille Docker ajoutée | 0 Mo | ~250-400 Mo (nltk data, scikit-learn, litestar...) |
| RAM au runtime | ~5 Mo (array ops) | ~80-150 Mo (chargement modules) |
| Tests statistiques | KS-like via histogrammes quantile | KS, Anderson-Darling, PSI, Wasserstein, Jensen-Shannon, Chi² (auto-select) |
| Visualisation | Aucune (données brutes) | HTML report, Plotly intégré |
| Interprétabilité | Très haute (PSI = 1 nombre, seuils industriels) | Haute (p-values + drift/no-drift + stat test name) |
| Déterminisme | Oui (quantile bins fixés) | Oui (tests stats déterministes) |
| Maintenance | 160 lignes, aucune dépendance à maintenir | Mise à jour fréquentes, breaking changes (v0.4 → v0.7 = preuve) |

### Décision

**PSI comme moteur principal de drift.** Evidently en option pour les rapports HTML enrichis.

**Raisons** :
1. PSI **fonctionne déjà** et est testé. Evidently est **cassé** avec le pin actuel.
2. Sur un VPS 12 Go RAM avec Docker, ajouter 250+ Mo de dépendances pour un DAG quotidien n'est pas justifié.
3. Le PSI fournit exactement ce dont on a besoin : un score par feature + un seuil + un statut. Le health check et le widget dashboard n'ont besoin que de ça.
4. Evidently est un excellent outil, mais il apporte plus de valeur dans un contexte de reporting ponctuel (notebook, CI) que dans un DAG quotidien sur VPS.

### Ce qu'on garde d'Evidently

Evidently reste dans `requirements-base.txt` (usage notebook/local) mais **pas** dans le chemin critique DAG. Le `drift_detector.py` utilisera PSI par défaut et Evidently en fallback optionnel pour les rapports HTML (export ponctuel depuis le dashboard Pro_7).

---

## 3. API Evidently v0.4 vs v0.7 — Breaking changes

### Imports

```python
# v0.4 (ancien — code actuel cassé)
from evidently.report import Report
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset

# v0.7 (nouveau)
from evidently import Report
from evidently.presets import DataDriftPreset
# ColumnMapping supprimé — plus nécessaire
```

### Exécution

```python
# v0.4
report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=ref, current_data=cur, column_mapping=cm)
result = report.as_dict()
drift_info = result["metrics"][0]["result"]
# drift_info = {"dataset_drift": bool, "number_of_drifted_columns": int, ...}

# v0.7
report = Report(metrics=[DataDriftPreset()])
snapshot = report.run(current_data=cur, reference_data=ref)
# snapshot.dict() → {"metrics": [...], "tests": [...]}
# snapshot.metric_results → dict[str, MetricResult]
#   Clé "DriftedColumnsCount" → .count.value, .share.value
#   Clé "ValueDrift for X" → .value (= p-value)
```

### Extraction des résultats v0.7 (vérifié expérimentalement)

```python
def extract_drift_from_snapshot(snapshot) -> dict:
    """Extrait les résultats drift d'un Snapshot Evidently v0.7."""
    out = {}
    for key, val in snapshot.metric_results.items():
        dn = val.display_name
        if hasattr(val, "count") and hasattr(val, "share"):
            out["n_drifted"] = int(val.count.value)
            out["share_drifted"] = float(val.share.value)
            out["dataset_drift"] = val.share.value >= 0.5
        elif hasattr(val, "value") and "drift for" in dn:
            col = dn.replace("Value drift for ", "")
            out[f"{col}_p_value"] = float(val.value)
            out[f"{col}_drifted"] = float(val.value) < 0.05
    return out
```

### Résultats validés expérimentalement (2026-06-20)

**Sans drift** (mêmes distributions) :
```
dataset_drift: False
n_drifted: 0
share_drifted: 0.0
error_abs_kmh_p_value: 0.654   → pas de drift
xgb_speed_kmh_p_value: 0.396   → pas de drift
```

**Avec drift** (prédictions décalées + erreurs doublées) :
```
dataset_drift: True
n_drifted: 4
share_drifted: 0.8
error_abs_kmh_p_value: 1.3e-53 → drift massif
xgb_speed_kmh_p_value: 2.9e-10 → drift
tomtom_confidence_p_value: 4.6e-66 → drift
tomtom_speed_kmh_p_value: 0.210 → stable (oracle inchangé ✓)
```

**Observation clé** : quand le modèle drift mais l'oracle (TomTom) reste stable, `tomtom_speed_kmh` ne drift PAS → c'est bien le modèle qui dégrade, pas la source. Ce diagnostic différentiel est exactement ce qu'on veut.

---

## 4. Architecture cible

```
                    DAG daily_drift_report (05h30)
                              │
                              ▼
                    ┌──────────────────┐
                    │ drift_detector.py │
                    │  run_drift_report │
                    └──────┬───────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
        ┌──────────────┐    ┌────────────────────┐
        │   psi.py      │    │  evidently (v0.7)   │
        │  PRIMARY      │    │  OPTIONAL           │
        │  zéro deps    │    │  rapports HTML       │
        │  PSI scores   │    │  export ponctuel     │
        └──────┬────────┘    └────────┬─────────────┘
               │                      │
               ▼                      ▼
     gold.model_drift_reports    /tmp/drift_report.html
     (INSERT quotidien)          (export Pro_7 on-demand)
               │
               ▼
     ┌─────────────────────────────────────────┐
     │ health_checks.py → check_drift_evidently │
     │ (lit dernier rapport, détermine statut)  │
     └─────────┬─────────────┬─────────────────┘
               │             │
               ▼             ▼
     Pro_7 widget        Élu badge
     backtest_dashboard  drift_status_badge
```

### Flux de données

1. **05h30** : DAG `daily_drift_report` lance `run_drift_report()`
2. `run_drift_report()` appelle `psi.compute_dataset_drift()` sur les colonnes de `gold.mv_xgb_vs_tomtom`
3. Résultat INSERT dans `gold.model_drift_reports`
4. **Dashboard** : `check_drift_evidently()` lit le dernier rapport → statut ok/warning/critical
5. **On-demand** : bouton Pro_7 "📊 Rapport drift Evidently (HTML)" → `_run_evidently_html()` → affichage inline (si evidently installé)

---

## 5. Configuration Evidently v0.7

### Quand Evidently est utilisé (et quand il ne l'est pas)

| Contexte | Moteur | Justification |
|----------|--------|---------------|
| DAG quotidien `daily_drift_report` | **PSI** | Léger, déterministe, zéro deps |
| Health check `check_drift_evidently()` | **Lecture DB** | Lit le résultat PSI, pas de calcul |
| Widget Pro_7 KPIs | **Lecture DB** | Idem |
| Bouton Pro_7 "Rapport HTML détaillé" | **Evidently v0.7** (optionnel) | Rapport visuel riche, on-demand |
| Notebook local d'analyse | **Evidently v0.7** | Exploration interactive |

### DataDriftPreset — configuration recommandée

```python
from evidently import Report
from evidently.presets import DataDriftPreset

# Colonnes à surveiller (alignées sur gold.mv_xgb_vs_tomtom)
DRIFT_COLUMNS = [
    "xgb_speed_kmh",      # prédiction XGBoost
    "tomtom_speed_kmh",    # oracle TomTom
    "error_abs_kmh",       # erreur absolue (proxy MAE)
    "error_pct",           # erreur relative (proxy MAPE)
    "tomtom_confidence",   # confiance TomTom (qualité oracle)
]

def generate_evidently_html_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    output_path: str = "/tmp/drift_report.html",
) -> str | None:
    """Génère un rapport HTML Evidently (v0.7).

    Usage ponctuel — bouton Pro_7 ou notebook.
    Ne doit PAS être appelé dans un DAG (trop lourd).
    """
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except ImportError:
        return None  # Evidently non installé, pas grave

    ref = reference_df[DRIFT_COLUMNS].dropna()
    cur = current_df[DRIFT_COLUMNS].dropna()

    if ref.empty or cur.empty:
        return None

    report = Report(metrics=[DataDriftPreset()])
    snapshot = report.run(current_data=cur, reference_data=ref)
    snapshot.save_html(output_path)
    return output_path
```

### Diagnostic différentiel — la logique métier

Le drift sur ces 5 colonnes a des significations distinctes :

| Colonne en drift | Diagnostic | Action |
|-----------------|-----------|--------|
| `xgb_speed_kmh` ↑ + `tomtom_speed_kmh` stable | **Modèle dégradé** — prédictions décalées, oracle inchangé | Retrain XGBoost |
| `error_abs_kmh` ↑ ou `error_pct` ↑ | **Qualité modèle en baisse** — erreurs croissantes | Retrain + vérifier features |
| `tomtom_speed_kmh` drift + `xgb_speed_kmh` drift | **Changement réel du trafic** — les deux sources bougent | Normal (événement, vacances, chantier) |
| `tomtom_confidence` ↓ | **Oracle dégradé** — TomTom moins fiable | Vérifier quota API / couverture GPS |
| Rien ne drift | **Stable** | RAS |

Ce diagnostic est implémenté dans le widget `drift_status_badge` :

```python
def _diagnose_drift(report: dict) -> tuple[str, str]:
    """Retourne (statut, message) pour le badge Élu."""
    psi_details = report.get("details", {})

    xgb_drift = psi_details.get("xgb_speed_kmh", {}).get("status") in ("moderate", "significant")
    tomtom_drift = psi_details.get("tomtom_speed_kmh", {}).get("status") in ("moderate", "significant")
    error_drift = psi_details.get("error_abs_kmh", {}).get("status") in ("moderate", "significant")
    confidence_drop = psi_details.get("tomtom_confidence", {}).get("status") in ("moderate", "significant")

    if error_drift and xgb_drift and not tomtom_drift:
        return "critical", "Modèle dégradé — retrain recommandé"
    if xgb_drift and tomtom_drift:
        return "warning", "Changement trafic réel détecté"
    if confidence_drop and not error_drift:
        return "warning", "Oracle TomTom moins fiable"
    if error_drift:
        return "warning", "Erreurs en hausse — surveiller"
    return "ok", "Modèle stable"
```

---

## 6. Modifications `drift_detector.py`

### Avant (cassé — API v0.4)

```python
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=ref, current_data=cur, column_mapping=mapping)
result = report.as_dict()
drift_info = result["metrics"][0]["result"]
```

### Après (PSI primary, Evidently optionnel)

```python
def run_drift_report(
    reference_df: pd.DataFrame | None = None,
    current_df: pd.DataFrame | None = None,
    hours_current: int = 24,
    hours_reference: int = 168,
) -> dict[str, Any]:
    """Compare reference vs current via PSI (moteur principal).

    PSI (Population Stability Index) : standard industrie, zéro dépendance.
    Seuils : < 0.1 stable, 0.1-0.2 modéré, > 0.2 drift significatif.
    """
    if reference_df is None or current_df is None:
        reference_df, current_df = _fetch_reference_current(
            hours_current=hours_current, hours_reference=hours_reference,
        )

    if reference_df.empty or current_df.empty:
        return {
            "dataset_drift": False,
            "n_drifted_features": 0,
            "share_drifted_features": 0.0,
            "n_ref": len(reference_df),
            "n_current": len(current_df),
            "details": {"info": "empty reference or current"},
            "engine": "psi",
        }

    available = [c for c in NUMERICAL_FEATURES
                 if c in reference_df.columns and c in current_df.columns]
    if not available:
        return {
            "dataset_drift": False,
            "n_drifted_features": 0,
            "share_drifted_features": 0.0,
            "n_ref": len(reference_df),
            "n_current": len(current_df),
            "details": {"info": "no numerical features available"},
            "engine": "psi",
        }

    from src.monitoring.psi import compute_dataset_drift

    psi_result = compute_dataset_drift(
        reference=reference_df,
        current=current_df,
        columns=available,
    )
    summary = psi_result.pop("_summary")

    return {
        "dataset_drift": summary["dataset_drift"],
        "n_drifted_features": summary["n_columns_drifted"],
        "share_drifted_features": summary["drift_share"],
        "n_ref": len(reference_df),
        "n_current": len(current_df),
        "details": psi_result,  # {col: {psi, status, ...}, ...}
        "engine": "psi",
    }
```

### Fonction Evidently HTML (optionnelle, non DAG)

```python
def generate_html_drift_report(
    reference_df: pd.DataFrame | None = None,
    current_df: pd.DataFrame | None = None,
    hours_current: int = 24,
    hours_reference: int = 168,
) -> str | None:
    """Génère un rapport HTML Evidently v0.7 (usage ponctuel).

    Retourne le HTML en string ou None si Evidently non installé.
    NE PAS appeler dans un DAG — usage dashboard on-demand uniquement.
    """
    try:
        from evidently import Report as EvidentlyReport
        from evidently.presets import DataDriftPreset
    except ImportError:
        return None

    if reference_df is None or current_df is None:
        reference_df, current_df = _fetch_reference_current(
            hours_current=hours_current, hours_reference=hours_reference,
        )

    available = [c for c in NUMERICAL_FEATURES
                 if c in reference_df.columns and c in current_df.columns]
    ref = reference_df[available].dropna()
    cur = current_df[available].dropna()

    if ref.empty or cur.empty:
        return None

    report = EvidentlyReport(metrics=[DataDriftPreset()])
    snapshot = report.run(current_data=cur, reference_data=ref)
    return snapshot.get_html_str()
```

---

## 7. Modifications `health_checks.py`

Aucune modification nécessaire. `check_drift_evidently()` lit `gold.model_drift_reports` via `get_latest_drift_report()`. Le format des résultats PSI est compatible avec les champs existants (`dataset_drift`, `n_drifted_features`, `drift_share`).

La seule adaptation : le champ `details` contient maintenant des PSI scores au lieu de p-values Evidently. Le health check ne lit pas `details` (il utilise uniquement `dataset_drift` et `n_drifted_features`), donc aucun changement.

---

## 8. Modifications `pyproject.toml` et requirements

### `requirements-airflow.txt`

```diff
- evidently>=0.4,<0.5
+ # Evidently retiré des dépendances Airflow — le drift DAG utilise PSI
+ # (src/monitoring/psi.py, zéro dépendance). Evidently disponible en
+ # option pour rapports HTML (pip install evidently>=0.7 sur le poste local).
```

### `requirements-base.txt`

```diff
- evidently>=0.4.0
+ evidently>=0.7.0  # optionnel — rapports HTML drift (pas dans le chemin critique)
```

### `pyproject.toml`

Ajouter evidently dans `[project.optional-dependencies]` plutôt que dans les deps obligatoires :

```toml
[project.optional-dependencies]
drift-reports = ["evidently>=0.7.0"]
```

Installation : `pip install lyonflowfull[drift-reports]` ou `pip install evidently>=0.7.0` directement.

### Pourquoi ne pas mettre Evidently en dépendance obligatoire

Evidently v0.7.21 tire **13+ dépendances transitives** :

| Dépendance | Taille estimée | Déjà en place |
|------------|---------------|---------------|
| scikit-learn | ~30 Mo | ✅ Oui |
| scipy | ~35 Mo | ✅ Oui |
| statsmodels | ~25 Mo | ❌ Non |
| nltk | ~15 Mo (+data ~100 Mo) | ❌ Non |
| litestar | ~10 Mo | ❌ Non |
| uvicorn | ~5 Mo | ❌ Non |
| opentelemetry-proto | ~8 Mo | ❌ Non |
| pydantic | ~5 Mo | ✅ Oui |
| plotly | ~20 Mo | ✅ Oui |
| rich | ~3 Mo | ❌ Non |
| typer | ~2 Mo | ❌ Non |
| dynaconf | ~2 Mo | ❌ Non |
| cryptography | ~15 Mo | ✅ Oui |

**Impact Docker estimé** : +180-250 Mo d'image, +50-100 Mo RAM au runtime.
Sur un VPS 12 Go RAM avec 29 Go Docker data-root, c'est faisable mais pas gratuit.

---

## 9. Plan de tests

### 9.1. Tests PSI (`tests/monitoring/test_psi.py`) — EXISTANTS à vérifier

```python
class TestComputePsi:
    """Tests unitaires pour psi.compute_psi()."""

    def test_identical_distributions_psi_near_zero(self):
        """Deux distributions identiques → PSI ≈ 0."""
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(35, 10, 500))
        result = compute_psi(ref, cur)
        assert result["psi"] < 0.1
        assert result["status"] == "stable"

    def test_shifted_distribution_psi_significant(self):
        """Distribution décalée → PSI > 0.2."""
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(55, 10, 500))  # +20 km/h
        result = compute_psi(ref, cur)
        assert result["psi"] > 0.2
        assert result["status"] == "significant"

    def test_moderate_shift(self):
        """Décalage léger → PSI entre 0.1 et 0.2."""
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 500))
        cur = pd.Series(np.random.normal(38, 11, 500))  # léger shift
        result = compute_psi(ref, cur)
        assert result["status"] in ("stable", "moderate")

    def test_empty_series(self):
        """Séries vides → status insufficient_data."""
        result = compute_psi(pd.Series(dtype=float), pd.Series(dtype=float))
        assert result["status"] == "insufficient_data"
        assert np.isnan(result["psi"])

    def test_constant_values(self):
        """Valeurs constantes → ne crash pas (fallback linspace bins)."""
        ref = pd.Series([30.0] * 100)
        cur = pd.Series([30.0] * 100)
        result = compute_psi(ref, cur)
        assert result["psi"] >= 0  # ne crash pas

    def test_bucket_edges_count(self):
        """10 buckets → 11 edges."""
        np.random.seed(42)
        ref = pd.Series(np.random.normal(35, 10, 200))
        cur = pd.Series(np.random.normal(35, 10, 200))
        result = compute_psi(ref, cur, n_buckets=10)
        assert len(result["bucket_edges"]) == 11  # ou moins si duplicates dropped


class TestComputeDatasetDrift:
    """Tests unitaires pour psi.compute_dataset_drift()."""

    def test_no_drift_all_stable(self):
        """Mêmes distributions sur toutes les colonnes → pas de drift."""
        np.random.seed(42)
        n = 300
        cols = ["speed", "error", "confidence"]
        ref = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        cur = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        result = compute_dataset_drift(ref, cur, cols)
        assert result["_summary"]["dataset_drift"] is False
        assert result["_summary"]["n_columns_drifted"] == 0

    def test_drift_detected_when_majority_columns_shift(self):
        """Drift sur 2/3 colonnes → dataset_drift=True (share > 0.5)."""
        np.random.seed(42)
        n = 300
        ref = pd.DataFrame({
            "speed": np.random.normal(35, 10, n),
            "error": np.abs(np.random.normal(5, 3, n)),
            "confidence": np.random.uniform(0.6, 1.0, n),
        })
        cur = pd.DataFrame({
            "speed": np.random.normal(60, 15, n),   # gros shift
            "error": np.abs(np.random.normal(20, 8, n)),  # gros shift
            "confidence": np.random.uniform(0.6, 1.0, n),  # stable
        })
        result = compute_dataset_drift(ref, cur, ["speed", "error", "confidence"])
        assert result["_summary"]["dataset_drift"] is True
        assert result["_summary"]["n_columns_drifted"] >= 2

    def test_missing_column_skipped(self):
        """Colonne absente d'un DataFrame → ignorée sans crash."""
        ref = pd.DataFrame({"a": [1, 2, 3]})
        cur = pd.DataFrame({"a": [1, 2, 3]})
        result = compute_dataset_drift(ref, cur, ["a", "b_missing"])
        assert result["_summary"]["n_columns_analyzed"] == 1

    def test_per_column_psi_values(self):
        """Chaque colonne a un score PSI et un statut."""
        np.random.seed(42)
        n = 200
        ref = pd.DataFrame({"x": np.random.normal(0, 1, n)})
        cur = pd.DataFrame({"x": np.random.normal(0, 1, n)})
        result = compute_dataset_drift(ref, cur, ["x"])
        assert "x" in result
        assert "psi" in result["x"]
        assert "status" in result["x"]
```

### 9.2. Tests `drift_detector.py` (après refactoring)

```python
class TestRunDriftReport:
    """Tests pour drift_detector.run_drift_report() — PSI engine."""

    def test_returns_engine_psi(self):
        """Le rapport indique engine='psi'."""
        np.random.seed(42)
        n = 100
        ref = pd.DataFrame({c: np.random.normal(0, 1, n) for c in NUMERICAL_FEATURES})
        cur = pd.DataFrame({c: np.random.normal(0, 1, n) for c in NUMERICAL_FEATURES})
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["engine"] == "psi"

    def test_no_drift_stable(self):
        """Distributions identiques → dataset_drift=False."""
        np.random.seed(42)
        n = 300
        ref = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        cur = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["dataset_drift"] is False

    def test_drift_detected(self):
        """Prédictions décalées → drift détecté."""
        np.random.seed(42)
        n = 300
        ref = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        cur_data = {c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES}
        cur_data["xgb_speed_kmh"] = np.random.normal(55, 15, n)  # shifted
        cur_data["error_abs_kmh"] = np.abs(np.random.normal(15, 6, n))  # doubled
        cur_data["error_pct"] = np.abs(np.random.normal(35, 12, n))  # doubled
        cur = pd.DataFrame(cur_data)
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["n_drifted_features"] >= 2

    def test_empty_dataframes(self):
        """DataFrames vides → pas de crash, drift=False."""
        result = run_drift_report(
            reference_df=pd.DataFrame(),
            current_df=pd.DataFrame(),
        )
        assert result["dataset_drift"] is False
        assert result["n_ref"] == 0

    def test_details_contain_per_column_psi(self):
        """Les détails contiennent le PSI par colonne."""
        np.random.seed(42)
        n = 200
        ref = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        cur = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        result = run_drift_report(reference_df=ref, current_df=cur)
        for col in NUMERICAL_FEATURES:
            assert col in result["details"]
            assert "psi" in result["details"][col]
            assert "status" in result["details"][col]

    def test_result_json_serializable(self):
        """Le résultat est sérialisable JSON (pour INSERT dans gold.model_drift_reports)."""
        np.random.seed(42)
        n = 200
        ref = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        cur = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        result = run_drift_report(reference_df=ref, current_df=cur)
        json.dumps(result, default=str)  # ne doit pas lever

    def test_persist_and_read_roundtrip(self, mock_db_connection):
        """Insertion + lecture dans gold.model_drift_reports."""
        result = run_drift_report(...)
        ok = persist_drift_report(result, mock_db_connection)
        assert ok is True
```

### 9.3. Tests Evidently optionnel

```python
class TestEvidentlyOptional:
    """Vérifie que le code fonctionne SANS Evidently installé."""

    def test_run_drift_report_without_evidently(self, monkeypatch):
        """PSI fonctionne même si evidently n'est pas importable."""
        # Simule evidently non installé
        import sys
        monkeypatch.setitem(sys.modules, "evidently", None)
        # Le drift report doit quand même fonctionner (via PSI)
        result = run_drift_report(reference_df=ref, current_df=cur)
        assert result["engine"] == "psi"

    def test_generate_html_returns_none_without_evidently(self, monkeypatch):
        """generate_html_drift_report retourne None si evidently absent."""
        import sys
        monkeypatch.setitem(sys.modules, "evidently", None)
        html = generate_html_drift_report(reference_df=ref, current_df=cur)
        assert html is None

    @pytest.mark.skipif(
        not _evidently_available(),
        reason="evidently not installed",
    )
    def test_generate_html_returns_string_with_evidently(self):
        """Si evidently est installé, le rapport HTML est généré."""
        np.random.seed(42)
        n = 200
        ref = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        cur = pd.DataFrame({c: np.random.normal(35, 10, n) for c in NUMERICAL_FEATURES})
        html = generate_html_drift_report(reference_df=ref, current_df=cur)
        assert html is not None
        assert "<html" in html.lower()
        assert len(html) > 1000
```

### 9.4. Tests diagnostic différentiel

```python
class TestDiagnoseDrift:
    """Tests pour le diagnostic métier (widget drift_status_badge)."""

    def test_model_degraded_xgb_drifts_tomtom_stable(self):
        """XGB drift + TomTom stable → 'Modèle dégradé'."""
        report = {
            "details": {
                "xgb_speed_kmh": {"status": "significant"},
                "tomtom_speed_kmh": {"status": "stable"},
                "error_abs_kmh": {"status": "significant"},
                "error_pct": {"status": "moderate"},
                "tomtom_confidence": {"status": "stable"},
            }
        }
        status, msg = _diagnose_drift(report)
        assert status == "critical"
        assert "retrain" in msg.lower()

    def test_real_traffic_change_both_drift(self):
        """XGB + TomTom driftent → 'Changement trafic réel'."""
        report = {
            "details": {
                "xgb_speed_kmh": {"status": "significant"},
                "tomtom_speed_kmh": {"status": "significant"},
                "error_abs_kmh": {"status": "stable"},
                "error_pct": {"status": "stable"},
                "tomtom_confidence": {"status": "stable"},
            }
        }
        status, msg = _diagnose_drift(report)
        assert status == "warning"
        assert "réel" in msg.lower()

    def test_oracle_degraded(self):
        """TomTom confidence drop → 'Oracle moins fiable'."""
        report = {
            "details": {
                "xgb_speed_kmh": {"status": "stable"},
                "tomtom_speed_kmh": {"status": "stable"},
                "error_abs_kmh": {"status": "stable"},
                "error_pct": {"status": "stable"},
                "tomtom_confidence": {"status": "significant"},
            }
        }
        status, msg = _diagnose_drift(report)
        assert status == "warning"
        assert "oracle" in msg.lower() or "TomTom" in msg

    def test_all_stable(self):
        """Tout stable → ok."""
        report = {
            "details": {
                "xgb_speed_kmh": {"status": "stable"},
                "tomtom_speed_kmh": {"status": "stable"},
                "error_abs_kmh": {"status": "stable"},
                "error_pct": {"status": "stable"},
                "tomtom_confidence": {"status": "stable"},
            }
        }
        status, msg = _diagnose_drift(report)
        assert status == "ok"
        assert "stable" in msg.lower()

    def test_errors_rising_alone(self):
        """Erreurs en hausse seules → warning."""
        report = {
            "details": {
                "xgb_speed_kmh": {"status": "stable"},
                "tomtom_speed_kmh": {"status": "stable"},
                "error_abs_kmh": {"status": "moderate"},
                "error_pct": {"status": "moderate"},
                "tomtom_confidence": {"status": "stable"},
            }
        }
        status, msg = _diagnose_drift(report)
        assert status == "warning"
```

### Résumé tests

| Catégorie | Fichier | Tests | Dépendance Evidently |
|-----------|---------|-------|---------------------|
| PSI core | `tests/monitoring/test_psi.py` | 9 | Non |
| drift_detector refactored | `tests/monitoring/test_drift_detector.py` | 7 | Non |
| Evidently optionnel | `tests/monitoring/test_evidently_optional.py` | 3 | Conditionnel (`skipif`) |
| Diagnostic différentiel | `tests/monitoring/test_drift_diagnosis.py` | 5 | Non |
| **Total** | | **24** | **21 sans Evidently** |

---

## 10. Impact Docker / VPS

### Sans Evidently dans Docker (recommandé)

| Métrique | Avant | Après |
|----------|-------|-------|
| Image Docker | ~2.1 Go | ~2.1 Go (inchangé) |
| RAM runtime DAG drift | ~50 Mo (placeholder) | ~55 Mo (PSI numpy) |
| Temps DAG drift | ~2s (count seulement) | ~5-10s (PSI calcul) |
| Dépendances nouvelles | 0 | 0 |

### Avec Evidently dans Docker (optionnel, si demandé plus tard)

| Métrique | Impact |
|----------|--------|
| Image Docker | +250-400 Mo |
| RAM runtime | +80-150 Mo (chargement initial Evidently) |
| Temps DAG drift | +15-30s (Evidently report) |
| Dépendances nouvelles | 13+ (nltk, litestar, uvicorn, statsmodels, rich, typer...) |

### Recommandation

Ne PAS installer Evidently dans Docker VPS. Le PSI couvre 100% du besoin opérationnel (détection drift + diagnostic + stockage). Evidently est un luxe pour les rapports HTML visuels — usage notebook local uniquement.

Si besoin futur d'Evidently en prod : créer un container dédié `lyonflow-drift-reporter` avec ses dépendances, isolé du worker Airflow principal.
