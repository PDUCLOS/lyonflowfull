# Sprint 9 — Summary

**Date:** 2026-06-12
**Branche:** `sprint11-eludashboard` (contexte VPS)

---

## 1. Tests E2E — État

### API (tests/ml/ — exécutés depuis le host avec `.venv`)

| Fichier | Résultat | Détail |
|---------|----------|--------|
| `test_api_health.py` | **PASS** (3/3) | `/health` → 200, structure JSON, `/bottlenecks` → 401 sans clé |
| `test_api_itinerary_endpoint.py` | **PASS** (1/1) | Itinéraire + vérification auth |
| SKIP | 3 tests | `LYONFLOW_API_KEY` absent en local |

### Playwright / Streamlit (lancés via `docker compose exec api pytest /tmp/...`)

| Fichier | Résultat | Cause |
|---------|----------|-------|
| `test_accueil_redirect.py` | **PASS** | Redirect persona fonctionnel |
| `test_elu_roi.py` | **FAIL** | Combobox supprimé par refactoring sprint10 sidebar |
| `test_persona_switcher.py` | **FAIL** | Combobox supprimé par refactoring sprint10 sidebar |

**Récap:** 2 PASS, 2 FAIL, 3 SKIP.
**Action requise:** Mettre à jour les sélecteurs Playwright vers les nouveaux composants sidebar (sprint10 a supprimé `get_by_role("combobox")`).

### Tests ML Unitaires

| Fichier | Tests | Résultat |
|---------|-------|----------|
| `tests/ml/test_xgboost_speed.py` | 14 | **PASS** |
| `tests/ml/test_xgboost_velov.py` | 11 | **PASS** |
| `tests/ml/test_velov.py` | 10 | **PASS** |
| **Total** | **35** | **35/35 PASS** |

---

## 2. Dettes XGBoost Corrigées

### `src/models/xgboost_speed.py`

| # | Type | Description | Correction |
|---|------|-------------|------------|
| 1 | Double assignation | `model_dir` en paramètre ET `self.model_dir` dans `__init__` | Renommé `self._model_dir` (attribut privé) |
| 2 | Variable indéfinie | `params` référencé dans `train_one()` block model card — jamais défini | Remplacé par `card_params` avant `generate_xgboost_card()` |

### `src/models/xgboost_velov.py`

| # | Type | Description | Correction |
|---|------|-------------|------------|
| 1 | Argument redondant | `_load_training_data()` appelle `execute_query(query, ())` avec `()` explicite | Supprimé: `execute_query(query)` (défaut `()`) |

### `src/ingestion/velov.py`

| # | Type | Description | Correction |
|---|------|-------------|------------|
| 1 | NameError latent | `import logging` dans le bloc `except` — `logger` référencé avant assignment | Déplacé `import logging` + `logger = logging.getLogger(__name__)` au niveau module |

### Schéma `gold.traffic_features_live` aligné

`FEATURE_COLS` (11 colonnes) aligné sur schéma v0.3.1:
`speed_kmh`, `lag_1`, `lag_2`, `lag_3`, `rolling_mean_3`, `sin_hour`, `cos_hour`, `temperature_2m`, `precipitation`, `is_vacances`, `is_ferie`.

---

## 3. Commit Hashes

### Sprint 9 — Refacto XGBoost

```
97bbd53 test(ingestion/velov): add unit tests for logger, instantiation, and fetch_raw
a4dddd5 fix(ingestion/velov): move logger to module-level, remove import in except
0606f40 test(models/xgboost_velov): add unit tests for load, predict, and SQL pattern
01dbf88 fix(models/xgboost_velov): rename self.model_dir, remove redundant execute_query arg
2f56184 test(models/xgboost_speed): add unit tests for load, predict, and feature cols
332b1d2 fix(models/xgboost_speed): rename self.model_dir -> self._model_dir, fix undefined params
```

### Sprint 10 — Favoris Multimodaux

```
6013b99d docs: sprint10-summary.md — bilan Sprint 10 favoris multimodaux
4e1c4262 feat(reco): add multimodal alternatives for favorites (Sprint 10)
19f650c9 feat(user): persist favorites in DB, add CRUD API
```

---

## 4. Recommandations Sprint 10 — User Favorites

Sprint 10 (favoris multimodaux) a été complété et mergé sur `main`.

### Ce qui a été livré

- **Persistance DB:** table `user_favorites` avec ajout/suppression/liste des favoris
- **API CRUD:** `POST /api/user/favorites`, `GET /api/user/favorites`, `DELETE /api/user/favorites/{id}`
- **Recommandations multimodales:** alternatives TC, piéton, velov pour chaque favori
- **UI Streamlit:** page `Favoris` dans le dashboard

### Points d'attention

1. **Tests Playwright cassés:** les sélecteurs `get_by_role("combobox")` dans `test_elu_roi.py` et `test_persona_switcher.py` ne correspondent plus au DOM après le refactoring sidebar sprint10. Mettre à jour avec les nouveaux sélecteurs.
2. **API Key tests:** 3 tests skipés (`LYONFLOW_API_KEY` absent). À exécuter en intégration continue.
3. **Couverture e2e Favoris:** pas de test Playwright pour la page Favoris. À ajouter.
4. **MLflow fallback:** 1 test FAIL `test_load_mlflow_models_returns_list` avec `force_mock=True` → 0 models. Vérifier `data_loader.py`.

---

*Synthèse générée le 2026-06-12 depuis les deliverable.md des tâches e2e-run et refacto-xgboost.*