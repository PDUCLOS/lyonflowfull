# =============================================================================
# AUDIT_VPS_RAPPORT_FINAL.md — Audit complet branche `vps` LyonFlowFull
# =============================================================================
# Date : 2026-06-08
# Branche : `vps` (ACTIVE — cible prod 51.83.159.224)
# Auditeur : Mavis (orchestrateur) + 3 workers + 2 pistes en mode solo
# Comparaison : 9 commits ahead of `main`, 0 derrière
# =============================================================================

# Audit complet branche `vps` — LyonFlowFull

## Executive Summary

**Statut global : NOT-READY** — 3 actions bloquantes avant prochain deploy.

| Piste | Statut | CRITICAL | HIGH | MEDIUM | LOW | INFO |
|-------|--------|----------|------|--------|-----|------|
| Sécurité | **WARN** | 2 | 3 | 3 | 3 | 3 |
| Infra | **WARN** | 1 | 4 | 5 | 2 | 4 |
| Code quality | **FAIL** | 1 | 5 | 5 | 1 | 5 |
| Backup-recovery | **WARN** | 3 | 2 | 3 | 3 | 3 |
| Doc/isolation | **WARN** | 0 | 4 | 4 | 5 | 3 |
| **TOTAL** | | **7** | **18** | **20** | **14** | **18** |

**3 actions prioritaires (bloquantes avant prochain deploy)** :

1. 🔴 **Ajouter `prometheus-client` + `prometheus-fastapi-instrumentator` à `requirements.txt`** (F-INF-01). Sans ça, l'API crash au démarrage, `/metrics` inaccessible, Sprint VPS-4 mort.
2. 🔴 **Patcher `scripts/audit-vps-predeploy.sh` et `Makefile:backup`** pour utiliser `backup-offsite.sh` (F-SEC-01, F-SEC-02, F-BAK-01). Actuellement le pre-deploy écrit des snapshots locaux sur le VPS, en violation directe de la règle cardinale.
3. 🔴 **Étendre `.gitignore` (`backups/`, `*.dump.gz`, `*.tar.gz`)** + ajouter un job CI qui bloque les fichiers > 100 Mo (F-SEC-03, F-CQ-08). Le dump 2.9 Go actuellement sur disque pourrait être `git add`-é par accident.

**Effort cumulé estimé : 1h pour les CRITICAL, 4-6h pour HIGH, 1-2j pour MEDIUM/LOW**.

---

## Tableau de scoring — Tous findings

| # | Piste | ID | Criticité | Effort | Bloquant prod ? |
|---|-------|----|-----------|--------|-----------------|
| 1 | Infra | F-INF-01 | CRITICAL | 5 min | OUI (API crash) |
| 2 | Sécurité | F-SEC-01 | CRITICAL | 30 min | OUI (violation OFFSITE) |
| 3 | Sécurité | F-SEC-02 | CRITICAL | 5 min | OUI (violation OFFSITE) |
| 4 | Backup | F-BAK-01 | CRITICAL | 5 min | OUI (pre-deploy faux) |
| 5 | Backup | F-BAK-02 | CRITICAL | 5 min | OUI (.gitignore漏 *.dump.gz) |
| 6 | Backup | F-BAK-03 | CRITICAL | 10 min | OUI (3 Go sur disque) |
| 7 | Code | F-CQ-01 | CRITICAL | 5 min | OUI (= F-INF-01) |
| 8 | Infra | F-INF-02 | HIGH | 1 min | NON (transitive) |
| 9 | Infra | F-INF-03 | HIGH | 5 min | NON (Grafana fallback) |
| 10 | Infra | F-INF-04 | HIGH | 15 min | NON (detection délai) |
| 11 | Infra | F-INF-05 | HIGH | 5 min | NON (info leak) |
| 12 | Sécurité | F-SEC-03 | HIGH | 15 min | NON (volumétrie) |
| 13 | Sécurité | F-SEC-04 | HIGH | 5 min | OUI (HTTP→HTTPS) |
| 14 | Sécurité | F-SEC-05 | HIGH | 5 min | NON (cohérence systemd) |
| 15 | Code | F-CQ-02 | HIGH | 30 min | NON (code mort) |
| 16 | Code | F-CQ-03 | HIGH | 1h | NON (tests manquants) |
| 17 | Code | F-CQ-04 | HIGH | 5 min | NON (CI) |
| 18 | Code | F-CQ-05 | HIGH | 30 min | NON (= F-SEC-01) |
| 19 | Code | F-CQ-06 | HIGH | 5 min | NON (.gitignore) |
| 20 | Backup | F-BAK-04 | HIGH | 1h | NON (CI gate) |
| 21 | Backup | F-BAK-05 | HIGH | 30 min | NON (Makefile rsync) |
| 22 | Doc | F-DOC-1 | HIGH | 5 min | NON (soutenance) |
| 23 | Doc | F-DOC-2 | HIGH | 30 min | NON (soutenance) |
| 24 | Doc | F-DOC-3 | HIGH | 15 min | OUI (soutenance) |
| 25 | Doc | F-DOC-4 | HIGH | 30 min | NON (obsolete) |
| 26 | Infra | F-INF-06 | MEDIUM | 5 min | NON |
| 27 | Infra | F-INF-07 | MEDIUM | 30 min | NON |
| 28 | Infra | F-INF-08 | MEDIUM | 4h | NON (optionnel) |
| 29 | Infra | F-INF-09 | MEDIUM | 5 min | NON |
| 30 | Infra | F-INF-10 | MEDIUM | 1h | NON |
| 31-50 | ... | (MEDIUM/LOW/INFO) | ... | ... | NON |

**Total : 7 CRITICAL, 18 HIGH, 20 MEDIUM, 14 LOW, 18 INFO = 77 findings** sur 5 pistes.

---

## Findings CRITICAL — Détail

### 🔴 F-INF-01 / F-CQ-01 — `prometheus-fastapi-instrumentator` absent de requirements.txt
- **Preuve** : `src/api/main.py` ligne 32 : `from prometheus_fastapi_instrumentator import Instrumentator`. `grep -nE 'prometheus' requirements.txt` → 0 match.
- **Impact** : **BLOQUANT** — Au prochain deploy, le container API crash avec `ModuleNotFoundError`. Tout le Sprint VPS-4 (métriques FastAPI custom, endpoint `/metrics`) est mort en prod. Prometheus ne scrape rien, alertes API muettes.
- **Action immédiate** :
  ```bash
  # Éditer requirements.txt, ajouter :
  prometheus-client>=0.20.0
  prometheus-fastapi-instrumentator>=7.0.0

  # Rebuild + test
  docker compose build api
  docker exec lyonflow-api python -c "from prometheus_fastapi_instrumentator import Instrumentator; print('OK')"
  ```

### 🔴 F-SEC-01 — `audit-vps-predeploy.sh` écrit snapshot volume dans `/opt/lyonflow/backups/`
- **Preuve** : `scripts/audit-vps-predeploy.sh` ligne 58-62 : `tar czf /backup/$SNAPSHOT_NAME -C /data .` où `/backup` est bindé sur `/opt/lyonflow/backups`.
- **Impact** : Crée un tar.gz du volume Postgres sur le VPS à chaque pre-deploy. VPS à 96G/96G → saturation. **Viole la règle cardinale OFFSITE** (CLAUDE.md ligne « 🔴 BACKUP OFFSITE OBLIGATOIRE »).
- **Action** : Remplacer le snapshot par un upload direct offsite, OU supprimer après vérification md5 (`rm -f` après succès).

### 🔴 F-SEC-02 / F-BAK-01 — `Makefile:backup` et `audit-vps-predeploy.sh` appellent `backup.sh` (local) au lieu de `backup-offsite.sh`
- **Preuve** : `Makefile` ligne 141 : `backup: ./scripts/backup.sh`. `audit-vps-predeploy.sh` ligne 42 : `$SSH 'cd /opt/lyonflow && ./scripts/backup.sh'`.
- **Impact** : Double violation de la règle OFFSITE. Un user qui tape `make backup` ou qui lance le pre-deploy remplit le disque VPS.
- **Action** : Remplacer les 2 appels par `./scripts/backup-offsite.sh` (déjà propre, vérifié : stream `pg_dump|gzip|gpg|rclone rcat`).

### 🔴 F-BAK-02 — `.gitignore`漏 `*.dump.gz` et `backups/`
- **Preuve** : Le dump `backups/lyonflow_20260608_064919Z_postgres.dump.gz` (2.9 Go) n'est PAS ignoré (vérifié par `git check-ignore`).
- **Impact** : Si quelqu'un fait `git add -A`, le dump est commité → repo saturé + PII potentielle exposée.
- **Action** : Ajouter à `.gitignore` :
  ```
  backups/
  *.dump
  *.dump.gz
  *.dump.gz.gpg
  *.tar.gz
  ```
  + Job CI : `find . -size +100M -not -path './.git/*' -not -path './node_modules/*' | head` doit retourner vide.

### 🔴 F-BAK-03 — Dump 2.9 Go présent physiquement sur disque
- **Preuve** : `ls -la backups/` → `lyonflow_20260608_064919Z_postgres.dump.gz` 2.9 Go.
- **Impact** : Croissance en cours (224 Mo → 2.9 Go pendant l'audit) — probablement un process live (dump en cours d'écriture). Le disque va saturer.
- **Action** : Identifier le process (`lsof backups/lyonflow_*.dump.gz`, `ps aux | grep pg_dump`), le killer proprement, puis `rm` le dump. Setup `audit-vps-predeploy.sh` (F-SEC-01) pour ne plus en créer.

---

## Findings HIGH — Résumé (18)

| # | ID | Résumé | Effort |
|---|----|--------|--------|
| 1 | F-SEC-03 | `.gitignore`漏 `backups/`, `*.dump.gz`, `*.tar.gz` (= F-BAK-02) | 15 min |
| 2 | F-SEC-04 | Nginx bloc 80 ne redirige pas vers 443 | 5 min |
| 3 | F-SEC-05 | `lyonflow-backup.service` `ReadWritePaths=/opt/lyonflow/backups` incohérent avec stream pur | 5 min |
| 4 | F-INF-02 | `prometheus-client` non listé explicitement (transitive fragile) | 1 min |
| 5 | F-INF-03 | Grafana fallback `:admin` (`:${GRAFANA_ADMIN_PASSWORD:-admin}`) | 5 min |
| 6 | F-INF-04 | Pas de healthcheck Docker sur service `api` | 15 min |
| 7 | F-INF-05 | Prometheus scrape Airflow `/admin/metrics` sans auth (info leak) | 5 min |
| 8 | F-CQ-02 | 4/6 métriques custom sont du code mort (PERSONA_REQUESTS, DAG_RUNS_TOTAL, MLFLOW_ACTIVE_RUNS, DB_QUERY_DURATION définies mais jamais incrémentées) | 30 min |
| 9 | F-CQ-03 | Pas de `tests/api/test_metrics.py` | 1h |
| 10 | F-CQ-04 | `check-deploy-env.sh` a un prompt interactif (`read -p`) qui casse en CI | 5 min |
| 11 | F-CQ-05 | `audit-vps-predeploy.sh` crée des backups persistants (= F-SEC-01) | 30 min |
| 12 | F-CQ-06 | `backups/*.dump.gz` non ignoré (= F-BAK-02) | 5 min |
| 13 | F-BAK-04 | CI n'a aucun job qui vérifie l'absence de backup local | 1h |
| 14 | F-BAK-05 | `make backup-offsite` (ligne 244) redondant avec `scripts/backup-offsite.sh` (utilise rsync au lieu de rclone rcat) | 30 min |
| 15 | F-DOC-1 | README.md en-tête (lignes 9-17) dit toujours `vps=Phase1 archive` (alignement 54deb7b partiel) | 5 min |
| 16 | F-DOC-2 | `docs/GIT_STRUCTURE.md` totalement désaligné (vps=archive, k8s=Phase2, cloud-demo=Phase3) | 30 min |
| 17 | F-DOC-3 | `docs/REPO_STRUCTURE.md` décrit `kubernetes/` et `cloud-demo/` comme sous-dossiers du repo, mais ABSENTS sur vps — **CRITIQUE pour soutenance Jedha** | 15 min |
| 18 | F-DOC-4 | `docs/DEPLOYMENT.md` section 8 « Migration vers K8s (à venir) » obsolète | 30 min |

---

## Plan d'action recommandé

### 🔴 Immédiat (avant prochain deploy, ~1h)

| Ordre | Action | Effort | Bloquant |
|-------|--------|--------|----------|
| 1 | Ajouter `prometheus-client` + `prometheus-fastapi-instrumentator` à `requirements.txt` + rebuild image API | 5 min | OUI |
| 2 | Remplacer `backup.sh` par `backup-offsite.sh` dans `audit-vps-predeploy.sh:42` + `Makefile:141` | 10 min | OUI |
| 3 | Étendre `.gitignore` (`backups/`, `*.dump.gz`, `*.tar.gz`) | 2 min | OUI |
| 4 | Identifier + killer le process qui écrit dans `backups/` (dump en cours) + supprimer le dump | 15 min | OUI |
| 5 | Patcher `audit-vps-predeploy.sh:58-62` pour ne plus écrire de snapshot local | 30 min | OUI |
| 6 | Ajouter `return 301 https://$host$request_uri;` dans bloc Nginx 80 | 5 min | Recommandé |

### 🟠 Court terme (semaine prochaine, 4-6h)

- Patcher les 18 HIGH findings
- Ajouter job CI qui vérifie l'absence de backup local + fichiers > 100 Mo
- Factoriser les blocs Nginx 80/443 via `include` (F-INF-07)
- Refondre `RUNBOOK.md` (3 contradictions : `find backups -delete` viole OFFSITE, "Grafana à venir" déjà déployé VPS-3, "6 DAGs" alors qu'il y en a 8)
- Patcher README + version (3 versions différentes : 0.5.0-rc1, 0.3.0, 0.6.0)
- Ajouter tests `tests/api/test_metrics.py`

### 🟡 Moyen terme (sprint suivant, 1-2j)

- Patcher les 20 MEDIUM (Prometheus remote_write, healthcheck Docker, OCSP resolver, Grafana provisioning test, etc.)
- Refactoring `Makefile:backup-offsite` pour qu'il appelle `scripts/backup-offsite.sh` au lieu de rsync manuel
- Patcher `monitoring/MONITORING.md` pour refléter les vraies alertes
- Aligner `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, `README.md` (commit 54deb7b a corrigé 50% du problème)

---

## Signaux positifs (ce qui est bien fait)

- ✅ **Isolation branches structurellement saine** : `kubernetes/` et `cloud-demo/` JAMAIS mergés dans `vps` ou `main` (vérifié par `git log`).
- ✅ **Aucun secret hardcodé** : grep sur 9 patterns dans 9 extensions → 0 match dans les fichiers vps.
- ✅ **API FastAPI auth correctement implémentée** : `verify_api_key` (HMAC compare_digest) protège 6 endpoints, fail-closed si API key non configuré.
- ✅ **Métriques custom propres** : pas de PII dans les labels, cardinalité bornée.
- ✅ **`backup-offsite.sh` est un modèle** : stream pur `pg_dump|gzip|gpg|rclone rcat`, AUCUN fichier intermédiaire, fail-fast si pas de destination offsite.
- ✅ **systemd sécurisé** : `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths` explicites, `PrivateTmp=yes`.
- ✅ **Monitoring bien structuré** : 16 alertes avec severity, runbook, inhibitions logiques, retention 30d/10GB.
- ✅ **TLS moderne** : TLS 1.2/1.3, ciphers ECDHE-only, HSTS 1 an, OCSP stapling.
- ✅ **Nginx headers sécurité** : X-Frame-Options, X-Content-Type-Options, XSS, Referrer-Policy.
- ✅ **`check-deploy-env.sh` propre** : `set -euo pipefail`, chmod 600, détection placeholders.
- ✅ **`Makefile` target `deploy-vps` robuste** : rsync avec `--exclude` des data dirs (`.env`, `.deploy.env`, `backups/`, `postgres_data/`, etc.).
- ✅ **CI bloquante** : ruff lint, tests, docker build + Trivy scan, gitleaks.
- ✅ **`VPS_HARDENING.md` est un modèle** : checklist post-déploiement (UFW, fail2ban, SSH key only, etc.).
- ✅ **CHANGELOG.md bien tenu** : 0.6.0 référence les Sprints VPS-1 à VPS-4 (avec un trou de 4 commits post-Sprint, à compléter).

---

## État git et divergences

- **9 commits d'avance sur main**, 0 derrière. Branche linéaire propre.
- **Branches dormantes correctes** : `kubernetes`, `cloud-demo` jamais mergées.
- **Modifs locales non commitées** (5 fichiers dashboard) :
  - `dashboard/components/colors.py` (polish couleurs)
  - `dashboard/components/theme.py` (polish CSS, +245 lignes)
  - `dashboard/components/widgets/elu/executive_summary.py` (typo HTML)
  - `dashboard/components/widgets/elu/kpi_cards.py` (refactor `delta_color`)
  - `dashboard/components/widgets/usager/alert_card.py` (typo HTML)
  - **Recommandation** : Commit séparé (polish UI) ou `git restore` pour reset, AVANT le prochain deploy.
- **Dossier `backups/` 2.9 Go non tracké** : à supprimer (voir F-BAK-03).

---

## Annexes

| Annexe | Fichier | Piste | Source |
|--------|---------|-------|--------|
| 1 | `AUDIT_VPS_securite.md` | Sécurité (mono) | Mavis solo (11 KB, 18 findings) |
| 2 | `AUDIT_VPS_infra.md` | Infra (mono) | Mavis solo (10 KB, 16 findings) |
| 3 | `AUDIT_VPS_code-quality.md` | Code quality | Worker `coder` (27 KB) |
| 4 | `AUDIT_VPS_backup-recovery.md` | Backup | Worker `general` (21 KB) |
| 5 | `AUDIT_VPS_doc-isolation.md` | Doc/isolation | Worker `general` (26 KB) |

**Total** : 5 annexes, ~95 KB de rapports détaillés, 77 findings, 0 modif du repo (audit 100% lecture seule).
