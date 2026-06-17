# Audit Backup & Recovery — branche `vps` (LyonFlowFull)

**Date** : 2026-06-08
**Branche auditée** : `vps` (commit `a05032b`, up to date avec `origin/vps`)
**Périmètre** : stratégie backup PostgreSQL, recovery, audit pre-deploy, systemd timer, CI
**Mode** : LECTURE SEULE (aucune modification de code, commit, ou push)

---

## Executive Summary

**Statut global : 🟡 WARN (correctifs requis avant prochain deploy)**

| Domaine | Statut | Criticité dominante |
|---------|--------|---------------------|
| `backup-offsite.sh` (stream offsite) | ✅ PASS | — |
| Timer systemd `lyonflow-backup.timer` | ✅ PASS | — |
| `check-deploy-env.sh` | ✅ PASS | — |
| `restore.sh` | 🟡 WARN | pas testé E2E, pas de drill documenté |
| `backup.sh` (legacy local) | 🔴 CRITICAL | viole la règle "jamais de backup local" |
| `audit-vps-predeploy.sh` | 🔴 CRITICAL | appelle `backup.sh` au lieu de `backup-offsite.sh` |
| `.gitignore` (formats backup) | 🔴 CRITICAL | `*.dump.gz` NON ignoré |
| `backups/` (2.3 Go sur disque) | 🔴 CRITICAL | fichier réel non tracké ni ignoré |
| CI (pas de garde-fou `backups/`) | 🟠 HIGH | aucune détection de régression |
| `Makefile backup-offsite` (rsync) | 🟠 HIGH | stratégie redondante qui suppose des fichiers locaux |

**3 actions prioritaires** :
1. **CRITIQUE** : Corriger `audit-vps-predeploy.sh` → utiliser `backup-offsite.sh` + `rclone cat` au lieu de `backup.sh` + filesystem local.
2. **CRITIQUE** : Étendre `.gitignore` → ajouter `backups/*.dump.gz`, `backups/*.dump`, `backups/**` complet + décider du sort du dump 2.3 Go (upload offsite, suppression après confirmation user).
3. **HIGH** : Ajouter un job CI qui fail si un fichier `backups/lyonflow_*.dump*` est commité ou qu'un dossier `backups/` non vide dépasse 100 Mo.

---

## Périmètre examiné

| Fichier | Lignes | Lu | Commentaire |
|---------|--------|----|----|
| `scripts/backup-offsite.sh` | 123 | ✅ | Script principal de la stratégie offsite |
| `scripts/audit-vps-predeploy.sh` | 122 | ✅ | Audit pre-deploy |
| `scripts/check-deploy-env.sh` | 45 | ✅ | Vérif env deploy |
| `scripts/backup.sh` | 107 | ✅ | Legacy backup local (à supprimer ?) |
| `scripts/restore.sh` | 101 | ✅ | Restore |
| `scripts/systemd/lyonflow-backup.timer` | 21 | ✅ | Timer systemd |
| `scripts/systemd/lyonflow-backup.service` | 36 | ✅ | Unit systemd backup |
| `scripts/systemd/lyonflow.service` | 50 | ✅ | Unit systemd app |
| `.gitignore` | 73 | ✅ | Patterns ignorés |
| `backups/lyonflow_20260608_064919Z_postgres.dump.gz` | 2.3 Go | ✅ (taille) | Dump non tracké |
| `Makefile` (295 lignes) | — | ✅ | Targets `backup`, `backup-offsite`, `check-deploy-env` |
| `.github/workflows/ci.yml` | 157 | ✅ | Pas de check `backups/` |
| `docs/VPS_HARDENING.md` (extrait §0) | 56 | ✅ | Doc règle offsite |
| `docs/RUNBOOK.md` (extrait) | — | ✅ | Procédure "disque VPS plein" |
| `CHANGELOG.md` (extrait 0.6.0) | — | ✅ | Annonce backup offsite |

---

## Findings

### F-BAK-01 — CRITICAL — `audit-vps-predeploy.sh` utilise `backup.sh` (local) au lieu de `backup-offsite.sh`

**Preuve** :
- `scripts/audit-vps-predeploy.sh:42` : `$SSH 'cd /opt/lyonflow && ./scripts/backup.sh 2>&1 | tail -5'`
- `scripts/audit-vps-predeploy.sh:43` : `BACKUP_FILE=$($SSH 'ls -t /opt/lyonflow/backups/lyonflow_*_postgres.dump 2>/dev/null | head -1')`
- `scripts/audit-vps-predeploy.sh:60-62` : snapshot tar.gz du volume Docker écrit dans `/opt/lyonflow/backups/`
- `scripts/audit-vps-predeploy.sh:108` : `pg_restore --list $BACKUP_FILE` (lit le fichier local sur le VPS)

**Constat** : L'audit pre-deploy viole directement la règle absolue du projet (CLAUDE.md) :

> JAMAIS de backup persistant sur le VPS (full à 100%, 583M libre sur 96G). Toujours offsite via `scripts/backup-offsite.sh`.

À chaque exécution de `audit-vps-predeploy.sh` (avant deploy), on écrit :
- Un dump PostgreSQL complet (~18 Go source → ~5-8 Go compressé) dans `/opt/lyonflow/backups/`
- Un snapshot tar.gz du volume Docker dans `/opt/lyonflow/backups/`

Le VPS a 583 Mo libre. Ces écritures **feront planter le système** (ou échoueront).

**Recommandation** : Refactoriser `audit-vps-predeploy.sh` :
- Étape 1 : `./scripts/backup-offsite.sh` (stream offsite)
- Étape 2 : Snapshot volume via `rclone rcat` (stream) au lieu de `tar czf` local
- Étape 3 : Vérification intégrité via `rclone cat gdrive:... | gunzip | gpg -d | pg_restore --list | head -10` (jamais de fichier local)
- Étape 4 : Si l'archive ne peut pas être lue via stream (à cause de `pg_restore --list` qui n'est pas streamable), créer une alternative type `--to-stdout | head -n 10` après extraction partielle.

**Effort** : M (1-2h, réécriture de la logique d'audit + tests SSH/rclone).

---

### F-BAK-02 — CRITICAL — `.gitignore` n'ignore pas les fichiers `*.dump.gz` (et la moitié des variantes)

**Preuve** :
```
$ git check-ignore -v backups/lyonflow_20260608_064919Z_postgres.dump.gz
exit: 1   # = NOT ignored

$ git check-ignore -v backups/test.dump
.gitignore:64:backups/*.dump	backups/test.dump
exit: 0   # = ignored

$ git check-ignore -v backups/test.dump.gz
exit: 1   # = NOT ignored
```

**Patterns actuels dans `.gitignore`** (lignes 63-65) :
```
backups/*.sql
backups/*.dump
backups/*.tar.gz
```

`*.dump.gz` n'est pas couvert. Le dump réel (`.dump.gz`) sera tracké par un éventuel `git add .` ou un commit accidentel.

**Recommandation** : Remplacer par une ligne omnibus + cas particulier :
```gitignore
# Backups (STRICT — jamais commité, jamais sur disque VPS)
backups/
backups/**
!.gitkeep
```

**Effort** : XS (5 min).

---

### F-BAK-03 — CRITICAL — Dump 2.3 Go sur disque local (violation directe règle)

**Preuve** :
```
$ du -sh backups/
2.2G	backups/
2.2G	backups/lyonflow_20260608_064919Z_postgres.dump.gz
$ git status
Untracked files:
  ...
  backups/
```

**Constat** :
1. Le dump fait **2.3 Go** (pas 224 Mo comme indiqué dans la tâche — la taille a évolué).
2. Il est sur le disque du dev/local — pas sur le VPS (donc violation du même esprit sur la machine de dev, et présage de ce qui se passerait sur le VPS via `backup.sh`/`audit-vps-predeploy.sh`).
3. Il n'est pas ignoré (cf. F-BAK-02) — donc traçable.
4. Il n'est pas uploadé offsite (le script `backup-offsite.sh` n'a pas été exécuté sur cet environnement).

**Recommandation** (ordre d'action) :
1. **Confirmer avec Patrice** : le dump est-il issu d'un test E2E local, ou est-ce un dump de prod potentiel ?
2. **Si test/dev** : supprimer le fichier (`mavis-trash backups/lyonflow_20260608_064919Z_postgres.dump.gz`).
3. **Si données prod à conserver** : uploader via `rclone rcat` vers Google Drive (`backups/lyonflow/`), puis supprimer du local.
4. **Ajouter `backups/` au `.gitignore`** (cf. F-BAK-02) pour éviter récidive.

**Effort** : S (10 min, demande confirmation user).

---

### F-BAK-04 — HIGH — Aucun job CI ne détecte la réintroduction de backups locaux

**Preuve** :
```
$ grep -n "backup" .github/workflows/ci.yml
# (aucun match)
```

Le CI vérifie : lint, mypy, security (bandit/gitleaks/pip-audit), tests, docker-build. **Aucun job** ne vérifie :
- Qu'aucun fichier `backups/lyonflow_*.dump*` n'est commité.
- Qu'aucun dossier `backups/` > 100 Mo n'est présent.
- Que les scripts de backup respectent la règle (ex. pas de `> $BACKUP_DIR` non streamé).

**Recommandation** : Ajouter un job `backup-policy` dans `ci.yml` :
```yaml
backup-policy:
  name: Backup policy check
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Check no backup files in repo
      run: |
        ! git ls-files | grep -E '^backups/.*\.(dump|gz|tar|sql)$' && \
        ! find backups/ -type f -size +100M 2>/dev/null
    - name: Check backup-offsite.sh does not write to disk
      run: |
        ! grep -E '>\s*\S+\.(dump|gz|sql)\b' scripts/backup-offsite.sh
```

**Effort** : S (15 min).

---

### F-BAK-05 — HIGH — Stratégie `Makefile backup-offsite` redondante (rsync sur dossier local)

**Preuve** : `Makefile:244-251` :
```makefile
backup-offsite:  ## Push backup vers serveur distant (rsync over SSH)
    ...
    rsync -avz --delete -e "ssh -i $(SSH_KEY)" \
        backups/ $$OFFSITE_HOST:~/lyonflow-backups/
```

**Constat** : Cette cible **suppose** que `backups/` existe localement (donc que `backup.sh` a été exécuté). C'est une chaîne `backup.sh` → `Makefile backup-offsite` qui **utilise deux scripts redondants** et viole l'esprit de la règle offsite (le dump transite par le disque VPS avant d'être rsync).

**Recommandation** : 
- **Option A (préférée)** : Supprimer cette cible, forcer l'usage de `scripts/backup-offsite.sh` partout.
- **Option B** : Renommer en `backup-offsite-legacy` + DEPRECATED warning + pointer vers `backup-offsite.sh`.
- Documenter la différence dans `Makefile` (commentaire).

**Effort** : S (10 min).

---

### F-BAK-06 — MEDIUM — `restore.sh` documenté mais pas testé E2E (drill backup manquant)

**Preuve** :
- `docs/PIPELINE_AUDIT_AND_PLAN.md:28` : `| Backup/restore | ✅ Scripts OK, jamais testés E2E | **70%** |`
- `docs/PIPELINE_AUDIT_AND_PLAN.md:243-249` : `### 4.7 MINEUR — Pas de backup verification` (constat + fix proposé : "Cron mensuel qui restore un backup aléatoire dans une DB")
- `docs/RUNBOOK.md:143` : Monthly checklist `Backup verification : tester un restore` — checklist, pas automation.

**Constat** : Aucun test automatisé ne restore un backup de prod et vérifie son intégrité. Si le dump est corrompu, on le découvrira au pire moment.

**Recommandation** :
1. Ajouter `tests/integration/test_backup_restore_drill.py` qui :
   - Télécharge/restore un dump depuis Google Drive
   - Crée une DB éphémère (`lyonflow_restore_drill`)
   - `pg_restore` dedans
   - Vérifie `n_live_tup` sur quelques tables critiques
   - Drop la DB
2. Lancer via cron mensuel + alerte si KO.
3. Documenter procédure drill dans `RUNBOOK.md` (déjà checklist, manque commande).

**Effort** : M (1-2h pour le test + cron).

---

### F-BAK-07 — MEDIUM — `backup.sh` legacy non décommissionné (source de confusion)

**Preuve** :
- `scripts/backup.sh` existe toujours (107 lignes).
- Il écrit dans `${PROJECT_ROOT}/backups/` (LOCAL).
- Il est appelé par `Makefile backup` (Makefile:140) et `audit-vps-predeploy.sh:42`.
- Le commentaire d'en-tête (ligne 5) dit `Rétention : 7j local, envoi S3/MinIO distant optionnel` — ce qui contredit la nouvelle règle.

**Constat** : Bien que le bon script (`backup-offsite.sh`) existe et que le timer systemd l'utilise, `backup.sh` reste :
- Appelé par `Makefile backup` (target par défaut `make backup` → LOCAL, pas offsite).
- Appelé par `audit-vps-predeploy.sh` (cf. F-BAK-01).
- Non marqué comme DEPRECATED.

**Risque** : Un dev/sysadmin qui lance `make backup` (commande naturelle) crée un dump local qui remplit le disque et n'est pas envoyé offsite. Aucune alerte.

**Recommandation** :
1. Renommer `backup.sh` → `backup-local-DEPRECATED.sh` (ou supprimer).
2. `Makefile backup` → appeler `backup-offsite.sh` avec un wrapper explicite.
3. Ajouter bannière DEPRECATED en tête de `backup.sh` (si conservé pour référence).

**Effort** : S (15 min).

---

### F-BAK-08 — MEDIUM — `lyonflow-backup.service` n'a pas de préflight `RequiresMountsFor`

**Preuve** : `scripts/systemd/lyonflow-backup.service` :
```ini
[Service]
WorkingDirectory=/opt/lyonflow
EnvironmentFile=/opt/lyonflow/.env
EnvironmentFile=-/opt/lyonflow/.deploy.env
ExecStart=/opt/lyonflow/scripts/backup-offsite.sh
ProtectSystem=strict
ReadWritePaths=/opt/lyonflow/backups
PrivateTmp=yes
TimeoutStartSec=2h
```

**Constat** :
- `RequiresMountsFor=` absent — si `/opt/lyonflow` est sur un montage réseau et qu'il n'est pas dispo au boot, le timer (avec `Persistent=true`) échouera sans retry clair.
- `ReadWritePaths=/opt/lyonflow/backups` — la règle projet dit "jamais de backup local" → ce path ne devrait jamais être écrit. Si le script respecte sa propre pipeline (stream only), c'est inutile ; si quelqu'un modifie le script pour écrire un fichier temp, ce path l'autorise.
- Pas de `CPUQuota=` ou `MemoryMax=` → un rclone en run-away peut manger toutes les ressources.

**Recommandation** :
- Retirer `ReadWritePaths=/opt/lyonflow/backups` (le script offsite ne doit RIEN écrire).
- Ajouter `MemoryMax=2G` et `CPUQuota=200%` (cohabite avec `lyonflow.service` qui prend 400%).
- Ajouter `RequiresMountsFor=/opt/lyonflow` (robustesse boot).

**Effort** : S (10 min).

---

### F-BAK-09 — LOW — `rclone rcat` sans `--timeout` / `--retries` explicites

**Preuve** : `scripts/backup-offsite.sh:101` :
```bash
$PG_DUMP_CMD | gzip | $GPG_CMD | rclone rcat "gdrive:${GDRIVE_BACKUP_DEST}/${FINAL_NAME}" --progress
```

**Constat** : Si la connexion Google Drive hangue, `pg_dump` continue à produire (le pipe buffer remplit la RAM) jusqu'à OOM kill. Pas de `--timeout`, pas de `--retries`.

**Recommandation** : Wrapper avec timeout + health-check :
```bash
# Dans le script offsite :
timeout 90m bash -c '$PG_DUMP_CMD | gzip | $GPG_CMD | rclone rcat ... --timeout 30m --retries 3 --low-level-retries 5'
```

**Effort** : S (10 min).

---

### F-BAK-10 — LOW — Pas de monitoring de la SUCCÈS du backup quotidien

**Preuve** :
- Timer systemd déclenché : oui (`OnCalendar=*-*-* 03:00:00`, `Persistent=true`).
- Logs : `journalctl -u lyonflow-backup` (ligne 23-24 service).
- Monitoring Prometheus : aucun metric sur l'âge/échec du dernier backup.

**Constat** : Si le backup offsite échoue silencieusement (rclone timeout, OAuth expiré, etc.), personne n'est alerté tant qu'on n'a pas besoin de restore.

**Recommandation** : Ajouter une metric `lyonflow_backup_last_success_timestamp_seconds` (Gauge, mis à jour via un script post-backup ou un cron check). Alerte Prometheus `BackupStale` (silence > 26h).

**Effort** : M (1h, exporter + alerte).

---

### F-BAK-11 — LOW — Documentation `restore.sh` minimale (pas de procédure de bout en bout)

**Preuve** : `scripts/restore.sh:6-12` :
```
# Usage : ./scripts/restore.sh /path/to/backup/lyonflow_20260606_030000
```

Le script prend un `BACKUP_PATH` local. Mais comme la stratégie est offsite (gdrive), l'utilisateur doit d'abord faire `rclone cat` ou `rclone copy` pour récupérer le dump → puis lancer `restore.sh`. Cette procédure n'est pas documentée.

**Constat** : Le seul indice est dans `scripts/backup-offsite.sh:121` :
```
rclone cat 'gdrive:${GDRIVE_BACKUP_DEST:-}/$FINAL_NAME' | gunzip | gpg -d | pg_restore -U lyonflow -d lyonflow
```
Mais c'est en commentaire dans le script de backup, pas dans un runbook.

**Recommandation** : Ajouter une section dans `docs/RUNBOOK.md` :
```markdown
### Restore depuis Google Drive
# 1. Lister les backups
rclone ls gdrive:backups/lyonflow/ | sort

# 2. Choisir un backup (ex: lyonflow_20260607_030000Z_postgres.dump.gz.gpg)
# 3. Stream restore
ssh ubuntu@VPS 'rclone cat gdrive:backups/lyonflow/<fichier> | gunzip | gpg -d | docker exec -i lyonflow-postgres pg_restore -U lyonflow -d lyonflow --clean --if-exists'
```

**Effort** : S (15 min).

---

### F-BAK-12 — INFO — `backup-offsite.sh` est propre (✅ stream pur, conforme)

**Preuve** :
- Ligne 32 : `set -euo pipefail` (bon).
- Lignes 64-70 : `pg_dump` en stream via docker exec, pas de `-f` fichier.
- Ligne 101 : `$PG_DUMP_CMD | gzip | $GPG_CMD | rclone rcat "gdrive:..." --progress` → **AUCUN fichier intermédiaire sur disque**.
- Ligne 105 : variante SSH idem.
- Ligne 111 : `SIZE_HUMAN=$(du -h /opt/lyonflow/data 2>/dev/null ...)` — c'est juste pour le log, pas un write.

**Constat** : Ce script est **propre et conforme à la règle**. Il est la référence pour les autres scripts.

---

### F-BAK-13 — INFO — Timer systemd est correct (✅ 03:00 + Persistent)

**Preuve** : `scripts/systemd/lyonflow-backup.timer` :
- `OnCalendar=*-*-* 03:00:00` ✅ (3h du matin comme indiqué dans CLAUDE.md)
- `Persistent=true` ✅ (rattrape les runs manqués après reboot)
- `RandomizedDelaySec=300` ✅ (évite les spikes)
- `WantedBy=timers.target` ✅
- Service lié : `lyonflow-backup.service` → `ExecStart=/opt/lyonflow/scripts/backup-offsite.sh` ✅

**Constat** : Timer conforme aux exigences, appelle bien le script offsite (pas `backup.sh`).

---

### F-BAK-14 — INFO — `check-deploy-env.sh` est propre (✅ chmod 600 + détection defaults)

**Preuve** : `scripts/check-deploy-env.sh` :
- `set -euo pipefail` (ligne 8)
- Vérifie présence fichier (ligne 12)
- `stat` permissions (ligne 19)
- Si != 600, propose fix interactif (lignes 22-32)
- Boucle sur vars critiques `VPS_HOST VPS_SSH_KEY VPS_DEPLOY_PATH DEPLOY_BRANCH` (ligne 37)
- Détection valeurs par défaut `VOTRE_*` et `*example*` (ligne 39)

**Constat** : Script propre, bloque deploy si env mal configuré.

---

## Synthèse par criticité

| # | ID | Titre | Criticité | Effort | Bloquant prod ? |
|---|----|-------|-----------|--------|-----------------|
| 1 | F-BAK-01 | audit-vps-predeploy.sh utilise backup.sh (local) | CRITICAL | M | OUI |
| 2 | F-BAK-02 | .gitignore manque `*.dump.gz` | CRITICAL | XS | OUI |
| 3 | F-BAK-03 | Dump 2.3 Go sur disque non ignoré | CRITICAL | S | OUI |
| 4 | F-BAK-04 | CI : pas de check backups/ | HIGH | S | NON (mais recommandé) |
| 5 | F-BAK-05 | Makefile backup-offsite (rsync) redondant | HIGH | S | NON |
| 6 | F-BAK-06 | restore.sh jamais testé E2E | MEDIUM | M | NON |
| 7 | F-BAK-07 | backup.sh legacy non décommissionné | MEDIUM | S | NON |
| 8 | F-BAK-08 | systemd service : hardening manquant | MEDIUM | S | NON |
| 9 | F-BAK-09 | rclone rcat : pas de timeout | LOW | S | NON |
| 10 | F-BAK-10 | Pas de monitoring succès backup | LOW | M | NON |
| 11 | F-BAK-11 | Doc restore depuis offsite | LOW | S | NON |
| 12 | F-BAK-12 | backup-offsite.sh propre | INFO | — | — |
| 13 | F-BAK-13 | Timer systemd conforme | INFO | — | — |
| 14 | F-BAK-14 | check-deploy-env.sh propre | INFO | — | — |

---

## Plan d'action recommandé

### 🔴 Immédiat (avant prochain deploy)

1. **F-BAK-02** : Étendre `.gitignore` avec `backups/` + `backups/**` (5 min).
2. **F-BAK-03** : Décider du sort du dump 2.3 Go actuel (confirmation user) :
   - Option recommandée : `mavis-trash backups/lyonflow_20260608_064919Z_postgres.dump.gz` (test/dev) OU upload gdrive d'abord si prod (10 min).
3. **F-BAK-01** : Patcher `audit-vps-predeploy.sh` pour utiliser `backup-offsite.sh` + `rclone cat` (1-2h, test SSH requis).

### 🟠 Court terme (semaine)

4. **F-BAK-04** : Ajouter job CI `backup-policy` qui fail si backup local (15 min).
5. **F-BAK-05** : Décommissionner `Makefile backup-offsite` (rsync) — pointer vers `backup-offsite.sh` (10 min).
6. **F-BAK-07** : Renommer `backup.sh` en `backup-local-DEPRECATED.sh` avec bannière (15 min).
7. **F-BAK-08** : Durcir `lyonflow-backup.service` : retirer `ReadWritePaths=/opt/lyonflow/backups`, ajouter `MemoryMax`, `RequiresMountsFor` (10 min).

### 🟡 Moyen terme (sprint suivant)

8. **F-BAK-06** : Implémenter `tests/integration/test_backup_restore_drill.py` + cron mensuel (1-2h).
9. **F-BAK-10** : Ajouter métrique `lyonflow_backup_last_success_timestamp` + alerte Prometheus (1h).
10. **F-BAK-11** : Documenter procédure restore depuis Google Drive dans `RUNBOOK.md` (15 min).
11. **F-BAK-09** : Wrapper `rclone rcat` avec `--timeout --retries` (10 min).

---

## Conformité aux règles du projet (CLAUDE.md)

| Règle | Statut | Notes |
|-------|--------|-------|
| "JAMAIS de backup persistant sur le VPS" | 🔴 VIOLÉE | `backup.sh` + `audit-vps-predeploy.sh` violent la règle |
| "Stream pur, rien d'écrit sur le disque VPS" | ✅ RESPECTÉE (partiel) | `backup-offsite.sh` est OK ; `audit-vps-predeploy.sh` non |
| "Rétention 7j" (historique) | N/A | Nouvelle stratégie : offsite only, pas de rétention locale |
| `scripts/backup-offsite.sh` = référence | ✅ OK | Script propre, conforme |

---

## Notes pour le verifier

1. **Fichier dump actuel** : `backups/lyonflow_20260608_064919Z_postgres.dump.gz` (2.3 Go) — n'est PAS dans `.gitignore` (vérifié via `git check-ignore`, exit 1). Si vous voulez confirmer :
   ```bash
   cd /Users/patriceduclos/Documents/Lyonfull && git check-ignore -v backups/lyonflow_20260608_064919Z_postgres.dump.gz
   ```
   Le `git status` actuel montre bien `backups/` dans "Untracked files", pas dans "Ignored files".

2. **audit-vps-predeploy.sh** : j'ai lu ligne 42 (`./scripts/backup.sh`) — c'est `backup.sh`, pas `backup-offsite.sh`. C'est une violation directe.

3. **Pas de modification appliquée** : rapport only, comme demandé par le protocol (LECTURE SEULE). Les corrections (F-BAK-01 à F-BAK-11) sont des recommandations, à discuter avec Patrice avant implémentation.

4. **Syncronisation avec autres audits** : le finding F-BAK-03 (dump 2.3 Go) est probablement aussi remonté dans `security-audit` (PII / credentials potentiellement dans le dump) et `infra-audit` (disque). À centraliser dans le rapport de synthèse final.

5. **Pas de tests automatisés** : le dossier `tests/` n'a aucun test de backup/restore (vérifié via `grep`). Donc F-BAK-06 (drill restore) est confirmé par absence.

6. **Coordination team** : entrée board mise à jour à 08:58:30.
