# Demo script pas-a-pas — 20 min

## T-30 min — Pre-demo

```bash
# 1. Verifier que tout est UP
kubectl get pods -n lyonflow
# → tous Running

# 2. Test acces externes
curl -fsSL https://lyonflow.demo.jedha.fr | head -1
curl -fsSL https://api.lyonflow.demo.jedha.fr/health

# 3. Charger les onglets dans le browser, mute notifications
# 4. Backup demo en local (au cas ou le wifi tombe)
```

## T+0 — Intro (3 min)

> "Bonjour. Aujourd'hui je vais vous presenter LyonFlowFull,
> ma reponse au probleme du pilotage trafic temps reel d'une grande
> metropole. Slide d'intro, probleme, vision, persona."

## T+3 — Architecture (5 min)

Slide diagramme Medallion. Slide stack. Slide securite.

> "Cle de voute : pipeline Medallion separant donnees brutes,
> nettoyees, et features ML-ready. Chaque etage est isole, idempotent,
> auditable RGPD."

## T+8 — Demo live (8 min)

### 8.1 — Dashboard usager (1 min)

URL : `https://lyonflow.demo.jedha.fr`

> "Persona Usager. Je cherche un trajet Bellecour → Part-Dieu.
> Le systeme me propose 4 modes avec score composite temps + cout + CO2."

Cliquer "Mon Trajet" → carte multimodale s'affiche.

### 8.2 — Pro TCL (2 min)

> "Maintenant cote operateur TCL. Page 'PCC Live'.
> Rouge = bus + trafic congestionnes (bottleneck infra).
> Orange = trafic seul.
> Bleu = piste cyclable contournant les rouges."

Zoom sur quartier Guillotiere — montrer cluster rouge → diagnostic.

### 8.3 — Elu (2 min)

> "Cote elu. 'Synthese executive' : 5 KPIs sur la semaine.
> 'Avant/Apres' : impact des amenagements.
> 'Simulateur' : et si on creait une voie velo rue Vendome ?"

Lancer simulateur → impact CO2 / report modal calcule.

### 8.4 — Behind the scenes (3 min)

Ouvrir MLflow `https://mlflow.lyonflow.demo.jedha.fr`

> "Tracking experiences GNN. Comparer runs. Promotion staging→prod."

Ouvrir Airflow `https://airflow.lyonflow.demo.jedha.fr`

> "Pipeline orchestre. 9 DAGs. Trigger live `transform_silver_to_gold`."

Pendant exec, ouvrir Grafana `https://grafana.lyonflow.demo.jedha.fr`

> "Latence FastAPI p95 < 300ms, HPA replicas 1→3."

## T+16 — Technique cle (3 min)

Ouvrir VSCode / GitHub `kubernetes` branch.

> "Zoom 30s sur le SpatioTemporalGCN. GRU temporel par noeud + 2 GCN layers."

Montrer `training/stgcn/model.py` lignes 20-60.

> "Optim majeure : refactor N+1 SQL → set-based avec CTE et window functions.
> 100x speedup. `src/transformation/silver_to_gold.py`."

## T+19 — Closing (1 min)

> "Phase 1 production-ready local (commit branche `main`).
> Phase 2 manifests K8s complets (`kubernetes`).
> Phase 3 cette demo (`cloud-demo`).
> Tout est sur https://github.com/PDUCLOS/lyonflowfull.
> Questions ?"

## T+20 — Q&A

Cf `SOUTENANCE_RNCP_38777.md` section Q&A anticipees.

## Si quelque chose plante

| Probleme | Mitigation |
|----------|-----------|
| Wifi KO | Backup demo video local (mp4) |
| K8s cluster down | Screenshots fallback dans slides |
| API timeout | Switch sur instance dev secondaire VPS |
| GNN pas trained | Fallback XGBoost (toujours disponible) |
| Auth Streamlit KO | Code admin de secours dans .env.demo |
