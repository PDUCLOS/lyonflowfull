# LyonFlow : fiche portfolio vérifiée

> Plateforme MLOps de prédiction du trafic multimodal lyonnais (H+1h).
> Dépôt : https://github.com/PDUCLOS/lyonflowfull (branche `feat/vitrine-lyonflow`).
> Variante : https://github.com/PDUCLOS/databrickslyonflow (citée, non vérifiée ici).
> Vérifications faites le **27/10/2026** sur Windows 11, Ryzen 9 3900X, 32 Go, Python 3.12.3, xgboost 3.4.1.
> Ce document distingue strictement ce qui a été **mesuré dans cette session** de ce qui est **repris du dépôt sans revérification**.

## 1. En une phrase

LyonFlow collecte 9 flux open data de la Métropole de Lyon avec Airflow et les raffine en Medallion
(Bronze → Silver → Gold) sur PostgreSQL 16 + PostGIS + pgRouting. Il prédit la vitesse du trafic et la
disponibilité Vélo'v à H+1h avec XGBoost quantile (P10/P50/P90), suit les modèles dans MLflow, surveille
la dérive par PSI et restitue le tout via FastAPI et un dashboard Streamlit à 3 personas.

## 2. Quelle version tourne sur la machine ? (écart important)

Les conteneurs `lyonflow-*` en marche dans Docker Desktop **ne proviennent pas de ce dépôt**.
Leur label `com.docker.compose.project.working_dir` pointe vers `M:\Architect-IA-final-project-main`,
un autre projet LyonFlow, non versionné dans git :

| | Stack en marche (`Architect-IA-final-project-main`) | `lyonflowfull` (ce dépôt) |
|---|---|---|
| Modèle | ST-GRU-GNN (PyTorch Geometric) + Ray + Optuna | XGBoost quantile |
| DAGs | 2 (`dag_pipeline.py`, `dag_monitoring.py`) | 27 (+1 legacy) |
| Base | `postgres:15-alpine` (sans PostGIS) | `pgrouting/pgrouting:16-3.5-3.7.3` |
| MLflow | `mlflow:latest`, **registre vide** (seule l'expérience « Default ») | MLflow 2.12.1 |
| Autres | Ray head/worker, ngrok | MinIO, Nginx, Prometheus/Grafana |

Constats sur cette stack (lecture seule, aucun conteneur redémarré ni modifié) :
- Airflow 2.9.1 : `/health` → metadatabase `healthy`, scheduler `healthy`.
- MLflow : `registered-models/search` → `{}` (0 modèle) ; 1 expérience « Default ».
- Streamlit : HTTP 200 sur le port 8501.
- La liste des DAGs (API Airflow) et le contenu Postgres n'ont pas été lus : les identifiants par défaut
  du compose sont refusés. Je n'ai pas cherché d'autres identifiants.

**Conséquence** : aucune capture, aucune mesure de cette stack n'est attribuée à `lyonflowfull`.
Toutes les vérifications ci-dessous portent sur le code de ce dépôt, lancé localement sans sa base.

## 3. Chiffres du portfolio : vérification

| Affirmation (fiche `projects.py`, slug `lyonflow`) | Vérifié ici | Verdict |
|---|---|---|
| 27 DAGs Airflow (25 actifs) | 28 appels `DAG(...)` dans `dags/`, dont 1 legacy (`dags/legacy_github`) → **27**. Un seul porte « PAUSED » dans sa description (`retrain_xgboost_speed`). L'état « actif » réel est dans la base Airflow du VPS, non accessible. | ✅ 27 confirmé · « 25 actifs » non vérifiable |
| 620 tests pytest | **674 collectés** dans la config du dépôt : 650 verts, 1 ignoré, 23 d'intégration désélectionnés. 689 avec les dossiers exclus (e2e, etc.). | ⚠️ à mettre à jour : 650 verts / 674 |
| 9 sources open data | Non recomptées une par une. `collect_bronze` déclare « 6 sources temps réel », plus TomTom, vigilance, calendriers = 9. | ✅ cohérent |
| Retrain XGBoost toutes les 30 min | Vitesse : entraînement **quotidien** à 03:38 (`dag_daily_speed_train`) ; le DAG horaire est en pause depuis le 01/07/2026. Vélo'v : **horaire** à :50. | ❌ inexact, à corriger |
| Inférence toutes les 15 min | `dag_inference_xgboost` : `*/15 * * * *` | ✅ |
| Drift PSI maison + Evidently | `src/monitoring/psi.py` ; `daily_drift_report` à 05:30 utilise le moteur PSI ; Evidently est une dépendance optionnelle (`extra drift-reports`). | ✅ (Evidently optionnel) |
| 7 groupes d'alertes | `monitoring/prometheus/rules/` : 7 groupes, 17 règles. | ✅ |
| Prometheus / Grafana / Alertmanager | `docker-compose.monitoring.yml` (Prometheus 2.54.1, Alertmanager 0.27, Grafana 11.2). Le README dit pourtant « Prometheus retiré Sprint 15+ ». | ✅ code · ⚠️ README contradictoire |
| 18 pages / 59 widgets | 18 fichiers dans `dashboard/pages/` (16 de persona + RGPD + À propos) + `Accueil.py`. Widgets non recomptés. | ✅ 18 pages |
| MLflow : 6 modèles, stage Production | Non vérifiable (registre du VPS). Le code charge `models:/xgb_speed_h60/Production` avec repli sur un `.pkl` local. | ⏸ non vérifié |
| MAE 5,8 → 3,2 (−45 %) | Dépôt de travail privé, non accessible. | ⏸ non vérifié |
| Benchmark MAE 6,97 · R² 0,71 | Notebook du dépôt privé, absent d'ici. | ⏸ non vérifié |
| ~458 stations Vélo'v, ~101 k arêtes OSM | Valeurs du README, données non chargées ici. | ⏸ non vérifié |
| Cible Kubernetes sur branche dormante | Branche `origin/kubernetes` (Phase 2, juin 2026). Sa base kustomize **ne se construisait plus** (référence à `base/secrets` absent). | ✅ existe · réparée ici |

## 4. Mesures réalisées (27/10/2026)

Scripts : `scripts/vitrine/measure.py`, `scripts/vitrine/count_dags.py`. Résultats bruts :
`docs/measures/measures.json`, `docs/measures/dags_inventory.json`, `docs/measures/pytest_default.txt`.

| Mesure | Résultat | Conditions |
|---|---|---|
| pytest (addopts du dépôt) | **650 passed, 1 skipped, 23 deselected, 0 failed**, 18,4 s ; 653 après ajout de 3 tests de sécurité | venv `requirements.txt` + pytest ; 1 skip = PostgreSQL absent |
| Entraînement `XGBoostSpeedModel.train_one` (3 modèles quantiles, 200 arbres, prof. 6) | **8,19 s** | 49 985 lignes **synthétiques**, 11 features, CPU |
| `predict()` d'un capteur (P10 + P50 + P90) | **médiane 5,43 ms · p95 15,29 ms · p99 46,57 ms** | 1 000 appels, DataFrame d'une ligne |
| Prédiction P50 en lot | **14,78 ms / 10 000 lignes** | même modèle |
| Modèle sérialisé | **2 680 Ko** | `xgb_speed_h60.pkl` (dict de 3 modèles) |
| PSI, même loi | 0,0007 → stable | `compute_psi`, 20 000 points, 10 buckets |
| PSI, décalage +0,25 σ | 0,0626 → stable | idem |
| PSI, décalage +0,5 σ | **0,2377 → significant** | idem |
| PSI, décalage +1 σ | 0,9491 → significant | idem |
| PSI, variance ×2 | 0,4794 → significant | idem |
| `compute_dataset_drift`, 2 colonnes | 13,2 ms ; 1 colonne en dérive sur 2 → `dataset_drift=false` (règle : > 50 %) | |
| `GET /health` (FastAPI TestClient) | **médiane 26,9 ms · p95 55,1 ms**, 200 OK, `db=false` | 200 appels, la latence inclut l'échec de connexion Postgres |
| `kubectl kustomize` overlays/dev | 1 759 lignes, 0 erreur | kubectl client de Docker Desktop |
| `kubectl kustomize` overlays/prod | 1 972 lignes, 0 erreur | idem |

**Avertissement** : le jeu synthétique (cycle journalier + bruit) mesure le **coût** du modèle, pas sa
**qualité**. Les erreurs obtenues dessus ne sont volontairement pas publiées.

## 5. Corrections apportées (branche `feat/vitrine-lyonflow`)

1. **Tests non portables sous Windows** : `tests/persona/test_real_durations.py` et
   `tests/routing/test_audit_sprint22.py` lisaient un fichier source sans encodage (cp1252 par défaut sous Windows) :
   `UnicodeDecodeError`. Ajout de `encoding="utf-8"`. Résultat : 649 → 650 verts.
2. **Page « Statut du service » qui plantait** (`dashboard/pages/Usager_5_Statut_Service.py`) : base injoignable,
   la page affichait une trace Python complète (`DashboardDataError`). Les 3 autres voyants passaient déjà en
   « Indéterminé ». Le voyant Alertes et le bloc « Derniers incidents » suivent désormais la même règle.
   Vérifié visuellement (`docs/screenshots/streamlit-statut-service.png`).
3. **`.gitignore`** : `docs/` était entièrement ignoré (choix RNCP Sprint 23). La règle est conservée, avec
   une exception pour les seuls fichiers de la vitrine (`index.html`, `PORTFOLIO.md`, `architecture.drawio`,
   `diagrams/`, `screenshots/`, `video/`, `measures/`).

4. **Sécurité (revue automatique des manifestes)** : sans authentification, l'UI Prometheus/Alertmanager aurait été publique.
   Le chart Airflow aurait créé un compte `admin/admin` avec une UI publique, et `--forwarded-allow-ips=*` acceptait n'importe quel proxy.
   Corrigé dans `deploy/k8s` (détail dans `deploy/k8s/README.md`). Dans l'application elle-même,
   `src/api/middleware/rate_limit.py` prenait la **première** IP de `X-Forwarded-For`, que le client
   choisit : le rate limit (dont l'anti brute-force du login) était contournable. Il prend maintenant la dernière,
   ajoutée par nginx. 3 tests ajoutés (`tests/security/test_rate_limit_client_ip.py`) : suite **653 verts**.

Extrait exact du correctif n° 2 :

```python
def _kpi_alerts() -> dict | None:
    """KPI #4 — Alertes actives 6h.

    Comme les 3 autres voyants : si la base ne répond pas, le voyant passe
    en « Indéterminé » au lieu d'afficher une trace Python à l'usager.
    """
    try:
        df = cached_recent_alerts(hours=6, limit=50)
    except DashboardDataError:
        logger.warning("Statut service : alertes indisponibles (DB injoignable)")
        return None
    n_total = len(df)
    n_critical = int((df["severity"] == "critical").sum()) if "severity" in df.columns else 0
    return {"n_total": n_total, "n_critical": n_critical}
```

## 6. Kubernetes : `deploy/k8s`

Réveil de la branche `kubernetes` sous forme kustomize `base` + `overlays/dev` + `overlays/prod`
+ `components/monitoring`, réaligné sur `main` :

| Branche dormante | `deploy/k8s` | Raison |
|---|---|---|
| `postgis/postgis:16-3.4` | `pgrouting/pgrouting:16-3.5-3.7.3` | `pgr_dijkstra` est utilisé par `main` |
| images `-api` / `-dashboard` | une image `lyonflowfull-app:0.5.0` | même Dockerfile, comme en Compose |
| CronJob GNN GPU, Redis | supprimés | retirés de `main` |
| `base/secrets` manquant → build KO | Secret factice généré en dev, SealedSecret en prod | aucun secret dans le dépôt |
| `commonLabels` | `labels` | déprécié |
| monitoring dans la base | `Component` activé en prod | CRD Prometheus Operator absentes en dev |

Extrait exact (`deploy/k8s/overlays/prod/kustomization.yaml`) :

```yaml
resources:
  - ../../base

components:
  - ../../components/monitoring
```

Validation : `kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/overlays/{dev,prod}`
(le flag permet de garder `deploy/init-db.sql` comme source unique du schéma).

**Reste à faire** : publier l'image `ghcr.io/pduclos/lyonflowfull-app`, manifeste MinIO, `ClusterIssuer`
cert-manager, valider les DAGs sous KubernetesExecutor (écrits pour LocalExecutor + `/tmp/models`),
migrer le dump du VPS, `kubectl apply --dry-run=server` puis `apply` sur un cluster.
**Aucun pod n'a été démarré** dans cette session (pas de cluster sur la machine).

## 7. Limites et défauts constatés (non corrigés)

- `POST /api/v1/recommend` renvoie un **exemple codé en dur** (commentaire `# Placeholder` dans `src/api/main.py`).
- `GET /api/v1/models` renvoie, quand MLflow est injoignable, des **métriques figées** (MAE 1,96, R² 0,947 ;
  Vélo'v MAE 4,2, R² 0,331) présentées comme « Production ». Ce sont des valeurs écrites dans le code,
  pas des mesures : à ne pas citer.
- Accueil Streamlit : une balise `</div>` s'affiche en texte sous les cartes Pro TCL et Élu, et le texte des cartes est tronqué.
- Versions incohérentes : badge README 0.12.1, `/health` 0.11.0, OpenAPI 0.6.1.
- `tests/widgets/test_horizon_h1h_only.py` contient des chemins macOS absolus (déjà exclu par `pyproject.toml`).
- Le README publie l'adresse IP du VPS. Je ne l'ai pas reprise ici ; à retirer du README.
- Serveur unique : pas de haute disponibilité.
- `XGBoostSpeedModel.train_one` tente de générer une « model card » en se connectant à `localhost:5432` même
  hors production (échec non bloquant, visible dans les logs de mesure).

## 8. Ce qui n'a pas pu être vérifié

- Le fonctionnement en production sur le VPS (collecte réelle, DAGs actifs, sauvegardes, TLS, health checks).
- Toute métrique de **précision** des modèles (MAE, R², −45 %), et le registre MLflow de production.
- Les 23 tests d'intégration et les tests e2e Playwright (exigent la stack complète et des navigateurs Playwright).
- Le dashboard avec données réelles : les captures montrent l'application sans base (états « indisponible »).
- La variante Databricks (`databrickslyonflow`).
- Un `docker compose up` de la stack `lyonflowfull` : non lancé, car la VM Docker (8 Go) est déjà occupée par l'autre stack LyonFlow et l'hôte n'avait qu'environ 3,7 Go de RAM libre.

## 9. Médias produits

| Fichier | Contenu |
|---|---|
| `docs/index.html` | Vitrine GitHub Pages (thème clair/sombre, responsive, vérifiée à 1 440 px et 390 px sans défilement horizontal) |
| `docs/architecture.drawio` | 3 pages : vue d'ensemble, cycle MLOps, cible Kubernetes (généré par `scripts/vitrine/build_drawio.py`) |
| `docs/diagrams/architecture-p{1,2,3}.png` | Exports draw.io CLI (échelle 1,5), relus visuellement : flèches orthogonales, sans croisement |
| `docs/screenshots/streamlit-accueil.png` | Accueil Streamlit réel (3 personas) |
| `docs/screenshots/streamlit-notre-modele.png` | Page Usager « Notre modèle » |
| `docs/screenshots/streamlit-statut-service.png` | Page « Statut du service » après correctif |
| `docs/screenshots/api-swagger.png` | Swagger FastAPI (9 routes) |
| `docs/video/lyonflow-promo.mp4` | 1 min 45 s (105,2 s), 1920×1080 H.264 + AAC, **9,7 Mo**, narration Hortense, 10 scènes |
| `docs/video/poster.png` | Affiche de la vidéo |

Captures prises avec Edge headless piloté par DevTools (`scripts/vitrine/cdp_shot.py`), sur l'API (port 48701)
et Streamlit (port 48702) lancés depuis ce dépôt avec une base volontairement injoignable.

## 10. Extraits de code exacts

`src/monitoring/psi.py` : terme PSI protégé contre `log(0)` :

```python
def _safe_psi_term(pct_ref: float, pct_curr: float, eps: float = 1e-6) -> float:
    """Un terme de la somme PSI, protégé contre log(0) et division par 0.

    Convention : si pct_curr == 0 et pct_ref == 0, on ignore le terme
    (les deux bins sont vides). Si pct_curr == 0 et pct_ref > 0, on
    utilise pct_curr = eps pour pouvoir calculer le log.
    """
    if pct_ref < eps and pct_curr < eps:
        return 0.0
    if pct_curr < eps:
        pct_curr = eps
    if pct_ref < eps:
        pct_ref = eps
    return (pct_curr - pct_ref) * np.log(pct_curr / pct_ref)
```

`src/models/xgboost_speed.py` : intervalles de confiance par régression quantile :

```python
        quantiles = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
        models: dict[str, xgb.XGBRegressor] = {}
        metrics: dict[str, float] = {}
        for label, alpha in quantiles.items():
            model = xgb.XGBRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                objective="reg:quantileerror",
                quantile_alpha=alpha,
                random_state=42,
                n_jobs=-1,
            )
```

## 11. Suggestions pour la fiche portfolio

- KPI « 620 tests pytest » → « 650 tests verts » (674 collectés).
- « retrain XGBoost toutes les 30 min » → « entraînement quotidien (vitesse) et horaire (Vélo'v), inférence toutes les 15 min ».
- `iac="p"` : la cible Kubernetes est maintenant **réveillée et validée par kustomize** dans `deploy/k8s` (non déployée).
- Limite « cible Kubernetes sur branche dormante » → « cible Kubernetes rendue (kustomize), pas encore déployée ».
- Nouveau lien possible : vitrine `docs/index.html` (après activation GitHub Pages sur la branche fusionnée).
