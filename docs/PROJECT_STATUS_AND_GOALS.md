# État d'avancement et Objectifs du Projet LyonFlowFull

**Dernière mise à jour :** Juin 2026

Ce document récapitule l'état actuel de l'infrastructure de LyonFlowFull et fixe le cap pour le déploiement MLOps en cours.

---

## 1. Ce qui est accompli et figé (Phase de Fiabilisation)

Le socle technique et logiciel est désormais à un stade de fiabilité "Production-ready".

### Infrastructure & Déploiement (Branche `vps`)
- **Serveur Unique** : Le projet est hébergé de manière autonome sur un VPS Ubuntu (pas de dépendance AWS/GCP). L'environnement Docker est complet (PostgreSQL + MinIO + Redis + Airflow + MLflow + FastAPI + Streamlit).
- **Hardening** : Certificats TLS via Let's Encrypt (Nginx reverse proxy), firewall, et services gérés par Systemd (avec relance automatique en cas de reboot).
- **Supervision** : Stack Prometheus + Grafana configurée. Les métriques de FastAPI et du Dashboard remontent en direct.

### Fiabilité Applicative (Data & QA)
- **Data Binding Total** : Les 45 widgets du Dashboard consomment les données réelles issues de la base de données.
- **Résilience Anti-Crash** : Si la base de données subit une micro-coupure (ex: erreur `OperationalError`), l'application l'intercepte silencieusement, active un "mode hors-ligne" transparent et utilise des données de fallback (Mocks) avec un bandeau préventif. Zéro écran blanc.
- **Couverture de Tests (E2E)** : Les scénarios de navigation pour les différents Personas (notamment les accès sécurisés "Pro TCL" et "Élu") sont validés par **Playwright**.
- **Testabilité Universelle** : Grâce à `make test-docker`, toute la suite de tests s'exécute isolée de l'hôte, évitant l'enfer des dépendances locales (C++, GDAL).

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
