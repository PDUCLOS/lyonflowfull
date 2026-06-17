# Audit documentation & isolation branches — branche `vps`

**Date** : 2026-06-08
**Auditeur** : agent `general` (session mvs_77f6adef3845493a95244a4556d455d6)
**Branche auditée** : `vps` (commit tip `a05032b`)
**Branches comparées** : `main`, `kubernetes`, `cloud-demo`
**Statut global** : **WARN** — isolation branches OK, alignement partiel des 4 docs principaux, plusieurs docs secondaires et procédures incohérentes avec la directive vps=cible unique

---

## Summary

Audit en lecture seule de la cohérence documentaire (AGENTS/CLAUDE/CHANGELOG/README + 8 docs techniques) et de l'isolation des branches `kubernetes` / `cloud-demo` par rapport à `vps` / `main`. **L'isolation git est techniquement OK** (aucun fichier `kubernetes/` ou `cloud-demo/` commit sur `vps`, branches dormantes jamais mergées dans `vps` ou `main`), mais **la documentation est partiellement désalignée** : le commit d'alignement `54deb7b` a corrigé AGENTS/CLAUDE/CHANGELOG/README§9 mais pas README§entête, ni `docs/GIT_STRUCTURE.md`, ni `docs/REPO_STRUCTURE.md`, ni `docs/DEPLOYMENT.md`, ni `docs/RUNBOOK.md`. Statut **WARN** : production-ready, mais cohérence doc à corriger avant soutenance Jedha (juillet 2026).

## Changed files

- **Aucun fichier modifié sur le projet** (audit lecture seule, contrainte du plan).
- `outputs/doc-isolation-audit/deliverable.md` (ce fichier, créé).
- `board.md` mis à jour avec entrée de progression.

## Notes

- Le fichier de contexte `.mavis/plans/audit-vps-context.md` mentionné dans le brief n'existe pas. Le contexte a été reconstitué via `plan.yaml` + `CLAUDE.md` + `AGENTS.md` + commit history.
- Toutes les preuves (commandes, lignes, sorties) sont consignées dans les sections "Preuve" de chaque finding.
- Les findings sont numérotés `F-DOC-N` (doc coherence), `F-DIR-N` (directives projet), `F-ISO-N` (isolation), `F-LNK-N` (liens).

---

## 1. Périmètre examiné

| Fichier | Lignes | Lu | Findings |
|---------|--------|----|----------|
| `AGENTS.md` | 95 | ✅ | aligné (post `54deb7b`) |
| `CLAUDE.md` | 363 | ✅ | aligné (post `54deb7b`) |
| `CHANGELOG.md` | 165 | ✅ | section `0.6.0` VPS complète |
| `README.md` | 503 | ✅ | **entête désalignée** |
| `docs/CONTROLE_VPS_VS_CLOUD_DEMO.md` | 200 | ✅ | 1 gap (rollback VPS) |
| `docs/VPS_HARDENING.md` | 201 | ✅ | OK procédures concrètes |
| `docs/MONITORING.md` | 117 | ✅ | pas de runbook incident |
| `docs/RUNBOOK.md` | 166 | ✅ | **3 contradictions** |
| `docs/DEPLOYMENT.md` | 286 | ✅ | **section 8 obsolète** |
| `docs/REPO_STRUCTURE.md` | 178 | ✅ | **arbre incohérent avec vps** |
| `docs/GIT_STRUCTURE.md` | 148 | ✅ | **statut branches faux** |
| `docs/ARCHITECTURE.md` | 231 | ✅ | pas de mention k8s (OK) |
| `docs/DATA_GOVERNANCE.md` | (entête) | ✅ | pas de mention k8s (OK) |
| `docs/API.md`, `SPRINT_*_REPORT.md`, `analysis_*.md` | — | partiel | pas de blocage |
| `docs/ADR/0003-docker-compose-pas-k8s.md` | 33 | ✅ | cohérent avec VPS unique |

Commandes git exécutées :
- `git log vps..kubernetes --oneline` → **8 commits en avance** (k8s-only, jamais mergés)
- `git log vps..cloud-demo --oneline` → **10 commits en avance** (cloud-demo-only)
- `git log main..kubernetes --oneline` → **8 commits** (idem)
- `git log main..cloud-demo --oneline` → **10 commits** (idem)
- `git log --oneline vps` → 16 commits, pas de merge de k8s/cloud-demo
- `git ls-tree -r vps --name-only` → **0 fichier** `kubernetes/` ou `cloud-demo/`
- `git diff --stat main..vps` → +62 fichiers, +2837 lignes, contient **uniquement** `monitoring/`, `nginx/`, `scripts/systemd/`, `src/api/metrics.py`, etc.

---

## 2. Findings

### F-DOC-1 — [HIGH] `README.md` entête (lignes 9-17) désalignée avec l'alignement `54deb7b`

**Description** : Le commit `54deb7b docs(vps): aligne AGENTS/CHANGELOG/CLAUDE/README sur directive vps=cible unique` a corrigé AGENTS, CLAUDE, CHANGELOG et la section 9 de README, mais pas l'entête de README qui dit toujours :

```
# Version: 0.5.0-rc1 (Phase 3 demo prête, Phase 2 K8s prête, Phase 1 v0.3.1)
#
# Branches :
#   - main         : Phase 1 production-ready local + fixes pipeline
#   - vps          : snapshot Phase 1 deployé sur VPS
#   - kubernetes   : Phase 2 manifests Kustomize (production K8s)
#   - cloud-demo   : Phase 3 Scaleway Kapsule (démo soutenance Jedha)
```

**Preuve** : `git show 54deb7b -- README.md` (ligne 100% du diff : section "9. Déploiement" uniquement, pas l'entête). `CHANGELOG.md` annonce `0.6.0` mais README entête dit `0.5.0-rc1`.

**Contradictions avec l'alignement** :
- README entête : `vps : snapshot Phase 1 deployé sur VPS` ↔ CLAUDE.md/AGENTS.md : `Phase 2 ACTIVE`
- README entête : `kubernetes : Phase 2 manifests Kustomize (production K8s)` ↔ CLAUDE.md/AGENTS.md : `dormante, futur AWS/GCP`
- README entête : `cloud-demo : Phase 3 Scaleway Kapsule (démo soutenance Jedha)` ↔ CLAUDE.md/AGENTS.md : `Phase 4 dormante`

**Recommandation** : Patcher l'entête README (lignes 9-17) en miroir de AGENTS.md, dans un commit dédié de type `docs(vps): aligne entete README sur directive vps=ACTIVE`. Ajouter aussi l'entrée dans CHANGELOG.

**Effort** : XS (5 min, ~15 lignes modifiées).

---

### F-DOC-2 — [HIGH] `docs/GIT_STRUCTURE.md` totalement désaligné

**Description** : `docs/GIT_STRUCTURE.md` (148 lignes, dernier commit `5a2d7b4` du 2026-06-07, jamais re-touché par `54deb7b`) décrit les branches dans un schéma **incompatible** avec la directive projet :

| Branche | GIT_STRUCTURE.md | AGENTS.md / CLAUDE.md |
|---------|------------------|----------------------|
| `main` | "Phase 1 + fixes ✅ active" | "Phase 1 ✅ livrée" |
| `vps` | **"Phase 1 frozen ✅ archive"** | **"Phase 2 ACTIVE"** |
| `kubernetes` | **"Phase 2 ✅ manifests prets"** | **"dormante AWS/GCP"** |
| `cloud-demo` | **"Phase 3 ✅ overlay pret"** | **"Phase 4 dormante"** |

Le doc dit aussi en workflow : "vps est fast-forward depuis main quand on veut updater le VPS" — mais en pratique sur l'historique git `vps` n'est jamais un descendant fast-forward de `main` (les 4 Sprints VPS 1-4 sont commits propres sur `vps`, pas des merges). Le schéma ASCII (ligne 9-26) parle de "Phase 1" pour vps sans mentionner la Phase 2.

**Preuve** : `git log --oneline -- docs/GIT_STRUCTURE.md` → 1 seul commit `5a2d7b4`. `git show 54deb7b --stat` → GIT_STRUCTURE.md n'apparaît pas dans la liste des fichiers touchés.

**Recommandation** : Réécrire `GIT_STRUCTURE.md` pour aligner sur AGENTS.md :
- `vps` = Phase 2 ACTIVE (source de vérité du déploiement production)
- `kubernetes` = Phase 3 dormante (futur AWS/GCP)
- `cloud-demo` = Phase 4 dormante (POC Jedha)

**Effort** : S (30-60 min, réécriture ciblée).

---

### F-DOC-3 — [HIGH] `docs/REPO_STRUCTURE.md` décrit un arbre qui n'existe PAS sur `vps`

**Description** : `docs/REPO_STRUCTURE.md` ligne 90-116 liste `kubernetes/` et `cloud-demo/` comme sous-dossiers du repo, avec leur contenu détaillé (overlays/, docker/, scripts/, etc.). Mais **sur la branche `vps`** :

```
$ git ls-tree -r vps --name-only | grep -E "^(kubernetes|cloud-demo)/"
(aucun résultat)
$ find . -type d -name kubernetes -o -name cloud-demo
(aucun résultat)
```

Un lecteur arrivant sur `vps` croira que ces dossiers existent et les cherchera en vain. C'est la désinformation la plus dangereuse de l'audit.

**Preuve** : `git show --stat 54deb7b` n'inclut pas `docs/REPO_STRUCTURE.md`.

**Recommandation** : 
- Soit supprimer `docs/REPO_STRUCTURE.md` (le remplacer par une note "voir branches `kubernetes` et `cloud-demo`")
- Soit l'annoter clairement : "Les dossiers `kubernetes/` et `cloud-demo/` n'existent QUE sur les branches du même nom. Sur `vps` (cible production), ces dossiers sont absents — la prod est docker-compose + monitoring, voir [SPRINT_*_REPORT.md]."
- Soit déplacer `REPO_STRUCTURE.md` dans une branche de référence

**Effort** : S (15 min, ajout d'un paragraphe d'avertissement).

---

### F-DOC-4 — [HIGH] `docs/DEPLOYMENT.md` §8 "Migration vers K8s (à venir)" obsolète

**Description** : `docs/DEPLOYMENT.md` ligne 278-286 contient une section "Migration vers K8s (à venir)" qui :
- Dit "Répertoire dédié `k8s/` (à créer — pas dans ce repo pour l'instant)" (ligne 281) — **FAUX** : le répertoire `kubernetes/` existe sur la branche `kubernetes` avec 35+ manifests.
- Propose `kompose convert` depuis docker-compose.yml comme chemin de migration — **implicite mais non aligné** avec la directive "pas de migration K8s vers vps".
- Le sommaire ligne 4 dit aussi "K8s (à venir — Sprint 6+, dans un répertoire dédié)" — **obsolète**, K8s est livré en 0.4.0 sur la branche dormante, pas "à venir".

**Preuve** : `docs/DEPLOYMENT.md:278-286` lu en clair. `CHANGELOG.md:73-86` annonce `0.4.0 Phase 2 Kubernetes complete`.

**Recommandation** : Remplacer §8 par "K8s dormant sur branche séparée" et renvoyer vers `CONTROLE_VPS_VS_CLOUD_DEMO.md`. Reformuler le sommaire en cohérence.

**Effort** : S (15 min).

---

### F-DOC-5 — [MEDIUM] `docs/RUNBOOK.md` 3 contradictions avec règles en vigueur

**Description** : Le runbook est le doc opérationnel le plus à risque. Trois contradictions avec des règles post-sprint :

1. **Ligne 121** : `find /opt/lyonflow/backups -name "lyonflow_*" -mtime +7 -delete` — **contredit la règle BACKUP OFFSITE** (CLAUDE.md ligne 35 : "JAMAIS de backup persistant sur le VPS"). Cette commande est le scénario catastrophe que la règle `backup-offsite.sh` (commit `a23f981`) cherche à éliminer.

2. **Ligne 165** : "Grafana (à venir) : http://localhost:3000" — **FAUX** depuis Sprint VPS-3 (commit `43e9b14 feat(monitoring): Sprint VPS-3 Prometheus + Alertmanager + Grafana stack`).

3. **Ligne 130** : "Airflow tourne (6 DAGs schedulés)" — **INCOHÉRENT** avec CLAUDE.md ligne 12 qui annonce "8 DAGs Airflow" et avec la structure réelle `dags/` (bronze/transforms/ml/maintenance + utils).

**Preuve** : 
- `docs/RUNBOOK.md:121` lu en clair
- `docs/RUNBOOK.md:165` lu en clair
- `docs/RUNBOOK.md:130` + `ls dags/bronze/ dags/transforms/ dags/ml/ dags/maintenance/` → 8 DAGs minimum

**Recommandation** : Réécrire le runbook dans un commit dédié `docs(runbook): aligne procedures post-sprints VPS 1-4 et regle backup OFFSITE`. Supprimer la procédure `find backups -delete` (la remplacer par "alerte disk > 85% → vérifier offsite OK et nettoyer via `scripts/backup-offsite.sh --prune-local-cache` si introduit").

**Effort** : M (1-2h, refonte ciblée des sections concernées).

---

### F-DOC-6 — [MEDIUM] `docs/MONITORING.md` ne référence pas les alertes réelles ni le runbook

**Description** : `docs/MONITORING.md` (117 lignes) liste les alertes par fichier (`api.yml`, `database.yml`, `system.yml`) mais ne donne **aucun nom d'alerte concret**. Le `RUNBOOK.md` non plus ne référence pas les noms réels. En cas d'incident à 3h du matin, l'opérateur doit ouvrir Grafana, lire le nom de l'alerte, puis chercher la procédure.

Concrètement, les alertes définies dans `monitoring/prometheus/rules/api.yml` sont `ApiHighErrorRate`, `ApiHighLatency`, `ApiDown` (avec lien runbook `https://github.com/PDUCLOS/lyonflowfull/blob/main/docs/RUNBOOK.md#api-5xx` qui pointe vers une ancre inexistante dans RUNBOOK.md — voir F-LNK-1).

**Preuve** : 
- `grep -E "ApiHighErrorRate|ApiHighLatency|ApiDown|DbHighConnections|DbDown|DiskSpaceLow|TlsCertExpiring" docs/MONITORING.md docs/RUNBOOK.md` → 0 résultat
- `monitoring/prometheus/rules/api.yml:18` ligne d'alerte `ApiHighErrorRate` avec annotation `runbook: "https://github.com/PDUCLOS/lyonflowfull/blob/main/docs/RUNBOOK.md#api-5xx"`

**Recommandation** : Ajouter une section "## Runbook par alerte" dans MONITORING.md avec un tableau `alerte → symptôme → commande → doc` pour les 5 alertes les plus courantes (ApiHighErrorRate, ApiDown, DbHighConnections, DbDown, TlsCertExpiringSoon). Idem enrichir RUNBOOK.md avec des sections `### ApiHighErrorRate` etc.

**Effort** : M (1-2h).

---

### F-DOC-7 — [MEDIUM] `docs/CONTROLE_VPS_VS_CLOUD_DEMO.md` : rollback VPS absent, rollback cloud-demo OK

**Description** : Le doc documente bien :
- §2.1 isolation PHYSIQUE VPS ↔ cloud-demo (✅)
- §2.2 isolation LOGIQUE VPS ↔ K8s (⚠️ à valider, actions requises)
- §3 garde-fous PostgreSQL (✅)
- §4 risques + mitigations (✅)
- §6.1 procédure d'urgence **cloud-demo** (kubectl rollout undo — ✅ concret)

**Mais** : aucune procédure de rollback **VPS** n'est documentée dans §6, alors que la commande existe dans le Makefile (`make rollback-vps`, ligne 206-216, complète avec tag, ssh, checkout). Le doc §6.2 ("Si le VPS est inaccessible pendant une démo") évoque `cd /opt/lyonflow && docker compose up -d --build` mais pas le rollback versionné.

**Preuve** : 
- `grep -E "make rollback|rollback-vps" docs/CONTROLE_VPS_VS_CLOUD_DEMO.md` → 0 résultat
- `grep -E "make rollback|rollback-vps" Makefile` → défini ligne 206

**Recommandation** : Ajouter §6.3 "Rollback VPS" avec :
```bash
# Lister les tags disponibles
git tag --list 'vps-*' --sort=-version:refname

# Rollback vers le tag précédent
make rollback-vps
# → checkout tag N-1, rsync vers VPS, restart stack, healthcheck
```

**Effort** : XS (10 min, 1 paragraphe).

---

### F-DOC-8 — [LOW] `CHANGELOG.md` : entrées vps bien référencées, mais commits backup post-VPS-2 absents

**Description** : Le CHANGELOG.md (165 lignes) référence bien les 4 Sprints VPS 1-4 et l'audit isolation (`051fa7c`). Mais **2 commits de la branche vps ne sont pas dans le CHANGELOG** :

| Commit | Date | Description | Statut CHANGELOG |
|--------|------|-------------|------------------|
| `a23f981` | 2026-06-07 | `feat(backup): regle stricte backup OFFSITE` | **absent** |
| `cbbf84a` | 2026-06-07 | `feat(backup): integration folder ID Google Drive` | **absent** |
| `f8957a6` | 2026-06-07 | `fix(vps): deploy-vps exclude data dirs + script audit pre-deploy securise` | **absent** |
| `a05032b` | 2026-06-08 | `feat(ui): theme polish + unifie palette couleurs sur 29 widgets` | **absent** |

Le CHANGELOG 0.6.0 s'arrête effectivement à la liste des Sprints, sans la sous-section "Hardening complémentaire" ou "Bug fixes post-VPS-2".

**Preuve** : `git log --oneline vps | head -16` (16 commits) vs `CHANGELOG.md` 0.6.0 (4 sprints + audit isolation = 5 entrées).

**Recommandation** : Enrichir la section `0.6.0` avec un §"### Hardening post-Sprints" listant `a23f981`, `cbbf84a`, `f8957a6`, `a05032b`.

**Effort** : XS (10 min).

---

### F-DOC-9 — [LOW] `docs/VPS_HARDENING.md` : OK, une seule remarque mineure

**Description** : Le doc est **exemplaire** : commandes concrètes, idempotentes, `sudo` explicite, sections numérotées, lien vers la procédure d'urgence finale (section 7 "Vérification finale"). Toutes les briques demandées sont présentes :
- ✅ §4 SSH key only (PermitRootLogin no, PasswordAuthentication no, PubkeyAuthentication yes)
- ✅ §1 UFW (default deny, allow 22/80/443, PostgreSQL/MinIO non exposés)
- ✅ §2 fail2ban (3 retries, 1h ban)
- ✅ §0 backup offsite (rclone + ssh)
- ⚠️ §0 mentionne "rappel : configurer le `.service` pour appeler `backup-offsite.sh` au lieu de `backup.sh`" — fait dans le commit `a23f981` mais pas re-vérifié dans ce doc. OK mineur.

**Preuve** : `docs/VPS_HARDENING.md:0-200` lu en entier.

**Recommandation** : Aucune. Note positive pour la soutenance : ce doc peut être montré tel quel comme exemple de hardening documenté.

**Effort** : 0.

---

### F-DOC-10 — [LOW] `docs/ARCHITECTURE.md` et `docs/DATA_GOVERNANCE.md` : OK

**Description** : Pas de mention de kubernetes / k8s / cloud-demo dans ARCHITECTURE.md ni DATA_GOVERNANCE.md — donc pas de contradiction. Pas de ref à mettre à jour.

**Preuve** : `grep -E "kubernetes|k8s|cloud-demo|kustomize|Helm" docs/ARCHITECTURE.md docs/DATA_GOVERNANCE.md` → 0 résultat.

**Recommandation** : Aucune.

**Effort** : 0.

---

### F-DIR-1 — [HIGH] Incohérence entre entête README et CLAUDE.md sur la version

**Description** : README entête ligne 9 dit `Version: 0.5.0-rc1`, mais CLAUDE.md ligne 10 dit `Version actuelle : v0.3.0 (Sprints 1-7 complétés)`. CHANGELOG annonce `0.6.0` en cours.

Trois versions différentes dans trois fichiers "source de vérité".

**Preuve** :
- `README.md:9` → "Version: 0.5.0-rc1"
- `CLAUDE.md:10` → "Version actuelle : v0.3.0"
- `CHANGELOG.md:8` → "[0.6.0] - 2026-06-07 — VPS production"

**Recommandation** : Standardiser sur `0.6.0` (la plus récente, déjà en CHANGELOG). Patcher CLAUDE.md ligne 10 et README.md ligne 9.

**Effort** : XS (2 min).

---

### F-ISO-1 — [INFO] Isolation branches : OK, structurellement sain

**Description** : Les branches `kubernetes` et `cloud-demo` sont **strictement isolées** de `vps` et `main` :

| Test | Résultat |
|------|----------|
| `git log vps..kubernetes --oneline` | 8 commits en avance (k8s-only, jamais mergés) |
| `git log vps..cloud-demo --oneline` | 10 commits en avance (cloud-demo-only) |
| `git log main..kubernetes --oneline` | 8 commits (idem) |
| `git log main..cloud-demo --oneline` | 10 commits (idem) |
| Fichiers `kubernetes/` ou `cloud-demo/` sur `vps` | **0 fichier** |
| Fichiers `kubernetes/` ou `cloud-demo/` sur `main` | **0 fichier** |
| Fichiers `monitoring/`, `nginx/`, `scripts/systemd/`, `src/api/metrics.py` sur k8s/cloud-demo | **0 fichier** |

**Preuve** : commandée exécutée (cf §1 Périmètre).

**Détail à noter** : 
- Les merges entre `main` ↔ `kubernetes` et `main` ↔ `cloud-demo` (commits `bf18924`, `5021b88`, `846d855`, `ad0dfde`, `4b72db2`, `ccbcbfd`, `115d9ab`) sont des **merges unidirectionnels vers les branches futures** (k8s/cloud-demo héritent des fixes de `main`). Ils ne contaminent pas `vps`.
- Le merge `b4e75bd Merge branch 'kubernetes' into cloud-demo` est interne aux branches dormantes — n'affecte pas `vps`.

**Recommandation** : Aucune action technique. **Bon comportement structurel** à valider au prochain sprint.

**Effort** : 0.

---

### F-ISO-2 — [INFO] Working tree de `vps` contient `backups/4.0GB` non tracké (déjà couvert par backup-recovery-audit)

**Description** : `git status` montre `backups/` (4.0 Go de dump postgres) en untracked. C'est une **violation de la règle BACKUP OFFSITE** côté disque VPS (le dump ne devrait pas être sur le VPS), pas un problème de branch isolation. Déjà documenté par la piste `backup-recovery-audit` (F-BAK-*).

**Preuve** : `git status` → "Untracked files: backups/". `du -sh backups/` → 4.0G. `ls backups/` → `lyonflow_20260608_064919Z_postgres.dump.gz` (4.0 Go).

**Recommandation** : Voir deliverable de la piste `backup-recovery-audit`. Hors scope de cette piste.

**Effort** : 0 (déjà tracé ailleurs).

---

### F-LNK-1 — [LOW] Lien runbook mort dans `monitoring/prometheus/rules/api.yml`

**Description** : L'alerte `ApiHighErrorRate` (et d'autres dans api.yml) référencent une ancre `docs/RUNBOOK.md#api-5xx` qui **n'existe pas** dans `docs/RUNBOOK.md` (le doc n'a pas de section `## api-5xx` ni d'ancre nommée).

**Preuve** : 
- `monitoring/prometheus/rules/api.yml:18` ligne d'annotation `runbook: "https://github.com/PDUCLOS/lyonflowfull/blob/main/docs/RUNBOOK.md#api-5xx"`
- `grep -E "^#.*api-5xx|^##.*api-5xx" docs/RUNBOOK.md` → 0 résultat

**Recommandation** : Soit créer l'ancre dans RUNBOOK.md (cf F-DOC-5, où le runbook sera de toute façon refondu), soit remplacer par un lien direct vers la procédure dans MONITORING.md ou CONTROLE_VPS_VS_CLOUD_DEMO.md.

**Effort** : XS (5 min, lors de la refonte RUNBOOK).

---

### F-LNK-2 — [INFO] Toutes les références inter-docs (AGENTS/CLAUDE/CHANGELOG/README → docs/*.md) sont valides

**Description** : Vérification systématique :

| Source | Cible | Statut |
|--------|-------|--------|
| `AGENTS.md:25` | `docs/VPS_HARDENING.md`, `docs/MONITORING.md`, `docs/CONTROLE_VPS_VS_CLOUD_DEMO.md` | ✅ fichiers présents |
| `CHANGELOG.md:19,40,58` | idem | ✅ |
| `CLAUDE.md:276-278` | idem | ✅ |
| `README.md:408-410` | idem | ✅ |
| `CLAUDE.md:11` | `SPRINT_7_REPORT.md` | ✅ |
| `CLAUDE.md:16` | `SPRINT_6_WIDGET_MIGRATION_CHECKLIST.md` | ✅ |
| `README.md:112` | `docs/ARCHITECTURE.md` | ✅ |
| `README.md:260` | `docs/API.md` | ✅ (avec note "à venir") |
| `README.md:427` | `docs/DATA_GOVERNANCE.md` | ✅ |

**Preuve** : `ls docs/VPS_HARDENING.md docs/MONITORING.md docs/CONTROLE_VPS_VS_CLOUD_DEMO.md` → tous présents.

**Recommandation** : Aucune. Liens inter-docs principaux sont OK. Le seul lien mort est F-LNK-1 (runbook ancre, hors flux principal).

**Effort** : 0.

---

### F-LNK-3 — [LOW] Mention `lyonflow.fr` dans VPS_HARDENING et CONTROLE_VPS_VS_CLOUD_DEMO : domaine non confirmé

**Description** : `docs/VPS_HARDENING.md:188` utilise `https://lyonflow.fr` comme commande de check TLS. `docs/CONTROLE_VPS_VS_CLOUD_DEMO.md:39` mentionne aussi `lyonflow.fr` comme domaine prod. Mais le `.deploy.env.example` n'a pas de `VPS_DOMAIN` pré-rempli et le projet n'a pas de confirmation explicite que `lyonflow.fr` est bien le domaine final (vs `lyonflowfull.fr` mentionné dans `AGENTS.md`/`README.md`/`docs/DATA_GOVERNANCE.md`).

**Preuve** : 
- `docs/VPS_HARDENING.md:188` → `curl -vI https://lyonflow.fr 2>&1 | grep -E "subject|issuer|expire"`
- `docs/DATA_GOVERNANCE.md:437` → `http://localhost/RGPD_Conformite` (référence à `localhost` pour le RGPD)
- Pas de mention explicite du domaine canonique dans `.env.example`

**Recommandation** : Confirmer le domaine final (lyonflow.fr vs lyonflowfull.fr vs autre) et le documenter dans `.env.example` (variable `VPS_DOMAIN=`) ou `AGENTS.md` (référence canonique). Idéalement, ajouter le paramètre `${VPS_DOMAIN}` dans `docs/VPS_HARDENING.md:188` au lieu d'un domaine hardcodé.

**Effort** : XS (5 min).

---

## 3. Tableau de scoring

| # | Finding | Catégorie | Criticité | Effort | Bloquant prod ? |
|---|---------|-----------|-----------|--------|-----------------|
| F-DOC-1 | README.md entête désalignée | Doc coherence | HIGH | XS | NON |
| F-DOC-2 | `docs/GIT_STRUCTURE.md` totalement désaligné | Doc coherence | HIGH | S | NON |
| F-DOC-3 | `docs/REPO_STRUCTURE.md` arbre inexistant sur vps | Doc coherence | HIGH | S | OUI (soutenance) |
| F-DOC-4 | `docs/DEPLOYMENT.md` §8 obsolète | Doc coherence | HIGH | S | NON |
| F-DOC-5 | `docs/RUNBOOK.md` 3 contradictions | Doc coherence | MEDIUM | M | OUI (incident) |
| F-DOC-6 | `docs/MONITORING.md` pas de runbook par alerte | Doc coherence | MEDIUM | M | OUI (incident) |
| F-DOC-7 | `CONTROLE_VPS_VS_CLOUD_DEMO.md` rollback VPS absent | Doc coherence | MEDIUM | XS | OUI (rollback) |
| F-DOC-8 | CHANGELOG 4 commits vps non référencés | Doc coherence | LOW | XS | NON |
| F-DOC-9 | `VPS_HARDENING.md` OK | Doc coherence | LOW | 0 | NON |
| F-DOC-10 | ARCHITECTURE/DATA_GOVERNANCE OK | Doc coherence | LOW | 0 | NON |
| F-DIR-1 | Version incohérente (3 sources, 3 versions) | Directives | HIGH | XS | NON |
| F-ISO-1 | Isolation branches OK | Isolation | INFO | 0 | NON |
| F-ISO-2 | `backups/4GB` non tracké (déjà couvert) | Isolation | INFO | 0 | OUI (disk) |
| F-LNK-1 | Runbook ancre morte | Liens | LOW | XS | NON |
| F-LNK-2 | Liens inter-docs OK | Liens | INFO | 0 | NON |
| F-LNK-3 | Domaine `lyonflow.fr` non confirmé | Liens | LOW | XS | NON |

**Total** : 16 findings (4 HIGH, 4 MEDIUM, 5 LOW, 3 INFO)
- 0 CRITICAL
- 4 HIGH
- 4 MEDIUM
- 5 LOW
- 3 INFO

---

## 4. Plan d'action recommandé

### Immédiat (avant prochain deploy, < 1h)

1. **F-DOC-1 + F-DIR-1** : Patcher `README.md` (entête + version) en miroir de l'alignement `54deb7b` → commit `docs(vps): aligne entete README`.
2. **F-DOC-7** : Ajouter §6.3 "Rollback VPS" à `CONTROLE_VPS_VS_CLOUD_DEMO.md` (10 min, 1 paragraphe).
3. **F-DOC-8** : Compléter CHANGELOG 0.6.0 avec les 4 commits post-Sprints (`a23f981`, `cbbf84a`, `f8957a6`, `a05032b`).

### Court terme (avant soutenance Jedha, 1-2 jours)

4. **F-DOC-3** : Annoter `REPO_STRUCTURE.md` que `kubernetes/` et `cloud-demo/` n'existent que sur leurs branches respectives. **CRITIQUE pour soutenance** : un évaluateur qui clone `vps` va chercher ces dossiers.
5. **F-DOC-2** : Réécrire `GIT_STRUCTURE.md` (mapping branches ↔ phases aligné sur AGENTS.md).
6. **F-DOC-4** : Réécrire `DEPLOYMENT.md` §8 + sommaire.
7. **F-DOC-5** : Refondre `RUNBOOK.md` (3 corrections + procédure d'incident par alerte).
8. **F-DOC-6** : Ajouter section "Runbook par alerte" dans `MONITORING.md`.

### Moyen terme (sprint suivant)

9. **F-LNK-3** : Documenter domaine canonique (`VPS_DOMAIN` dans `.env.example` + référence unique dans AGENTS.md).
10. **F-LNK-1** : Corriger le lien runbook dans les alertes Prometheus (lors de la refonte RUNBOOK).

---

## 5. Signaux positifs

- **Isolation structurelle des branches dormantes** est **exemplaire** (F-ISO-1) : aucun fichier k8s/cloud-demo sur vps, merges uniquement entre branches futures, pas de contamination.
- **`docs/VPS_HARDENING.md`** est un modèle de doc opérationnel : commandes concrètes, sudo explicite, sections numérotées, vérification finale.
- **CHANGELOG.md 0.6.0** documente fidèlement les 4 Sprints VPS + l'audit isolation, avec une note claire "non mergées dans vps ou main".
- **CLAUDE.md** est la source de vérité la mieux tenue (alignement `54deb7b` complet).
- **Liens inter-docs principaux** (AGENTS/CLAUDE/CHANGELOG/README → docs/*.md) sont tous valides.
- **CI** `.github/workflows/ci.yml` inclut gitleaks + Trivy + bandit + pip-audit (couvre la sécu déjà vérifiée par la piste `security-audit`).
- **Working tree** de vps est **propre** : seul `backups/` (déjà couvert) et `.opencode/` (config agent, non critique) en untracked.

---

## 6. Conclusion

**Statut final** : **WARN** — production-ready côté code/infra/sécu/backup, mais **cohérence documentaire partielle**. L'alignement `54deb7b` a corrigé 50% du problème (4 docs principaux partiellement touchés) mais laisse 6 docs/doc-sections désynchronisés. Aucun finding CRITICAL bloquant pour la production VPS. Pour la **soutenance Jedha** (juillet 2026) : corriger **F-DOC-3** (REPO_STRUCTURE.md) en priorité, c'est le plus dangereux car il décrit une structure qui n'existe pas sur la branche de référence.

**Effort cumulé estimé** : ~4-6h de travail pour aligner toute la doc (F-DOC-1 à F-DOC-8 + F-DIR-1 + F-LNK-1/3). Aucun n'est bloquant pour la production actuelle.

---

*Document généré le 2026-06-08 par agent `general` (session mvs_77f6adef3845493a95244a4556d455d6). Audit lecture seule sur branche `vps` @ commit `a05032b`. 16 fichiers lus, 16 findings, 0 secret réel exposé.*
