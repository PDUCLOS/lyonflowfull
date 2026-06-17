# Audit SÉCURITÉ — Branche `vps` LyonFlowFull

> **Date** : 2026-06-08
> **Branche** : `vps` (ACTIVE — cible prod 51.83.159.224)
> **Périmètre** : 9 commits ahead of main, 31 fichiers
> **Statut** : **WARN** — 2 CRITICAL / 3 HIGH / 3 MEDIUM / 3 LOW / 3 INFO

## 1. Périmètre examiné

Fichiers lus / audités :
- `nginx/nginx.conf` (209 lignes) + `nginx/ssl.conf` (31 lignes)
- `src/api/main.py` (extrait — 6 endpoints avec `verify_api_key`)
- `src/api/metrics.py` (67 lignes, complet)
- `scripts/audit-vps-predeploy.sh` (122 lignes, complet)
- `scripts/check-deploy-env.sh` (45 lignes, complet)
- `scripts/backup-offsite.sh` (123 lignes, complet)
- `scripts/systemd/lyonflow.service` + `lyonflow-backup.service` + `lyonflow-backup.timer`
- `monitoring/alertmanager/alertmanager.yml` (extrait)
- `docker-compose.monitoring.yml` (extrait 80 lignes)
- `Makefile` (295 lignes, complet)
- `pyproject.toml` (192 lignes, complet)
- `.gitignore` (extrait) + `.env.example` (extrait)
- `.github/workflows/ci.yml` (157 lignes, complet)

Commandes exécutées :
- `grep -rE '(password|api_key|secret|token|...|AKIA|ghp_|x-api-key)\s*[:=]\s*["\x27][^"\x27$]{8,}' ...` → **0 match**
- Lecture intégrale de `backup-offsite.sh` ligne par ligne (vérification stream pur)
- Lecture intégrale de `audit-vps-predeploy.sh` ligne par ligne

## 2. Findings

### CRITICAL

#### F-SEC-01 — `audit-vps-predeploy.sh` écrit snapshot volume dans `/opt/lyonflow/backups/` (local, viole règle OFFSITE)
- **Preuve** : `scripts/audit-vps-predeploy.sh` ligne 58-62 :
  ```bash
  SNAPSHOT_NAME="snapshot_volume_$(date +%Y%m%d_%H%M%S).tar.gz"
  $SSH "docker run --rm \
      -v lyonflow_postgres_data:/data:ro \
      -v /opt/lyonflow/backups:/backup \
      alpine tar czf /backup/$SNAPSHOT_NAME -C /data . 2>&1 | tail -3"
  ```
- **Impact** : Crée un `tar.gz` du volume Postgres sur le disque VPS, en violation directe de la règle « JAMAIS de backup persistant local » (CLAUDE.md, VPS_HARDENING.md). Sur un VPS à 96G/96G, chaque pre-deploy consomme ~3-10 Go de plus. Si pas de cleanup, le VPS sature et tout casse.
- **Aggravation** : Combiné avec F-BAK-01 (le script appelle `backup.sh` au lieu de `backup-offsite.sh` à la ligne 42), le pre-deploy crée DEUX fichiers locaux en plus d'un snapshot.
- **Recommandation** : Remplacer le snapshot par un upload direct offsite (pipe `tar | gpg | rclone rcat`) et supprimer `/opt/lyonflow/backups` côté VPS. En attendant, ajouter un `rm -f` après vérification md5.

#### F-SEC-02 — `Makefile` ligne 141 : `make backup` appelle `./scripts/backup.sh` (local, viole règle OFFSITE)
- **Preuve** : `Makefile` ligne 140-141 :
  ```makefile
  backup:  ## Backup PostgreSQL + MinIO
      ./scripts/backup.sh
  ```
- **Impact** : La commande `make backup` (target documenté, listé dans le `help`) persiste le dump sur le disque VPS. C'est l'exact opposé de ce que la documentation impose. Un user qui tape `make backup` après lecture de la doc viole sans le savoir la règle.
- **Recommandation** : Remplacer par `./scripts/backup-offsite.sh` (qui stream offsite). Ajouter une erreur explicite si l'env offsite n'est pas configuré.

### HIGH

#### F-SEC-03 — `.gitignore` ne couvre pas `*.dump.gz` ni `*.tar.gz` de backups
- **Preuve** : Le dossier `backups/lyonflow_20260608_064919Z_postgres.dump.gz` (2.9 Go) EST sur le disque et n'apparaît PAS dans `git check-ignore` (verifié par worker backup-recovery).
- **Impact** : Si quelqu'un fait `git add -A` (ou si le dossier est tracké par accident), le dump de 3 Go est commité. Ça saturerait le repo et exposerait des données potentiellement sensibles (PII Bronze si pas anonymisé).
- **Recommandation** : Ajouter à `.gitignore` :
  ```
  backups/
  *.dump
  *.dump.gz
  *.dump.gz.gpg
  *.tar.gz
  ```
  ET ajouter un job CI qui vérifie l'absence de fichiers > 100 Mo non trackés.

#### F-SEC-04 — Nginx bloc 80 (HTTP) ne redirige pas vers 443 (HTTPS)
- **Preuve** : `nginx/nginx.conf` lignes 60-138 (server block port 80) ne contient pas de `return 301 https://$host$request_uri;`. Le bloc HTTPS est séparé (lignes 143-208).
- **Impact** : Un user qui tape `http://lyonflow.fr` reste en clair HTTP, sans redirection. Combiné avec HSTS preload (qui ne s'applique qu'après 1ère visite HTTPS), c'est une fenêtre d'attaque MITM initiale.
- **Recommandation** : Ajouter dans le bloc 80 :
  ```nginx
  return 301 https://$host$request_uri;
  ```
  Ou utiliser le `certbot --nginx` qui fait la redirection automatiquement (mais alors le bloc manuel doit être compatible avec le certbot).

#### F-SEC-05 — `lyonflow-backup.service` autorise `ReadWritePaths=/opt/lyonflow/backups` (incohérent avec stream pur)
- **Preuve** : `scripts/systemd/lyonflow-backup.service` ligne 31 : `ReadWritePaths=/opt/lyonflow/backups`
- **Impact** : Le script `backup-offsite.sh` est censé faire un stream pur (pipe `pg_dump|gzip|gpg|rclone rcat`, AUCUN fichier intermédiaire — verifié ligne 64-101). Pourquoi autoriser l'écriture dans `backups/` ? Soit (a) inutile et à supprimer, soit (b) on autorise un fallback local non voulu. Le commentaire du service dit « Lance ./scripts/backup.sh + push offsite (rsync) » (ligne 5) — incohérent avec l'ExecStart=`backup-offsite.sh` (ligne 21).
- **Recommandation** : Supprimer `ReadWritePaths=/opt/lyonflow/backups` OU clarifier le commentaire (l'ExecStart appelle déjà `backup-offsite.sh`).

### MEDIUM

#### F-SEC-06 — Nginx expose la version (`server_tokens on` implicite)
- **Preuve** : `nginx/nginx.conf` ligne 8 : `user nginx;` mais pas de `server_tokens off;` dans le bloc http ou server.
- **Impact** : Les réponses 404/500 exposent `Server: nginx/1.24.0` (ou version), facilitant le fingerprinting pour exploit CVE.
- **Recommandation** : Ajouter `server_tokens off;` dans le bloc `http {}` (ligne 17).

#### F-SEC-07 — Pas de CSP (Content-Security-Policy) sur Streamlit
- **Preuve** : `nginx/nginx.conf` lignes 64-68 (security headers) : X-Frame, X-Content-Type, XSS, Referrer-Policy — **pas de CSP**.
- **Impact** : Streamlit injecte du JS dynamique. Sans CSP, un XSS dans un widget utilisateur pourrait exfiltrer des données.
- **Recommandation** : Ajouter pour la location Streamlit :
  ```nginx
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' wss:;" always;
  ```

#### F-SEC-08 — MinIO console exposé publiquement via Nginx sans auth Nginx supplémentaire
- **Preuve** : `nginx/nginx.conf` lignes 117-121 (location /minio/) — pas de `auth_basic` ni `if` pour restriction IP.
- **Impact** : La sécurité de `/minio/` repose uniquement sur MinIO lui-même (login/password). Si MinIO a un défaut d'auth ou si l'admin password fuite, le storage est exposé publiquement.
- **Recommandation** : Soit retirer l'exposition publique de MinIO console (utile seulement en debug), soit ajouter une couche auth Nginx (auth_basic + IP whitelist, ou SSO via OIDC).

### LOW

#### F-SEC-09 — `/metrics` endpoint non authentifié (mais sur 127.0.0.1 uniquement)
- **Preuve** : `src/api/main.py` lignes 70-78 — `Instrumentator(...).expose(app, endpoint="/metrics", include_in_schema=False)` — pas de `Depends(verify_api_key)`.
- **Impact** : Acceptable car Prometheus est sur 127.0.0.1 (vérifié `docker-compose.monitoring.yml` ligne 50 : `127.0.0.1:9090:9090`). Mais si l'API est exposée publiquement ailleurs, c'est une fuite de compteurs métier.
- **Recommandation** : Documenter explicitement que `/metrics` doit rester sur réseau interne. Ajouter une note dans `.env.example`.

#### F-SEC-10 — `make certbot-init` avec `--nginx` peut écraser la conf Nginx manuelle
- **Preuve** : `Makefile` ligne 231 : `sudo certbot --nginx -d $$DOMAIN --non-interactive --agree-tos -m admin@$$DOMAIN`
- **Impact** : Le plugin `--nginx` de certbot modifie automatiquement le fichier `nginx.conf` pour ajouter les directives SSL. Si la conf manuelle a des particularités (upstreams custom, headers), elles peuvent être perturbées.
- **Recommandation** : Préférer `certbot certonly --nginx` (obtient le cert sans toucher à la conf), puis inclure `nginx/ssl.conf` manuellement.

#### F-SEC-11 — Pas de `preload` sur HSTS
- **Preuve** : `nginx/ssl.conf` ligne 28 : `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;` — pas de `; preload`.
- **Impact** : Le domaine n'est pas dans la [HSTS Preload List](https://hstspreload.org/). Bénéfice sécurité marginal (visiteurs首次 en HTTP sont vulnérables). À activer seulement si Patrice est OK pour les contraintes (domaine neuf, contrôle total).
- **Recommandation** : Ajouter `; preload` et soumettre à hstspreload.org (optionnel).

### INFO (positifs + observations)

- **F-SEC-12** ✅ **Aucun secret hardcodé** trouvé dans tous les fichiers vps. Le grep couvrant 9 patterns (password, api_key, secret, token, BEGIN RSA, AKIA, ghp_, x-api-key, webhook) sur 9 extensions (`.py`, `.sh`, `.yml`, `.json`, `.conf`, `.service`, `.timer`, `.md`, `.toml`) dans nginx/scripts/monitoring/src/api/Makefile/.github/pyproject → 0 match.
- **F-SEC-13** ✅ **API FastAPI auth** correctement implémentée : `verify_api_key` (HMAC compare_digest, ligne 168) protège 6 endpoints (`/models`, `/predict/traffic`, `/predict/velov`, `/recommend`, `/itinerary`, `/bottlenecks`). Le check "LYONFLOW_API_KEY non configuré" retourne 500 (fail-closed), pas 200.
- **F-SEC-14** ✅ **Métriques Prometheus** : pas de PII dans les labels (`model`, `horizon_minutes`, `status`, `persona`, `endpoint`, `dag_id`, `state`, `experiment_name`, `query_type`). Cardinalité bornée (pas d'user_id, pas de timestamp).
- **F-SEC-15** ✅ **CORS configurable** via `s.api.cors_origins` (settings Pydantic), pas de `allow_origins=["*"]` hardcodé.
- **F-SEC-16** ✅ **systemd lyonflow.service** : `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=/opt/lyonflow`, `ProtectHome=yes`, `PrivateTmp=yes` — durcissement complet.
- **F-SEC-17** ✅ **docker-compose monitoring** : tous les exporters et Prometheus bindés sur `127.0.0.1` (lignes 50, 88, etc.). Pas d'admin:admin par défaut (variables d'env).
- **F-SEC-18** ✅ **TLS modernes** : `ssl_protocols TLSv1.2 TLSv1.3`, ciphers ECDHE-only, OCSP stapling, HSTS 1 an.

## 3. Statut

**WARN** — 2 CRITICAL bloquants prod (F-SEC-01 et F-SEC-02 violent la règle d'or OFFSITE).

## 4. Top 3 actions

1. **CRITIQUE** : Patcher `audit-vps-predeploy.sh` (F-SEC-01) + `Makefile` ligne 141 (F-SEC-02) pour utiliser `backup-offsite.sh` (déjà propre). Effort : 30 min.
2. **HIGH** : Étendre `.gitignore` (`backups/`, `*.dump.gz`, `*.tar.gz`) + job CI qui bloque les fichiers > 100 Mo (F-SEC-03). Effort : 15 min.
3. **HIGH** : Ajouter `return 301 https://` dans le bloc Nginx 80 (F-SEC-04) + `server_tokens off` (F-SEC-06) + `ReadWritePaths` à clarifier (F-SEC-05). Effort : 15 min.

Effort cumulé : **1h**, bloquant avant prochain deploy.
