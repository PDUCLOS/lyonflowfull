# État d'avancement et Objectifs du Projet LyonFlowFull

**Dernière mise à jour :** 2026-06-11 (Sprint VPS-6 livré, branche `vps`)

Ce document récapitule l'état actuel de l'infrastructure de LyonFlowFull et fixe le cap pour le déploiement MLOps en cours.

---

## 1. Ce qui est accompli et figé (Phase de Fiabilisation)

Le socle technique et logiciel est désormais à un stade de fiabilité "Production-ready".

### Infrastructure & Déploiement (Branche `vps`)
- **Serveur Unique** : Le projet est hébergé de manière autonome sur un VPS Ubuntu (51.83.159.224, pas de dépendance AWS/GCP). L'environnement Docker est complet (PostgreSQL + MinIO + Redis + Airflow + MLflow + FastAPI + Streamlit).
- **Hardening** (Sprint VPS-1) : Certificats TLS via Let's Encrypt (Nginx reverse proxy), firewall, et services gérés par Systemd (avec relance automatique en cas de reboot).
- **Supervision** (Sprint VPS-3) : Stack Prometheus + Grafana configurée. Les métriques de FastAPI et du Dashboard remontent en direct.
- **Backup offsite** (Sprint VPS-2) : Timer systemd quotidien 03:00 → `scripts/backup-offsite.sh` (Google Drive via rclone OU serveur SSH). Stream pur, rien d'écrit sur le disque VPS.
- **Rollback** (Sprint VPS-2) : `make rollback-vps` ramène à la release précédente.
- **Monitoring custom** (Sprint VPS-4) : `src/api/metrics.py` — prédictions, latence, personas, DAGs, MLflow, DB.

### Fiabilité Applicative (Data & QA)
- **Sprint VPS-6 (2026-06-11) — Politique "zéro mock"** : sur le VPS,
  `LYONFLOW_DEMO_MODE=0` est obligatoire. Toute source de données
  indisponible (PostgreSQL, Airflow, MLflow) lève `DashboardDataError` et
  le widget affiche `st.error` explicite. Plus de mock silencieux en prod.
  Mode démo (`LYONFLOW_DEMO_MODE=1`) réservé au dev local, screenshots,
  démos Jedha. `make check-deploy-env` valide la variable avant chaque
  deploy. Détails : [PLAN_NO_MOCK_VPS.md](PLAN_NO_MOCK_VPS.md).
- **Référentiel lieux en DB** (Sprint VPS-6) : 21 lieux emblématiques
  Lyon + 50+ liaisons transports (T*, M*, C*, bus) + cadences observées
  par tranche horaire × type de jour. Tables `referentiel.lieux_lyon`,
  `referentiel.lieux_transports`, `referentiel.lieux_calendrier`.
- **Pathfinding multimode** (Sprint VPS-6) : voiture (Dijkstra sur
  `silver.trafic_boucles_clean` + prédictions `gold.trafic_predictions`)
  + Vélov+marche (3 segments : marche → Vélov → marche, stations
  `silver.velov_clean`). Widget Folium avec carte + polylines colorées.
- **Data Binding Total** : Les 47 widgets du Dashboard consomment les
  données réelles issues de la base de données.
- **Tests** : 78/78 tests verts (data + dashboard + pathfinding), 35
  nouveaux tests fail loud. ruff clean sur les nouveaux fichiers.
- **Couverture de Tests (E2E)** : Les scénarios de navigation pour les
  différents Personas (notamment les accès sécurisés "Pro TCL" et "Élu")
  sont validés par **Playwright**.
- **Testabilité Universelle** : Grâce à `make test-docker`, toute la
  suite de tests s'exécute isolée de l'hôte, évitant l'enfer des
  dépendances locales (C++, GDAL).

---

## 2. Le cap actuel : Déploiement MLOps

Le pipeline de données (Ingestion ➡️ Bronze ➡️ Silver ➡️ Gold) fonctionne. Le prochain grand jalon consiste à automatiser l'entraînement et l'exposition des modèles prédictifs.

### Les défis à relever (En cours)

1. **Entraînement Automatisé (Airflow)** : 
   - Finaliser les DAGs d'entraînement (`retrain_xgboost.py` et `retrain_gnn.py`) pour qu'ils soient planifiés, exécutés, et qu'ils poussent leurs métriques vers le tracking server MLflow.
2. **Registre de Modèles Dynamique (MLflow)** :
   - Au lieu de lire statiquement des fichiers `.pkl`, le système doit s'appuyer sur le Model Registry de MLflow pour gérer les cycles de vie (`Staging`, `Production`, `Archived`).
3. **Serving Temps-Réel (FastAPI)** :
   - Modifier les endpoints `/api/v1/predict/` pour que l'API télécharge dynamiquement le modèle actuellement tagué "Production" dans MLflow, sans nécessiter de redéploiement de code.
4. **Modélisation Avancée** :
   - Achever l'intégration du Spatio-Temporal Graph Convolutional Network (**ST-GCN**) dans le DAG d'entraînement pour capturer la propagation de la congestion sur le réseau routier, en complément des modèles XGBoost actuels.

---

> [!NOTE]
> Ce document remplace les anciens plans de migration (AWS, K8s, Sprint 6) qui ont tous été archivés pour maintenir la clarté du référentiel sur notre cible principale : un système autonome, résilient, hébergé sur VPS, piloté par Airflow et MLflow.
