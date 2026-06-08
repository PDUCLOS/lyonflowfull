# Audit INFRA VPS — Branche `vps` LyonFlowFull

> **Date** : 2026-06-08
> **Branche** : `vps` (ACTIVE — cible prod 51.83.159.224)
> **Périmètre** : nginx, systemd, Prometheus/Grafana/Alertmanager, métriques FastAPI, CI
> **Statut** : **WARN** — 1 CRITICAL / 4 HIGH / 5 MEDIUM / 2 LOW / 4 INFO

## 1. Périmètre examiné

Fichiers lus / audités :
- `nginx/nginx.conf` (209) + `nginx/ssl.conf` (31)
- `scripts/systemd/lyonflow.service` (50), `lyonflow-backup.service` (36), `lyonflow-backup.timer` (21)
- `monitoring/prometheus/prometheus.yml` (104)
- `monitoring/prometheus/rules/{api,database,system}.yml` (67+84+99 = 250 lignes)
- `monitoring/alertmanager/alertmanager.yml` (63)
- `docker-compose.monitoring.yml` (204, extrait 80)
- `src/api/metrics.py` (67) + `src/api/main.py` (extrait, 100 premières lignes)
- `pyproject.toml` (192) + `requirements.txt` (extrait)
- `.github/workflows/ci.yml` (157)

## 2. Findings

### CRITICAL

#### F-INF-01 — `prometheus-fastapi-instrumentator` non listé dans `requirements.txt` (import cassé, API ne démarre pas)
- **Preuve** : `src/api/main.py` ligne 32 : `from prometheus_fastapi_instrumentator import Instrumentator`. `grep -nE 'prometheus|psutil' requirements.txt` → 0 match.
- **Impact** : **BLOQUANT** — au prochain deploy, `docker compose up` sur le container API va lever `ModuleNotFoundError: No module named 'prometheus_fastapi_instrumentator'`. Le container crash en boucle. Tout le Sprint VPS-4 (métriques FastAPI) est mort en prod. Le endpoint `/metrics` ne sera pas exposé → Prometheus ne scrape rien → alertes API muettes.
- **Recommandation** : Ajouter à `requirements.txt` :
  ```
  prometheus-client>=0.20.0
  prometheus-fastapi-instrumentator>=7.0.0
  ```
  Puis `docker compose build api` et vérifier `docker exec lyonflow-api python -c "from prometheus_fastapi_instrumentator import Instrumentator"`.

### HIGH

#### F-INF-02 — `prometheus-client` non listé explicitement (dépendance transitive fragile)
- **Preuve** : `src/api/metrics.py` ligne 14 : `from prometheus_client import Counter, Gauge, Histogram`. `prometheus-client` est importé directement, pas via le wrapper. Mais il n'est pas dans `requirements.txt` — il vient probablement de MLflow.
- **Impact** : Si MLflow met à jour sa stack et retire `prometheus-client` (improbable mais possible), l'API casse. C'est une dépendance implicite.
- **Recommandation** : Ajouter `prometheus-client>=0.20.0` à `requirements.txt` (voir F-INF-01).

#### F-INF-03 — `docker-compose.monitoring.yml` ligne 67 : Grafana admin password en variable d'env (pas de secret management)
- **Preuve** : `Makefile` ligne 264 : `Grafana : http://localhost:3000 (admin / \$$GRAFANA_ADMIN_PASSWORD)`
- **Impact** : Le password admin Grafana est dans `.env` (chmod 600) sur le VPS. Acceptable. Mais il est aussi dans le `docker-compose.monitoring.yml` en `${GRAFANA_ADMIN_PASSWORD:-admin}` (fallback `admin` par défaut si non set). C'est un risque si le user oublie de définir la variable.
- **Recommandation** : Retirer le fallback `:admin` (`:${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD required}`) pour faire échouer le démarrage si non set.

#### F-INF-04 — Pas de `healthcheck` défini pour le service `api` dans `docker-compose.yml` (vérifié absent)
- **Preuve** : `make healthcheck-vps` ligne 169 : `@curl -fsS --max-time 10 http://localhost/api/health || (echo "❌ API health failed" && exit 1)` — curl depuis l'extérieur. Mais Prometheus alerting rule `ApiDown` ligne 43-52 de `api.yml` check `up{job="fastapi"} == 0` qui dépend du scrape Prometheus — or si le container API est planté, le scrape échoue mais avec un délai de 2 min (for: 2m).
- **Impact** : Pas de healthcheck Docker natif → en cas de deadlock interne (pas de crash), le container est "up" pour Docker mais ne répond plus. Détection par Prometheus = 2 min.
- **Recommandation** : Ajouter dans `docker-compose.yml` service `api` :
  ```yaml
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 60s
  ```
  Et utiliser `depends_on: api: condition: service_healthy` pour les services dépendants.

#### F-INF-05 — `monitoring/prometheus/prometheus.yml` : scrape Airflow (`/admin/metrics`) sans auth
- **Preuve** : `prometheus.yml` ligne 81-86 :
  ```yaml
  - job_name: airflow
    metrics_path: /admin/metrics
    static_configs:
      - targets: ["airflow-webserver:8080"]
  ```
- **Impact** : Airflow expose `/admin/metrics` publiquement sur le réseau Docker interne. Prometheus scrape sans auth. Acceptable car sur réseau interne. Mais `/admin/metrics` est aussi exposé via Nginx (`/airflow/`, ligne 102-108 de nginx.conf) — un user authentifié sur Airflow peut voir les métriques internes. Pas critique.
- **Recommandation** : Documenter que `/admin/metrics` n'est volontairement pas protégé (réseau interne). Ajouter dans MONITORING.md.

### MEDIUM

#### F-INF-06 — `nginx/ssl.conf` : OCSP stapling activé mais pas de `resolver` pour le responder
- **Preuve** : `ssl.conf` ligne 24-25 : `ssl_stapling on; ssl_stapling_verify on;` — pas de directive `resolver`.
- **Impact** : Nginx ne peut pas vérifier les réponses OCSP → OCSP stapling effectif dégradé (les clients peuvent quand même vérifier, mais Nginx ne peut pas valider la chaîne).
- **Recommandation** : Ajouter dans `ssl.conf` :
  ```nginx
  resolver 1.1.1.1 8.8.8.8 valid=300s;
  resolver_timeout 5s;
  ```

#### F-INF-07 — `nginx.conf` doublons de blocs : 80 et 443 ont les mêmes `location`
- **Preuve** : `nginx/nginx.conf` lignes 60-138 (bloc 80) et 143-208 (bloc 443) sont quasi identiques (seuls les headers et TLS changent).
- **Impact** : Maintenance pénible — toute modification doit être faite 2 fois. Risque de drift (les 2 blocs divergent).
- **Recommandation** : Factoriser via un fichier `nginx/includes/proxy.conf` inclus dans les 2 blocs :
  ```nginx
  include /etc/nginx/includes/proxy.conf;
  ```
  (Pas critique, c'est de la qualité de code).

#### F-INF-08 — `prometheus.yml` : pas de `remote_write` pour archivage long-terme
- **Preuve** : `prometheus.yml` ligne 26-29 : `retention.time: 30d, retention.size: 10GB`. Pas de section `remote_write`.
- **Impact** : Au-delà de 30 jours, les métriques sont perdues. Utile pour analyser une régression long-terme, capacité, coûts.
- **Recommandation** : Optionnel — activer Thanos/Mimir/Cortex, ou un simple `remote_write` vers un bucket S3/GCS. Pour VPS solo, pas bloquant.

#### F-INF-09 — `Makefile` ligne 173 : `healthcheck-vps` en HTTP au lieu HTTPS
- **Preuve** : `Makefile` ligne 169 : `@curl -fsS --max-time 10 http://localhost/api/health`
- **Impact** : Le healthcheck utilise HTTP en clair. Si l'API check son propre endpoint via Nginx, c'est OK (Nginx sert HTTP localement). Mais si la stack est forcée HTTPS, le check devrait tester les deux.
- **Recommandation** : Tester d'abord `https://localhost/api/health`, fallback `http://localhost/api/health` (avec warning).

#### F-INF-10 — `monitoring/grafana/dashboards/*.json` : panneaux utilisent des PromQL queries non testés
- **Preuve** : Fichiers `monitoring/grafana/dashboards/lyonflow-{business,overview}.json` (309 lignes combinés) — non audités en détail dans cet audit (trop long).
- **Impact** : Risque de panneaux avec queries invalides ou N+1 → dashboards cassés en silence.
- **Recommandation** : Vérifier via `make monitoring-up` + ouverture Grafana. Ajouter un test de provisioning Grafana en CI (cf. `grafana/dashboard-linter`).

### LOW

#### F-INF-11 — `lyonflow.service` ligne 30 : `ExecStart` n'utilise pas `--wait` ou healthcheck
- **Preuve** : `lyonflow.service` ligne 29 : `ExecStart=/usr/bin/docker compose up -d --build`. `Type=oneshot`, `RemainAfterExit=yes`.
- **Impact** : Systemd considère le service "started" dès que `docker compose up -d` retourne. Or `up -d` peut retourner avant que les containers soient healthy. Si un service crash au boot, systemd ne le voit pas.
- **Recommandation** : Ajouter un post-check dans le service ou utiliser un `Type=notify` avec sd_notify (plus complexe).

#### F-INF-12 — `docker-compose.monitoring.yml` : pas de restart policy sur certains services
- **Preuve** : Prometheus, Alertmanager ont `restart: unless-stopped`. Mais les exporters (node, postgres, nginx, redis) — pas vérifié dans l'extrait.
- **Impact** : Si un exporter crash, pas de redémarrage auto → Prometheus ne scrape plus, alertes muettes.
- **Recommandation** : Vérifier que tous les services de monitoring ont `restart: unless-stopped`.

### INFO (positifs + observations)

- **F-INF-13** ✅ **Alert rules bien structurées** : 16 alertes au total (api: 4, database: 6, system: 6) avec severity, runbook, descriptions claires.
- **F-INF-14** ✅ **Alertmanager inhibitions logiques** : si `DatabaseDown` critical, inhibe les autres alertes DB → pas de spam.
- **F-INF-15** ✅ **systemd timer backup** : `OnCalendar=*-*-* 03:00:00`, `Persistent=true`, `RandomizedDelaySec=300` — conforme au standard.
- **F-INF-16** ✅ **systemd services sécurisés** : `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths` explicites, `PrivateTmp=yes`.
- **F-INF-17** ✅ **Prometheus retention** : 30 jours + 10 Go max, bien dimensionné pour VPS 100 Go.
- **F-INF-18** ✅ **CI bloquante** : lint ruff + tests + docker build (sauf sur branche vps) avec Trivy. Bonne practice.
- **F-INF-19** ✅ **docker-compose.monitoring.yml** : tous les services bindés sur 127.0.0.1 (Nginx reverse proxy public).
- **F-INF-20** ✅ **Métriques custom** (`src/api/metrics.py`) : labels non-PII, cardinalité bornée (9 labels × quelques valeurs = OK), buckets histogrammes bien calibrés (0.01s à 10s pour latence, 0.001s à 1s pour DB).

## 3. Statut

**WARN** — 1 CRITICAL bloquant prod (F-INF-01 casse l'API au deploy).

## 4. Top 3 actions

1. **CRITIQUE** : Ajouter `prometheus-client` et `prometheus-fastapi-instrumentator` à `requirements.txt` (F-INF-01 + F-INF-02). Effort : 2 min + rebuild image.
2. **HIGH** : Ajouter healthcheck Docker au service API (F-INF-04) et retirer fallback `admin` Grafana (F-INF-03). Effort : 15 min.
3. **MEDIUM** : Factoriser les blocs Nginx 80/443 (F-INF-07) + ajouter `resolver` pour OCSP (F-INF-06). Effort : 30 min.
