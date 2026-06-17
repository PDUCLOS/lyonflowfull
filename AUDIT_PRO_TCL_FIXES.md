# AUDIT PRO TCL — Liste des corrections Streamlit

> Audit exhaustif du 2026-06-17. 7 pages Pro TCL + 22 widgets + data layer.
> **174 tests verts, 1 test en échec (version assert), 0 erreur import.**

---

## CRITIQUE — Crash runtime garanti

### 1. `get_bottlenecks_summary` n'existe pas dans `db_query.py`

- **Fichier** : `src/data/data_loader.py:442`
- **Symptôme** : `ImportError: cannot import name 'get_bottlenecks_summary' from 'src.data.db_query'`
- **Impact** : crash `load_bottlenecks_summary()` et `load_bottlenecks_top()`. Affecte :
  - `Pro_1_PCC_Live.py:94` — quadrant SE "Top bottlenecks" (via `cached_bottlenecks_top`)
  - `Elu_1_Synthese.py:71`, `Elu_5_Rapport.py:58`, et 5 widgets Élu
- **Fix** : créer `def get_bottlenecks_summary() -> pd.DataFrame` dans `src/data/db_query.py`. Query probable :
  ```python
  def get_bottlenecks_summary(top: int = 50) -> pd.DataFrame:
      return _df_from_query("""
          SELECT bottleneck_id, road_name, lat, lng,
                 avg_bus_delay_s, avg_traffic_speed_kmh,
                 diagnosis, n_observations, voyageurs_jour
          FROM gold.infrastructure_bottlenecks
          ORDER BY avg_bus_delay_s DESC
          LIMIT %s
      """, (top,))
  ```

---

## IMPORTANT — Bugs visibles en prod

### 2. Caractères chinois "瓶颈" dans les messages utilisateur

- **Fichiers** :
  - `dashboard/components/widgets/pro_tcl/correlation_matrix.py:70`
  - `dashboard/components/widgets/pro_tcl/segment_table.py:48`
- **Texte actuel** : `"Aucun segment瓶颈 — gold.infrastructure_bottlenecks est vide."`
- **Fix** : remplacer par `"Aucun segment bottleneck — gold.infrastructure_bottlenecks est vide."`

### 3. Test infrastructure cassé — version assert `0.1.0` vs `0.6.1`

- **Fichier** : `tests/integration/test_infrastructure.py:19`
- **Texte** : `assert s.app_version == "0.1.0"`
- **Fix** : changer en `assert s.app_version == "0.6.1"` (ou mieux, `assert s.app_version` pour ne plus casser à chaque bump)

### 4. Caption obsolète "Mode démonstration · Données simulées" sur Pro_1

- **Fichier** : `dashboard/pages/Pro_1_PCC_Live.py:122`
- **Texte** : `"PCC Live · Mode démonstration · Données simulées · Sprint 6+ : branchement PostgreSQL Gold"`
- **Fix** : remplacer par `"PCC Live · Source : PostgreSQL Gold · Sprint 8+"` (le mode démo est viré depuis Sprint 8)

---

## DETTE TECHNIQUE — Cleanup Sprint 8 "zéro mock"

### 5. `_is_demo_mode()` encore appelé dans 2 widgets Pro TCL

`_is_demo_mode()` retourne toujours `False`. Les branches `if _is_demo_mode()` sont du dead code.

| Fichier | Lignes | Action |
|---------|--------|--------|
| `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 21, 82, 89, 197, 209 | Supprimer import + simplifier les `if/else` |
| `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 110, 125, 398, 407 | Supprimer import + simplifier les `if/else` |

**Détail pipeline_management.py** :
- L82-93 : la branche `_is_demo_mode()` affiche un warning mock. Puisque `_is_demo_mode()` = `False` toujours, les L89-93 sont inatteignables. Simplifier : garder uniquement le bloc `if not is_airflow_available():` avec `st.error`.
- L197-249 : le health panel a un `if _is_demo_mode(): results = [...]` mock fallback. Dead code — supprimer.
- L209 : même logique. Dead code.

**Détail model_monitoring.py** :
- L125 : `if _is_demo_mode(): models = MOCK_MODELS` — dead code, supprimer
- L407 : idem

### 6. `MOCK_MODELS` hardcodé dans `model_monitoring.py:20-92`

- 92 lignes de mock data encore dans le fichier widget, alors que Sprint 8 dit "zéro mock dans le projet"
- Utilisé uniquement dans les branches `_is_demo_mode()` (dead code, cf. point 5)
- **Fix** : supprimer `MOCK_MODELS` et les branches mortes qui l'utilisent

### 7. Mock hardcodé dans `render_drift_panel()` (model_monitoring.py:530-547)

- `drifts = [...]` — liste mock statique au lieu de lire `gold.model_drift_reports`
- Le rapport drift réel est déjà lu dans `render_model_registry()` via `get_latest_drift_report()`
- **Fix** : refactor `render_drift_panel()` pour lire le même `get_latest_drift_report()` ou supprimer/fusionner avec la section drift existante dans `render_model_registry()`

### 8. Mock hardcodé dans `render_training_history()` (model_monitoring.py:483-486)

- `mae_speed_h60 = [2.51, 2.48, ...]` — données mockées
- **Fix** : lire MLflow runs history ou afficher `st.info("Historique via MLflow — à brancher Sprint 10+")` + supprimer les données mock

### 9. Mock hardcodé dans `render_saeiv_export()` (saeiv_export.py:36-42)

- Export SAEIV avec des KPIs hardcodés `{"line_id": "C3", "otp_pct": 78.4}`
- **Fix** : utiliser `cached_line_kpis()` pour remplir les données réelles

### 10. Mock hardcodé dans `render_alerts_feed()` (pipeline_management.py:346-349)

- Historique alertes avec dates et textes hardcodés `"2026-06-06 04:15"`
- **Fix** : lire `gold.alerts` / `rgpd.audit_log` via `get_recent_alerts()`, ou afficher `st.caption("Historique alimenté par rgpd.audit_log (Sprint 10+)")`

---

## COSMÉTIQUE — Low priority

### 11. Caption obsolète "Mode mock" dans Pro_6

- **Fichier** : `dashboard/pages/Pro_6_Pipeline_Mgmt.py:28`
- **Texte** : `"Mode mock pour démo — Sprint 6+ : branchement Airflow API + PostgreSQL."`
- **Fix** : remplacer par `"Source : Airflow REST API + PostgreSQL Gold · Sprint 8+"`

### 12. Caption obsolète "Mock — Sprint 4" dans Pro_4

- **Fichier** : `dashboard/pages/Pro_4_Simulateur.py:81`
- **Texte** : `"Simulateur fréquences · Modèle simplifié — Sprint 4 : modèle GNN/XGBoost"`
- **Fix** : `"Simulateur fréquences · Modèle simplifié · Sprint 8+"`

### 13. `_FALLBACK_MOCK_MODELS` dans `data_loader.py:961-1028`

- 67 lignes de mock MLflow models dans la couche data loader
- N'est plus référencé par aucun code (dead code)
- **Fix** : supprimer le bloc entier

### 14. OTP Heatmap fallback `85.0` magique

- **Fichier** : `dashboard/components/widgets/pro_tcl/otp_heatmap.py:67`
- `values = [otp_data[line_id].get(d, [85.0] * 24)[h] for d in selected_dates]`
- Quand une date manque, assume OTP = 85%. Devrait être `0.0` ou `None` pour signaler l'absence.

---

## RÉSUMÉ PRIORISATION

| # | Sévérité | Effort | Description |
|---|----------|--------|-------------|
| 1 | 🔴 CRITIQUE | 15 min | Créer `get_bottlenecks_summary` dans db_query.py |
| 2 | 🟠 IMPORTANT | 2 min | Fix caractères chinois (2 fichiers) |
| 3 | 🟠 IMPORTANT | 2 min | Fix test version assert |
| 4 | 🟠 IMPORTANT | 1 min | Fix caption "mode démonstration" Pro_1 |
| 5 | 🟡 DETTE | 15 min | Supprimer `_is_demo_mode()` dans 2 widgets |
| 6 | 🟡 DETTE | 5 min | Supprimer `MOCK_MODELS` dans model_monitoring |
| 7 | 🟡 DETTE | 10 min | Refactor `render_drift_panel()` sur données réelles |
| 8 | 🟡 DETTE | 5 min | Supprimer mock `render_training_history()` |
| 9 | 🟡 DETTE | 10 min | Brancher `render_saeiv_export()` sur données réelles |
| 10 | 🟡 DETTE | 5 min | Brancher `render_alerts_feed()` sur données réelles |
| 11 | ⚪ COSM | 1 min | Caption Pro_6 |
| 12 | ⚪ COSM | 1 min | Caption Pro_4 |
| 13 | ⚪ COSM | 2 min | Supprimer `_FALLBACK_MOCK_MODELS` dead code |
| 14 | ⚪ COSM | 2 min | Fix OTP heatmap fallback 85.0 |

**Total estimé : ~75 min**

---

## CE QUI MARCHE BIEN (pas toucher)

- Tous les imports OK (22 widgets, 7 pages)
- `__init__.py` exports alignés sur tous les fichiers
- `db_query.py` : 28/29 fonctions présentes (seule `get_bottlenecks_summary` manque)
- `data_cache.py` : tous les wrappers `@st.cache_data` fonctionnels
- `line_kpis.py` : widget Sort + Explore complet, branché DB
- `gnn_map.py` : carte pydeck fonctionnelle, flag-gated
- `pipeline_management.py` : Airflow API + health checks + freshness branchés
- `model_monitoring.py` : MLflow live + drift PSI + data quality panel
- Ruff : 0 erreur sur les fichiers Pro TCL
- 174 tests verts / 1 failed (version assert trivial)
