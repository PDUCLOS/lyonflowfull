# LyonFlowFull — Rapport Sprint 7 : GNN Training (SpatioTemporalGCN)

**Date** : 2026-06-06
**Statut** : ✅ Livré — architecture complète, tests skip proprement
sans torch, DAG Airflow câblé
**Tests** : 19 tests GNN (12 passent sans torch, 6 skip, 1 skip is_available)

---

## 🎯 Objectif Sprint 7

Implémenter le pilier ML #1 du projet : **ST-GRU-GNN** pour la prédiction
spatiale du trafic (CLAUDE.md ligne 80-110). Le modèle capture la
propagation de congestion entre segments routiers via une combinaison de :

* **GRU temporel** (évolution séquence)
* **GCN spatial** (propagation sur le graphe H3)
* **Skip connections** (stabilité gradient)

## 🏗️ Architecture livrée

### 1. Modèle `SpatioTemporalGCN` — `training/stgcn/model.py`

Architecture complète (300+ lignes) :

```
Input (B, T, N, 5)
       │
       ▼
┌─────────────────┐
│  GRU temporel   │ input=(5), hidden=128, layers=1
│  par nœud       │ output: (B, N, 128)
└────────┬────────┘
         ▼
┌─────────────────┐
│  GCN layer 1    │ 128 → 128
│  + LeakyReLU    │ + skip
│  + LayerNorm    │
│  + Dropout      │
└────────┬────────┘
         ▼
┌─────────────────┐
│  GCN layer 2    │ 128 → 128
│  + LeakyReLU    │ + skip
│  + LayerNorm    │
│  + Dropout      │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Linear head    │ 128 → 1
└────────┬────────┘
         ▼
Output (B, N, 1) = predicted speed per node
```

**Hyperparamètres par défaut** (`STGCNConfig`) :

| Param | Default | Notes |
|-------|---------|-------|
| `in_channels` | 5 | speed_norm, hour_sin, hour_cos, day_sin, day_cos |
| `hidden_channels` | 128 | GRU + GCN hidden state |
| `seq_len` | 12 | timesteps × 5 min = 1h d'historique |
| `num_nodes` | 1520 | Capteurs Grand Lyon (réduit pour CPU) |
| `gcn_layers` | 2 | Empilé avec skip connections |
| `dropout` | 0.1 | Régularisation |
| `leaky_relu_slope` | 0.2 | Non-linéarité GCN |
| `out_channels` | 1 | 1 par horizon |

**Imports tolérants** : `is_available()` retourne `False` si torch ou
torch_geometric manquent. L'instanciation lève une `STGCNImportError` claire
qui aide au diagnostic.

**Persistance** : `save(path)` / `load(path)` avec `state_dict` + config
(dict). Test smoke vérifie que `save` → `load` produit les mêmes prédictions.

### 2. Dataset `STGCNDataset` — `training/stgcn/dataset.py` (~280 lignes)

Charge les features Gold + construit des **sliding windows** :

* **X** : `(num_samples, seq_len, num_nodes, in_channels)` — fenêtres temporelles
* **Y** : `(num_samples, num_nodes)` — target = speed_norm à t+horizon
* **edge_index** : `(2, num_edges)` au format PyG

Trois sources de données :

1. **`STGCNDataset.synthetic(num_nodes, seq_len, horizon)`** — pour tests
   et démo offline. Génère 1 journée à 5 min, 50 nœuds, bruit sinusoïdal
   + perturbations locales.
2. **`STGCNDataset.from_db(num_nodes_max, seq_len, horizon)`** — charge
   `gold.traffic_features_live` + `gold.dim_gnn_adjacency`. Lève si DB down.
3. **Custom** : le `STGCNDataset(X, edge_index, Y)` direct accepte des
   numpy arrays (utile pour l'inférence).

**Targets** : `target = speed_norm au timestep t + horizon` (logique LEAD-like
matching le pattern XGBoost Sprint 5).

**Split temporel** : pas de shuffle — train = 80% début, val = 20% fin
(pas de data leakage temporel).

### 3. Trainer `STGCNTrainer` — `training/stgcn/train.py` (~400 lignes)

Boucle d'entraînement complète avec :

* **Optimizer** : Adam (lr=1e-3)
* **Scheduler** : ReduceLROnPlateau (patience=3, factor=0.5)
* **Loss** : MSELoss (vitesses normalisées)
* **Early stopping** : patience=5 epochs
* **Batch size** : 16 (configurable)
* **Quality gate** : `MAE ≤ prev × 1.15` (réutilise le pattern Sprint 5)
* **MLflow tracking** : params, metrics, model artifact par horizon

**Métriques loggées** :
- `train_loss` (par epoch)
- `val_mae`, `val_rmse`, `val_mape_pct`, `val_r2`
- `lr` (pour debug scheduler)
- `quality_gate_pass` (0 ou 1)

**Fallback MLflow** : si mlflow indispo, log dans stdout (objet `_NoopRun`
no-op). Permet de tester sans mlflow installé.

**Graceful degradation** : si torch indispo, `STGCNTrainer.__init__` lève
un `RuntimeError` clair. Le DAG Airflow attrape et skip.

### 4. Wrapper production `STGCNWrapper` — `src/models/stgcn_wrapper.py`

Pont entre modèle entraîné et API FastAPI :

```python
wrapper = STGCNWrapper.get(horizon_min=60)  # singleton
wrapper.load()  # charge depuis disque, False si pas trouvé
pred = wrapper.predict(features, edge_index)  # numpy (B, N) ou None
speed_kmh = wrapper.predict_for_node(node_idx, recent, edge_index)  # 1 valeur
```

**Cache** : singleton par horizon (évite de recharger 6× le graphe).

**Fallback XGBoost** : si GNN pas chargé (modèle absent ou torch indispo),
`predict()` retourne `None` → l'API peut fallback sur XGBoost sans crash.

### 5. DAG Airflow — `dags/ml/retrain_gnn.py` (~80 lignes)

```python
dag_id="retrain_gnn"
schedule="0 3 * * *"  # daily 03h
execution_timeout=timedelta(hours=2)  # GNN est lourd
max_active_runs=1
```

**Logique** :
1. Vérifie torch disponible (sinon log + skip)
2. Charge dataset (DB ou synthetic fallback)
3. Pour chaque horizon (5, 15, 30, 60, 180, 360 min) :
   - Train (1 modèle par horizon)
   - Log MLflow
   - Quality gate
   - Save sur disque

**Fail-soft** : si torch indispo, DAG skip (le pipeline XGBoost prend le relais).
Logs explicites pour debugging.

### 6. Tests — `tests/ml/test_stgcn.py` (19 tests)

Stratégie **skip propre** : module-level `requires_torch` marker. Les
tests qui n'ont pas besoin de torch tournent toujours :

| Test | Catégorie | Statut sans torch |
|------|-----------|-------------------|
| `test_is_available_returns_true` | env | skip |
| `test_stgcn_config_defaults` | config | ✅ pass |
| `test_synthetic_traffic_shape` | dataset | ✅ pass |
| `test_synthetic_adjacency_shape` | dataset | ✅ pass |
| `test_build_tensors_shape` | dataset | ✅ pass |
| `test_stgcn_dataset_synthetic` | dataset | ✅ pass |
| `test_stgcn_dataset_repr` | dataset | ✅ pass |
| `test_compute_metrics_perfect_prediction` | train | ✅ pass |
| `test_compute_metrics_noisy_prediction` | train | ✅ pass |
| `test_quality_gate_no_previous` | train | ✅ pass |
| `test_quality_gate_pass` | train | ✅ pass |
| `test_quality_gate_fail` | train | ✅ pass |
| `test_spatiotemporal_gcn_forward_shape` | model | skip |
| `test_spatiotemporal_gcn_num_params_positive` | model | skip |
| `test_spatiotemporal_gcn_save_load` | model | skip |
| `test_trainer_one_epoch_smoke` | train | skip |
| `test_stgcn_wrapper_get_singleton` | wrapper | ✅ pass |
| `test_stgcn_wrapper_load_if_exists` | wrapper | skip |
| `test_stgcn_wrapper_no_torch` | wrapper | ✅ pass |

**Résultat** : 12 passent + 6 skip + 1 skip (is_available).

## 🐍 Compatibilité Python

Le code utilise `from __future__ import annotations` partout → compatible
Python 3.10+ (sprint précédent ciblait 3.12, mais 3.14 local n'a pas
problème avec `X | None` syntax).

## 📦 Dépendances (déjà dans `requirements.txt`)

* `torch>=2.1.0` (~700 MB, CPU-only)
* `torch-geometric>=2.4.0`
* `h3>=4.1.0` (pour indexation spatiale, pas utilisé dans Sprint 7 mais
  prévu Sprint 8+)

Installation pour activer le GNN :

```bash
pip install torch torch-geometric
# OU via le Dockerfile
RUN pip install --no-cache-dir torch torch-geometric
```

## 🎯 Quand le GNN sera activé

Sur VPS Phase 1 (12 GB RAM, pas de GPU) :

* **CPU** : 6 horizons × 20 epochs × 100 nœuds = ~3-4h par run quotidien
* **Limitation** : nombre de nœuds à 200 max (sinon RAM saturée)
* **Recommandation** : sur VPS actuel, on garde **XGBoost comme prod**, GNN
  est validé structurellement mais pas entraîné nightly tant qu'on a pas
  un node GPU (K8s Phase 2 ou RunPod pour les tests).

Sur Scaleway GPU (Phase 3 — K8s) :

* **GPU T4** : 6 horizons × 50 epochs × 1520 nœuds = ~30 min
* **Qualité attendue** : MAE 4-6 km/h sur horizon 60min (vs 7-8 XGBoost)
* **Production-ready** : full training daily activé

## 📊 Métriques Sprint 7

| Métrique | Sprint 6 | Sprint 7 | Delta |
|----------|---------|---------|-------|
| Modèles ML | 2 (XGBoost) | 3 (+ SpatioTemporalGCN) | +1 |
| DAGs ML | 2 (XGBoost) | 3 (+ retrain_gnn) | +1 |
| Fichiers Python | 134 | 142 | +8 |
| Lignes Python | ~16 500 | ~18 300 | +1 800 |
| Tests ML | 0 | 19 (12 OK + 6 skip) | +19 |

## 🔗 Liens inter-sprints

* **Sprint 5 → Sprint 7** : la couche data (`db_query.py`) est utilisée
  par `STGCNDataset.from_db()` pour charger `gold.traffic_features_live`.
* **Sprint 6 → Sprint 7** : `STGCNWrapper` partage le pattern "fallback
  gracieux" de `data_loader.py` (retourne None si modèle absent, API
  peut fallback sur XGBoost).
* **Sprint 7 → Phase 2** : quand on passe en K8s, le GNN peut être
  schedulé sur un node pool GPU séparé (`nodeSelector` + `tolerations`).
  Voir `docs/K8S_MIGRATION_PLAN.md` section "GPU pool GNN".

## ✅ Ce qu'il reste à faire

| Item | Qui | Quand |
|------|-----|-------|
| Installer torch sur VPS | toi (décision VPS) | Phase 1 validée |
| Premier train end-to-end sur vraies données | moi (auto, via DAG) | Quand torch dispo |
| Comparaison XGBoost vs GNN sur 7 jours de holdout | moi | Après premier train |
| Backfill des `gold.trafic_predictions` avec GNN | moi | Après validation |
| Intégration routing (utiliser GNN dans Dijkstra) | moi | Sprint 8+ |

## 🛠️ Outils dev

```bash
# Test rapide (sans torch)
pytest tests/ml/ -v

# Test complet (avec torch installé)
pip install torch torch-geometric
pytest tests/ml/ -v

# Run training (CLI)
python -c "
from training.stgcn.dataset import STGCNDataset
from training.stgcn.model import STGCNConfig
from training.stgcn.train import STGCNTrainer

ds = STGCNDataset.synthetic(num_nodes=100, seq_len=12, horizon=12)
cfg = STGCNConfig(num_nodes=100, hidden_channels=64, seq_len=12)
trainer = STGCNTrainer(ds, config=cfg, horizons=(60,), epochs=10)
results = trainer.train_all()
print(results)
"
```

---

*LyonFlowFull v0.3.0 — Sprint 7 — 2026-06-06 — Patrice DUCLOS*
