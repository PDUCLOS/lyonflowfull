# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [0.1.0] - 2026-06-06

### Sprint 5 — Production-ready local

#### Ajouté
- **Infrastructure** : Docker Compose (12 services), Dockerfile non-root,
  Nginx reverse proxy avec rate limiting, init-db.sql complet
- **Ingestion** : 8 collecteurs Bronze (DataCollector ABC + tenacity)
- **Transforms** : Bronze→Silver (5 transformers) + Silver→Gold (3 builders)
- **ML** : XGBoost Speed (4 horizons) + Vélov (3 horizons)
- **API** : FastAPI 8 endpoints (predict, recommend, bottlenecks, RGPD, auth)
- **RGPD** : consentement, audit log, DSR, hashing SHA256
- **Data Governance** : data dictionary, lineage, PII classification
- **Airflow** : 6 DAGs (collect, transforms, retrain, maintenance)
- **File Manager** : page upload/download Streamlit
- **CI/CD** : GitHub Actions (lint, security, tests, docker build, Trivy)
- **Documentation** : README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE
- **Monitoring** : 6 health checks + rate limit middleware
- **Sécurité** : scanning secrets, JWT auth, audit trail

### Sprint 1-4 — UI Foundation

#### Ajouté
- 3 personas (Usager, Pro TCL, Élu) avec auth par mot de passe
- 16 pages Streamlit (Mon Trajet, PCC Live, Synthèse exécutive, etc.)
- 45 widgets réutilisables
- Mock data Lyon réaliste (12 lignes TCL, 458 stations Vélov, etc.)
- Génération PDF (WeasyPrint + fallback reportlab)
- 28 tests (tous verts)
- Sélecteur de persona dans la sidebar

### Notes
- Phase 2 (Kubernetes) à venir dans un autre répertoire
- Phase 3 (cloud démo Jedha) après Phase 1+2
- VPS replacement : garder PostgreSQL, remplacer le reste
