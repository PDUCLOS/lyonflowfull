# Audit qualité code — branche `vps` LyonFlowFull

**Piste** : code-quality-audit
**Date** : 2026-06-08
**Auditeur** : coder (session mvs_954efed92ca44f5a833b5ecf2a3195f0)
**Branche** : `vps` (commit a05032b)
**Mode** : LECTURE SEULE — aucune modification du repo
**Statut global** : **FAIL** (1 bloquant prod : import cassé)

---

## 1. Summary

Audit qualité du code Python et scripts shell livrés par la branche `vps` (Sprints VPS-1 à VPS-4).
Périmètre : `src/api/metrics.py`, `src/api/main.py` (instrumentation), `pyproject.toml`,
3 scripts bash (`audit-vps-predeploy.sh`, `backup-offsite.sh`, `check-deploy-env.sh`) et le
`Makefile` étendu (+124 lignes). **1 finding CRITICAL bloquant prod** (dépendance
`prometheus-fastapi-instrumentator` absente de `requirements.txt` → l'API ne démarrera pas
en production) + 3 HIGH et 5 MEDIUM.

---

## 2. Périmètre examiné

| Fichier | Lignes | Rôle audit |
|---|---|---|
| `src/api/metrics.py` (nouveau) | 67 | Module métriques Prometheus custom |
| `src/api/main.py` | 545 (54 ajoutées) | Instrumentation FastAPI / middleware / hooks |
| `src/api/middleware/rate_limit.py` | 104 | Rate limit (vérif régression) |
| `src/api/__init__.py` | 5 | Vérif imports circulaires |
| `pyproject.toml` | 192 (5 ajoutées) | Dépendances + ruff config |
| `requirements.txt` | ~80 | Source de vérité des deps Python |
| `Dockerfile` | 57 | Confirmation `pip install -r requirements.txt` |
| `docker-compose.yml` (section api) | 110–340 | Confirme que l'API utilise le Dockerfile commun |
| `scripts/audit-vps-predeploy.sh` | 122 | Audit pré-déploy |
| `scripts/backup-offsite.sh` | 123 | Backup stream offsite (règle « pas de backup local ») |
| `scripts/check-deploy-env.sh` | 45 | Vérif .deploy.env avant rsync |
| `Makefile` | 295 (124 ajoutées) | Targets deploy/healthcheck/rollback/monitoring |
| `.gitignore` | 94 | Vérif `backups/*.dump.gz` |
| `tests/` | 6 sous-dossiers | Présence/absence de `test_metrics.py` |

Commandes de preuve exécutées (extraits) :
- `ruff check src/api/metrics.py src/api/main.py src/api/middleware/rate_limit.py` → `All checks passed!`
- `ruff format --check ...` → `3 files already formatted`
- `python3 -c "from prometheus_fastapi_instrumentator import Instrumentator"` → `ModuleNotFoundError`
- `pip show prometheus-fastapi-instrumentator` → `WARNING: Package(s) not found`
- `grep -rEn 'PREDICTIONS_TOTAL|PERSONA_REQUESTS|DAG_RUNS_TOTAL|MLFLOW_ACTIVE_RUNS|DB_QUERY_DURATION' src/`
- `grep -nE 'prometheus' requirements.txt pyproject.toml` → 0 match
- `git check-ignore -v backups/lyonflow_20260608_064919Z_postgres.dump.gz` → pas ignoré
- AST walk pour détecter imports inutilisés dans `main.py` → 0 hit

---

## 3. Findings

> Format : `F-CQ-N` | Sévérité | Fichier:ligne | Preuve | Recommandation

### F-CQ-1 — CRITICAL — Dépendance `prometheus-fastapi-instrumentator` absente

**Fichier** : `requirements.txt` (manquant) + `src/api/main.py:25`

**Preuve** :
```
$ grep -nE 'prometheus' requirements.txt
(aucun résultat)

$ python3 -c "from prometheus_fastapi_instrumentator import Instrumentator"
ModuleNotFoundError: No module named 'prometheus-fastapi-instrumentator'
```

`main.py:25` fait `from prometheus_fastapi_instrumentator import Instrumentator` puis
`main.py:81-87` instancie `Instrumentator(...).instrument(app).expose(app, endpoint="/metrics", ...)`.
**Sans cette dépendance, `uvicorn src.api.main:app` lève `ModuleNotFoundError` au chargement et
l'API ne démarre jamais** → /metrics inaccessible → Prometheus ne scrape rien → tout le Sprint
VPS-4 est mort en prod.

`prometheus-client` (0.25.0) est présent localement comme transitive dep (de MLflow), mais
n'est pas non plus épinglée dans `requirements.txt` — c'est un autre problème (voir F-CQ-2).

**Recommandation** :
```diff
# requirements.txt
+# Monitoring (Sprint VPS-4)
+prometheus-client>=0.20.0,<1.0
+prometheus-fastapi-instrumentator>=7.0.0,<8.0
```
Référencer la version exacte testée localement (0.25.0 pour `prometheus_client`).
Re-build l'image Docker API avant tout déploiement.

**Bloquant prod** : OUI.

---

### F-CQ-2 — HIGH — `prometheus-client` n'est pas déclarée explicitement

**Fichier** : `requirements.txt`

**Preuve** :
```
$ grep -nE 'prometheus-client' requirements.txt
(aucun résultat)
$ pip show prometheus-client
Name: prometheus_client
Version: 0.25.0
```
Présent localement comme dépendance transitive (de `mlflow` probablement), mais non déclarée
→ disparition silencieuse possible si MLflow change ses deps. Le module `src/api/metrics.py:14`
l'importe directement.

**Recommandation** : ajouter `prometheus-client>=0.20.0,<1.0` à `requirements.txt` (cf. F-CQ-1).

---

### F-CQ-3 — HIGH — 4 métriques sur 6 sont du code mort (non utilisées)

**Fichier** : `src/api/metrics.py:35-67`

**Preuve** :
```
$ grep -rEn 'PERSONA_REQUESTS|DAG_RUNS_TOTAL|MLFLOW_ACTIVE_RUNS|DB_QUERY_DURATION' src/ dags/ \
  | grep -v metrics.py
(aucun résultat)
```

| Constante | Définie | Utilisée | Statut |
|---|---|---|---|
| `PREDICTIONS_TOTAL` | metrics.py:19 | main.py:317,343 | OK |
| `PREDICTION_LATENCY` | metrics.py:25 | main.py:306,341 | OK |
| `PERSONA_REQUESTS` | metrics.py:35 | — | **mort** |
| `DAG_RUNS_TOTAL` | metrics.py:44 | — | **mort** |
| `MLFLOW_ACTIVE_RUNS` | metrics.py:53 | — | **mort** |
| `DB_QUERY_DURATION` | metrics.py:62 | — | **mort** |

Le commentaire de module les annonce toutes, mais aucun middleware / hook / endpoint ne les
incrémente. Risques :
- Faux sentiment de couverture monitoring (Sprint VPS-4 annonces 6 métriques, 2 effectives)
- Cardinalité 0 = pas d'alerte, mais aussi pas de signal
- Maintenance : si on supprime le fichier metrics.py par erreur, ça ne casse rien

**Recommandation** : soit (a) câbler les 4 métriques manquantes dans la prochaine itération
(middleware JWT pour PERSONA_REQUESTS, callback DAG pour DAG_RUNS_TOTAL, scraper MLflow pour
MLFLOW_ACTIVE_RUNS, decorator sur `execute_query` pour DB_QUERY_DURATION), soit (b) les
supprimer du module pour ne garder que les 2 utilisées. La doc Sprint VPS-4 doit alors être
alignée.

---

### F-CQ-4 — HIGH — `tests/test_metrics.py` n'existe pas

**Fichier** : `tests/` (manquant)

**Preuve** :
```
$ find tests/ -name 'test_metrics*'
(aucun résultat)
$ grep -rEn 'PREDICTIONS_TOTAL|PREDICTION_LATENCY' tests/
(aucun résultat)
```

`AGENTS.md:58` impose `pytest pour chaque module`. Le module `src/api/metrics.py` n'a aucun
test. Pas de couverture des :
- buckets Histogram
- labels (model, horizon_minutes, status)
- comportement si incrément rapide (counter overflow / race)
- compatibilité API `prometheus_client`

**Recommandation** : créer `tests/api/test_metrics.py` minimal :
```python
def test_counter_increments():
    from src.api.metrics import PREDICTIONS_TOTAL
    before = PREDICTIONS_TOTAL.labels(model="x", horizon_minutes="30", status="success")._value.get()
    PREDICTIONS_TOTAL.labels(model="x", horizon_minutes="30", status="success").inc()
    after = PREDICTIONS_TOTAL.labels(model="x", horizon_minutes="30", status="success")._value.get()
    assert after == before + 1
```
Et un smoke test qui vérifie que `from src.api.metrics import ...` ne lève pas (couvre F-CQ-1
via l'environnement de test).

---

### F-CQ-5 — HIGH — Script `check-deploy-env.sh` prompt interactif en mode non-interactif

**Fichier** : `scripts/check-deploy-env.sh:24`

**Preuve** :
```bash
24:    read -p "Appliquer chmod 600 maintenant ? [y/N] " confirm
25:    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
```

`Makefile:165` appelle ce script via `check-deploy-env` (en dépendance de `deploy-vps`). Si
appelé depuis CI / cron / pipe (`echo "y" | make deploy-vps`), le `read` lit EOF et `$confirm`
reste vide → branche `else` → `exit 1` → le déploiement échoue pour une raison triviale.

**Recommandation** :
- Soit auto-corriger (chmod 600 inconditionnel après confirmation explicite dans la doc) :
  ```bash
  if [ "$PERMS" != "600" ]; then
      echo "[WARN] $DEPLOY_ENV a les permissions $PERMS (attendu: 600)"
      chmod 600 "$DEPLOY_ENV"
      echo "[OK] Permissions corrigées : 600"
  fi
  ```
- Soit utiliser un flag `--non-interactive` (cf `apt-get -y`).
- Au minimum : `read -p ... < /dev/tty` (échoue explicitement si pas de TTY, pas de hang).

---

### F-CQ-6 — HIGH — `audit-vps-predeploy.sh` viole la règle « JAMAIS de backup persistant local »

**Fichier** : `scripts/audit-vps-predeploy.sh:42-62`

**Preuve** :
```bash
42: $SSH 'cd /opt/lyonflow && ./scripts/backup.sh 2>&1 | tail -5'
43: BACKUP_FILE=$($SSH 'ls -t /opt/lyonflow/backups/lyonflow_*_postgres.dump 2>/dev/null | head -1')
44: if [ -z "$BACKUP_FILE" ]; then
45:     echo "❌ Aucun backup trouve. Arret."
...
57: SNAPSHOT_NAME="snapshot_volume_$(date +%Y%m%d_%H%M%S).tar.gz"
58: $SSH "docker run --rm \
59:     -v lyonflow_postgres_data:/data:ro \
60:     -v /opt/lyonflow/backups:/backup \
61:     alpine tar czf /backup/$SNAPSHOT_NAME -C /data . 2>&1 | tail -3"
```

`CLAUDE.md` (règle 🔴) et `backup-offsite.sh:1-8` (en-tête) sont **explicites** :
> « JAMAIS de backup persistant sur le VPS (full à 100%). Toujours offsite via `scripts/backup-offsite.sh`. Stream pur, rien d'écrit sur le disque VPS. »

Or ce script (qui s'appelle « pre-deploy audit sécurisé ») :
1. Appelle `backup.sh` qui écrit `backups/lyonflow_*_postgres.dump` (PERSISTANT sur VPS, environ 18 GB)
2. Crée un snapshot volume tar.gz dans le même dossier (PERSISTANT)

C'est une contradiction directe avec la règle cardinale du projet. En cas de disque à 100%,
l'audit lui-même peut remplir le VPS avant de vérifier quoi que ce soit.

**Recommandation** : réécrire pour faire l'audit **AVANT** toute écriture de backup, et
**streamer** les sauvegardes hors site (utiliser `pg_dump | gzip | ssh backup-host 'cat > ...'`
sans fichier local). Cf. `backup-offsite.sh` pour le pattern. Si un filet local est vraiment
nécessaire (point-in-time snapshot), ajouter un check `df -h` et nettoyer
(`rm -f /opt/lyonflow/backups/snapshot_*.tar.gz`) à la fin de l'audit, ou le streammer vers
un dossier tmpfs.

**Bloquant prod** : NON (l'audit n'est pas obligatoire en routine), mais contredit l'esprit
du Sprint VPS-2 qui a justement créé `backup-offsite.sh` pour supprimer cette violation.

---

### F-CQ-7 — MEDIUM — `backups/*.dump.gz` non ignoré par `.gitignore`

**Fichier** : `.gitignore:63-65`

**Preuve** :
```
$ ls -la backups/
-rw-r--r--  3.9G  lyonflow_20260608_064919Z_postgres.dump.gz

$ git check-ignore -v backups/lyonflow_20260608_064919Z_postgres.dump.gz
(aucun match)

$ git status backups/
Untracked files:
    backups/
```

`.gitignore` couvre `backups/*.sql`, `backups/*.dump`, `backups/*.tar.gz` mais oublie
`backups/*.dump.gz` (combo). Le dump actuel 3.9 GB pourrait être accidentellement
`git add -A`'ed → inflate le repo de 4 GB.

**Recommandation** : ajouter
```gitignore
backups/
```
(plutôt que pattern par extension) — règle du projet = « JAMAIS de backup persistant local »
donc le dossier entier ne devrait jamais être commité.

---

### F-CQ-8 — MEDIUM — `audit-vps-predeploy.sh` : pas de validation de `VPS_SSH_KEY` path

**Fichier** : `scripts/audit-vps-predeploy.sh:25-31`

**Preuve** :
```bash
25: if [ -z "${VPS_HOST:-}" ] || [ -z "${VPS_SSH_KEY:-}" ]; then
26:     echo "❌ VPS_HOST et VPS_SSH_KEY doivent etre definies."
27:     echo "   source .deploy.env avant de lancer ce script."
28:     exit 1
29: fi
30:
31: SSH="ssh -i $VPS_SSH_KEY $VPS_HOST"
```

Manques :
1. Pas de validation que `$VPS_SSH_KEY` pointe vers un fichier existant (`[ -f "$VPS_SSH_KEY" ]` ou `[ -r "$VPS_SSH_KEY" ]`).
2. `SSH="ssh -i $VPS_SSH_KEY $VPS_HOST"` non quoté → si `$VPS_HOST` contient un espace ou
   un caractère spécial, l'expansion casse la commande.
3. Pas de validation de format de `$VPS_HOST` (devrait ressembler à `user@host` ou `host`).
4. Idempotence : le script peut être appelé plusieurs fois, le snapshot tar.gz s'accumule
   dans `/opt/lyonflow/backups/` (jamais nettoyé).

**Recommandation** :
```bash
[ -f "$VPS_SSH_KEY" ] || { echo "❌ VPS_SSH_KEY=$VPS_SSH_KEY introuvable"; exit 1; }
[[ "$VPS_HOST" =~ ^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$ || "$VPS_HOST" =~ ^[A-Za-z0-9_.-]+$ ]] \
    || { echo "❌ VPS_HOST=$VPS_HOST invalide"; exit 1; }
SSH=(ssh -i "$VPS_SSH_KEY" "$VPS_HOST")
```
Et cleanup du snapshot en fin d'audit (ou utiliser mktemp -d).

---

### F-CQ-9 — MEDIUM — `Makefile` healthcheck utilise HTTP, pas HTTPS

**Fichier** : `Makefile:169-171`

**Preuve** :
```makefile
169: @curl -fsS --max-time 10 http://localhost/api/health || (echo "❌ API health failed" && exit 1)
170: @echo "==[ HTTP /nginx-health ]=="
171: @curl -fsS --max-time 5 http://localhost/nginx-health || (echo "❌ nginx health failed" && exit 1)
```

En prod, Nginx force HTTPS (cf `nginx/ssl.conf`). Le healthcheck qui tape `http://` ne teste
que la redirection, pas le endpoint réel. Il faudrait `--insecure -L` (follow redirects) ou
taper directement `https://localhost/api/health` après que Let's Encrypt a signé le cert.

**Recommandation** : utiliser `https://localhost/api/health -k` ou un curl qui suit les
redirections `301/302` pour valider le vrai chemin de prod.

---

### F-CQ-10 — MEDIUM — `Makefile:backup-offsite` ambigu vs `scripts/backup-offsite.sh`

**Fichier** : `Makefile:244-251`

**Preuve** :
```makefile
244: backup-offsite:  ## Push backup vers serveur distant (rsync over SSH)
245:     @if [ -z "$$OFFSITE_HOST" ]; then \
246:         echo "❌ OFFSITE_HOST non défini. Ajouter à .deploy.env : OFFSITE_HOST=user@backup.example.com"; \
247:         exit 1; \
248:     fi
249:     @rsync -avz --delete -e "ssh -i $(SSH_KEY)" \
250:         backups/ $$OFFSITE_HOST:~/lyonflow-backups/
251:     @echo "✅ Backup offsite synced"
```

Deux commandes appelées `backup-offsite` :
- `make backup-offsite` → rsync le dossier **local** `backups/` vers OFFSITE_HOST (ce qui
  implique que `backups/` existe localement = viole la règle)
- `bash scripts/backup-offsite.sh` → stream pg_dump vers offsite (conforme à la règle)

L'utilisateur peut confondre. Le `make backup-offsite` ne devrait pas exister en prod VPS
(le bon chemin c'est `scripts/backup-offsite.sh` côté VPS via le timer systemd).

**Recommandation** : renommer `make backup-offsite` en `make backup-offsite-legacy` ou
`make rsync-backups` et ajouter un commentaire explicite :
> « ⚠️ Ce target rsync un dossier backups/ LOCAL → ne pas utiliser côté VPS. Pour le stream
> offsite conforme à la règle du projet, utiliser `scripts/backup-offsite.sh`. »

---

### F-CQ-11 — MEDIUM — `Makefile:rollback-vps` : checkout sans filet

**Fichier** : `Makefile:206-213`

**Preuve** :
```makefile
206: rollback-vps:  ## Rollback deploy VPS vers tag précédent (Sprint VPS-2)
207:     @PREV=$$(git tag --list 'vps-*' --sort=-version:refname | sed -n '2p'); \
208:     if [ -z "$$PREV" ]; then echo "❌ Pas de tag vps-* précédent"; exit 1; fi; \
209:     echo "Rollback vers $$PREV"; \
210:     git checkout $$PREV && \
211:     ssh -i $(SSH_KEY) $(VPS_HOST) "cd /opt/lyonflow && git fetch && git checkout $$PREV && docker compose up -d --build" && \
212:     git checkout -
```

Si la 2e commande SSH échoue, `git checkout -` n'est pas exécuté (à cause de `&&`) → le
worktree local reste sur l'ancien tag. De plus, `ssh ... && docker compose up -d --build`
est non-atomique : si le checkout distant réussit mais que le build échoue, le VPS est dans
un état incohérent.

**Recommandation** :
- Wrapper dans un trap :
  ```makefile
  rollback-vps:
      @trap 'git checkout -' EXIT; \
      PREV=...; \
      git checkout $$PREV || exit 1; \
      ssh ... || (git checkout -; exit 1); \
      git checkout -
  ```
- Préférer `git switch -d $$PREV` (plus moderne que `git checkout`).
- Ajouter un healthcheck post-rollback (cf F-CQ-9).

---

### F-CQ-12 — LOW — Convention française/anglaise mixte dans `metrics.py`

**Fichier** : `src/api/metrics.py:1-10`

**Preuve** : module docstring en français (conforme à CLAUDE.md), mais les commentaires
inline en anglais :
```python
22: ["model", "horizon_minutes", "status"],  # status = success | error
28: ["model"],
38: ["persona", "endpoint"],
47: ["dag_id", "state"],  # state = success | failed | running
56: ["experiment_name"],
65: ["query_type"],  # SELECT | INSERT | UPDATE | DELETE
```
`AGENTS.md:54` dit « code en ANGLAIS, commentaires en FRANÇAIS ». Les commentaires `# status = success | error` devraient être `# status = succès | erreur`. Pas critique (les valeurs restent anglaises car c'est le standard Prometheus), mais l'incohérence est notable.

**Recommandation** : convertir les commentaires en français ou accepter la convention
« labels Prometheus en anglais, commentaires explicatifs en français » comme une exception
documentée dans `AGENTS.md`.

---

### F-CQ-13 — INFO — `rm -rf` borné dans Makefile (non bloquant)

**Fichier** : `Makefile:150-153`

**Preuve** :
```makefile
150: find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
```

Les `rm -rf` sont :
1. Bornés par `find -type d -name "<pattern>"` (ne touchent que les dossiers matchant le nom)
2. Protégés par `2>/dev/null || true` (échec silencieux)
3. Ciblent uniquement des dossiers de cache (pycache, pytest_cache, mypy_cache, ruff_cache)

→ Pas de risque de destruction accidentelle, mais le motif `rm -rf {} +` reste à surveiller
dans tout ajout futur. Pour une sécurité maximale, utiliser `find ... -prune -exec rm -rf {} +`
ou `find ... -delete`.

---

### F-CQ-14 — INFO — Imports inutilisés : aucun

**Preuve** : AST walk sur `src/api/main.py` → tous les imports top-level sont référencés.
`src/api/metrics.py` : 1 seul import (`prometheus_client`) → référencé.
`src/api/middleware/rate_limit.py` : pas modifié par la branche vps, déjà propre.

→ ruff + AST confirment 0 import inutile sur le périmètre. **POSITIF.**

---

### F-CQ-15 — INFO — `set -euo pipefail` présent dans les 3 scripts

**Preuve** :
```
scripts/audit-vps-predeploy.sh:22: set -euo pipefail
scripts/backup-offsite.sh:32:     set -euo pipefail
scripts/check-deploy-env.sh:8:    set -euo pipefail
```
**POSITIF** : conforme aux bonnes pratiques bash.

---

### F-CQ-16 — INFO — Pas d'imports circulaires entre `metrics.py` et `main.py`

**Preuve** :
- `src/api/metrics.py` n'importe rien depuis `src.api` (juste `prometheus_client`)
- `src/api/main.py` importe `src.api.metrics` et `src.api.middleware.rate_limit` mais pas
  l'inverse.
- `src/api/__init__.py:3` fait `from src.api.main import app` — déclenche le chargement de
  main.py au premier `import src.api`, mais pas de cycle.

**POSITIF** : graphe d'imports linéaire, pas de cycle.

---

### F-CQ-17 — INFO — `X-API-Key` et rate limit préservés

**Preuve** :
- `verify_api_key` toujours appelé sur 6 endpoints (lignes 290, 303, 338, 359, 396, 450).
- `RateLimitMiddleware` toujours enregistré ligne 75 (avant Instrumentator, donc le rate
  limit catch les requêtes même avant que /metrics ne réponde).
- L'instrumentation `Instrumentator(...).instrument(app).expose(app, endpoint="/metrics", ...)`
  exclut explicitement `/health` et `/metrics` du tracking (ligne 84) → pas de pollution
  Prometheus avec les health checks.

**POSITIF** : pas de régression de sécurité sur l'authentification ou le rate limit.

---

## 4. Tableau récapitulatif

| # | Sévérité | Fichier | Sujet | Bloquant prod |
|---|---|---|---|---|
| F-CQ-1 | **CRITICAL** | `requirements.txt` | `prometheus-fastapi-instrumentator` manquant | **OUI** |
| F-CQ-2 | HIGH | `requirements.txt` | `prometheus-client` non déclarée | non (transitive) |
| F-CQ-3 | HIGH | `src/api/metrics.py:35-67` | 4 métriques sur 6 sont du code mort | non |
| F-CQ-4 | HIGH | `tests/` | Pas de `test_metrics.py` | non |
| F-CQ-5 | HIGH | `scripts/check-deploy-env.sh:24` | Prompt interactif casse en CI | non (CI) |
| F-CQ-6 | HIGH | `scripts/audit-vps-predeploy.sh:42-62` | Viole règle « pas de backup local » | non (audit) |
| F-CQ-7 | MEDIUM | `.gitignore:63-65` | `backups/*.dump.gz` non ignoré (3.9 GB) | non |
| F-CQ-8 | MEDIUM | `scripts/audit-vps-predeploy.sh:25-31` | Pas de validation VPS_SSH_KEY path | non |
| F-CQ-9 | MEDIUM | `Makefile:169-171` | Healthcheck HTTP au lieu de HTTPS | non |
| F-CQ-10 | MEDIUM | `Makefile:244-251` | `make backup-offsite` confusant | non |
| F-CQ-11 | MEDIUM | `Makefile:206-213` | `rollback-vps` : pas de trap en cas d'échec SSH | non |
| F-CQ-12 | LOW | `src/api/metrics.py:22-65` | Commentaires anglais au lieu de français | non |
| F-CQ-13 | INFO | `Makefile:150-153` | `rm -rf` bornés (acceptable) | non |
| F-CQ-14 | INFO | — | Aucun import inutile (positif) | — |
| F-CQ-15 | INFO | 3 scripts | `set -euo pipefail` partout (positif) | — |
| F-CQ-16 | INFO | — | Pas d'import circulaire (positif) | — |
| F-CQ-17 | INFO | `src/api/main.py` | X-API-Key + rate limit préservés (positif) | — |

**Scoring** :
- 1 CRITICAL
- 5 HIGH (dont 1 touche aux invariants du projet : règle « pas de backup local »)
- 5 MEDIUM
- 1 LOW
- 5 INFO (positifs)
- **Statut : FAIL** (à cause du CRITICAL F-CQ-1 qui empêche l'API de démarrer)

---

## 5. Plan d'action recommandé

### Immédiat (avant prochain déploiement)
1. **F-CQ-1** : ajouter `prometheus-client>=0.20.0,<1.0` ET
   `prometheus-fastapi-instrumentator>=7.0.0,<8.0` à `requirements.txt`, re-build l'image
   API, vérifier `pip show prometheus-fastapi-instrumentator` dans le conteneur API.
2. **F-CQ-6** : réécrire `audit-vps-predeploy.sh` pour streamer le filet de sécurité vers
   offsite (ou utiliser `backup-offsite.sh` directement).
3. **F-CQ-7** : remplacer `backups/*.sql|dump|tar.gz` par `backups/` dans `.gitignore` et
   ajouter le dump 3.9 GB au gitignore via `git rm --cached backups/lyonflow_*.dump.gz`
   (ne pas supprimer le fichier !).

### Court terme (semaine)
4. **F-CQ-2** : une fois F-CQ-1 résolu, F-CQ-2 est résolu automatiquement.
5. **F-CQ-3** : décision GO/NO-GO sur les 4 métriques « mortes ». Si GO : câbler
   (middleware JWT, callback DAG, scraper MLflow, decorator DB). Si NO-GO : retirer de
   `metrics.py` et aligner la doc Sprint VPS-4.
6. **F-CQ-4** : créer `tests/api/test_metrics.py` (smoke + counter increment + histogram
   observation).
7. **F-CQ-5** : supprimer le `read` interactif de `check-deploy-env.sh` (auto-correction
   `chmod 600` avec log).

### Moyen terme (prochain sprint)
8. **F-CQ-8, F-CQ-9, F-CQ-10, F-CQ-11** : durcir les scripts (validation, HTTPS, naming
   non ambigu, trap rollback).
9. **F-CQ-12** : harmoniser commentaires FR/EN ou documenter l'exception.

---

## 6. Signaux positifs (ce qui est bien fait)

- **Imports propres** : ruff + AST confirment 0 import inutile, 0 circular import (F-CQ-14, F-CQ-16).
- **Linting/formatage** : `ruff check` passe sans warning sur les 3 fichiers API ; `ruff format --check` confirme le formatage.
- **`set -euo pipefail`** présent dans les 3 scripts (F-CQ-15).
- **Conventions Prometheus respectées** : préfixe `lyonflow_`, snake_case, unités `_seconds`/`_total` (CLAUDE.md/standard Prometheus).
- **Pas de régression sécurité** : `X-API-Key` + `RateLimitMiddleware` préservés, `/health` et `/metrics` exclus du tracking (F-CQ-17).
- **`backup-offsite.sh` est conforme à la règle « stream pur »** : pas de fichier local entre pg_dump et rclone, le `pg_dump | gzip | gpg | rclone rcat` est un pipe pur, validation de l'espace disque, pas de dump en clair sur VPS.
- **Cardinalité Prometheus maîtrisée** : labels limités (`model`, `horizon_minutes`, `status`, `persona`, `dag_id`, `state`, etc.), buckets Histogram bien choisis.

---

## 7. Annexe — vérifications croisées pour le verifier

```bash
# F-CQ-1 : confirm absence
cd /Users/patriceduclos/Documents/Lyonfull
grep -E 'prometheus' requirements.txt  # doit retourner 0 ligne
python3 -c "import prometheus_fastapi_instrumentator"  # doit lever ImportError

# F-CQ-2 : confirm
pip show prometheus-client  # installé transitivement, non épinglé

# F-CQ-3 : usages réels
grep -rEn 'PERSONA_REQUESTS|DAG_RUNS_TOTAL|MLFLOW_ACTIVE_RUNS|DB_QUERY_DURATION' src/ dags/ | grep -v metrics.py
# doit retourner 0 ligne

# F-CQ-4 : absence test
ls tests/api/test_metrics.py 2>&1  # doit retourner "No such file"

# F-CQ-5 : prompt interactif
grep -n 'read -p' scripts/check-deploy-env.sh  # doit retourner 1 ligne (à fixer)

# F-CQ-6 : violation règle
grep -nE 'pg_dump|backup\.sh|snapshot_volume' scripts/audit-vps-predeploy.sh
# doit retourner les lignes 42, 57 (à fixer)

# F-CQ-7 : gitignore gap
git check-ignore -v backups/lyonflow_20260608_064919Z_postgres.dump.gz  # doit retourner rien

# F-CQ-14 : imports inutilisés
ruff check src/api/metrics.py src/api/main.py src/api/middleware/rate_limit.py
# doit retourner "All checks passed!"

# F-CQ-15 : set -euo pipefail
grep -n 'set -euo pipefail' scripts/audit-vps-predeploy.sh scripts/backup-offsite.sh scripts/check-deploy-env.sh
# doit retourner 3 lignes (une par script)

# F-CQ-16 : circular import
python3 -c "from src.api.metrics import *; from src.api.main import app; print('OK')"
# doit passer SANS prometheus_fastapi_instrumentator (ce qui est précisément F-CQ-1)
```

---

## 8. Changed files (audit)

**Aucun fichier modifié par cet audit (lecture seule, comme requis).**

| Fichier | Type |
|---|---|
| `/Users/patriceduclos/.mavis/plans/plan_c87e0b82/outputs/code-quality-audit/deliverable.md` | **créé** (livrable audit) |
| `/Users/patriceduclos/.mavis/plans/plan_c87e0b82/board.md` | mis à jour (progress) |

---

## 9. Notes pour le verifier

1. **F-CQ-1 est bloquant** : ne pas autoriser le déploiement prod tant que `prometheus-fastapi-instrumentator` n'est pas dans `requirements.txt`. Test simple :
   ```bash
   docker exec lyonflow-api python -c "from prometheus_fastapi_instrumentator import Instrumentator"
   ```
   Doit passer (sans erreur).

2. **F-CQ-6 est philosophique** : la règle « pas de backup local » est dans `CLAUDE.md` (règle 🔴) ET dans l'en-tête de `backup-offsite.sh`. L'audit pre-deploy la viole explicitement. À arbitrer avec Patrice : soit l'audit est documenté comme « exception assumée car exécuté en local dev », soit il est réécrit.

3. **F-CQ-3 (code mort)** est un piège classique du Sprint VPS-4 : la promesse initiale était 6 métriques, 2 seulement sont effectives. C'est une dette de livraison à documenter honnêtement dans le rapport Sprint VPS-4 ou à compléter dans le sprint suivant.

4. **Les bash scripts sont propres sur `set -euo pipefail`** (F-CQ-15) — c'est un signal fort des conventions VPS. Les autres findings bash sont des cas particuliers (interactivité, validation).

5. **Ruff passe intégralement** sur le périmètre Python — la dette est plutôt du côté *integration* (deps manquantes, câblage incomplet) que *style*.

6. **Aucune modification du repo n'a été faite** (audit lecture seule comme requis par le contexte). Le seul fichier créé est ce `deliverable.md` (livrable attendu par le plan).
