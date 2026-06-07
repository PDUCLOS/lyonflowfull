# Soutenance RNCP 38777 — Architecte en Intelligence Artificielle (Jedha)

## Sujet
LyonFlowFull — MLOps end-to-end pour la prediction et l'analyse du
trafic multimodal sur la Metropole de Lyon.

## Pitch 30 secondes

> Comment piloter le trafic d'une metropole en temps reel ? J'ai construit
> une plateforme MLOps qui ingere 8 sources publiques toutes les 5 minutes,
> entraine 3 modeles ML (XGBoost + GNN spatial) et propose des
> recommandations multimodales aux usagers, operateurs et elus de Lyon.
> Le tout reproductible en local via Docker, scalable via Kubernetes,
> et conforme RGPD.

## Story demo (20 min)

### Act I — Le probleme (3 min)
1. Slide : Lyon, 600k habitants, 1100 capteurs trafic, 458 stations Velov,
   300+ vehicules TCL temps reel
2. Probleme : info eparpillee, pas de prediction unifiee, decisions
   politiques basees sur le ressenti
3. Vision : un seul cockpit, 3 personas (Usager / Pro TCL / Elu),
   prediction multimodale

### Act II — L'architecture (5 min)
1. Pipeline Medallion (Bronze → Silver → Gold) — diagramme
2. 4 piliers ML (GNN spatial, XGBoost reactif, Velov, Recommandation)
3. Stack : Airflow / PostgreSQL+PostGIS / MLflow / FastAPI / Streamlit
4. Securite 10 regles : SQL parametre, RGPD, audit log, sealed-secrets

### Act III — La demo live (8 min)
1. Ouverture dashboard https://lyonflow.demo.jedha.fr
2. Persona Usager : Mon Trajet → recommandation Bellecour→Part-Dieu
3. Persona Pro TCL : PCC Live → carte bottlenecks rouge/orange
4. Persona Elu : Synthese executive + simulateur "et si on creait une
   voie velo rue Vendome"
5. Behind the scenes : ouvrir MLflow → derniere experience GNN, metriques
6. Bonus : trigger DAG Airflow `transform_silver_to_gold` en live,
   voir le rowcount augmenter dans Postgres

### Act IV — La technique cle (3 min)
1. Zoom sur le GNN : SpatioTemporalGCN, propagation congestion
2. Code walkthrough : `training/stgcn/model.py` (50 lignes architecture)
3. Set-based SQL vs N+1 : montrer le `silver_to_gold.py` apres refactor

### Act V — Le futur (1 min)
1. Phase 2 K8s production (deja livree, voir branche `kubernetes`)
2. Phase 3 cloud demo (ici meme)
3. Pistes : multimodal genAI assistant, prediction emissions CO2

## Q&A anticipees

| Question probable | Reponse cle |
|-------------------|-------------|
| Pourquoi pas DataBricks ? | Cout, RGPD UE, control total stack |
| Pourquoi Airflow et pas Prefect ? | Maturite ecosysteme, courbe equipe |
| Pourquoi GNN et pas Transformer ? | Graphe explicite (capteurs+routes), interpretabilite |
| Comment gerer privacy ? | Pas de PII collectee, audit log purge auto 45j |
| Cost projection 1 metropole ? | ~60 €/mois K8s prod, scale lineaire jusqu'a 10x |
| Production-ready ? | Phase 1 oui (104 tests, CI/CD), Phase 2 manifests prets |

## URLs jour J

| Service | URL | Commentaire |
|---------|-----|-------------|
| Dashboard | https://lyonflow.demo.jedha.fr | Public, multi-persona |
| API | https://api.lyonflow.demo.jedha.fr/docs | OpenAPI/Swagger |
| Airflow | https://airflow.lyonflow.demo.jedha.fr | demo / [demo password] |
| MLflow | https://mlflow.lyonflow.demo.jedha.fr | tracking experiments |
| Grafana | https://grafana.lyonflow.demo.jedha.fr | latence + HPA replicas |
| Repo Git | https://github.com/PDUCLOS/lyonflowfull | 4 branches : main, vps, kubernetes, cloud-demo |

## Outils visuels

- Diagramme architecture (Excalidraw) : `docs/architecture-soutenance.png`
- Slides PDF : `docs/SOUTENANCE_SLIDES.pdf`
- Video backup demo (si reseau KO) : `docs/demo-backup.mp4`

## Repetitions

- [ ] J-7 : repetition complete avec timer 20 min
- [ ] J-3 : repetition focus Q&A
- [ ] J-1 : spin-up cluster + test URLs + screenshot fallback
- [ ] J-0 09h : spin-up cluster final + verif tout
- [ ] J-0 H-1 : seed live derniers data
- [ ] J-0 H+1 : tear-down cluster
