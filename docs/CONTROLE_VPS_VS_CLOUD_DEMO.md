# =============================================================================
# docs/CONTROLE_VPS_VS_CLOUD_DEMO.md — Audit des 3 déploiements LyonFlow
# =============================================================================
# Date : 2026-06-07
# Auteur : PDUCLOS
# Objectif : valider l'isolation et la cohérence entre 3 contextes de deploy
# =============================================================================

# Contrôle vps ↔ cloud-demo ↔ kubernetes

Ce document compare les 3 contextes de déploiement de LyonFlow pour
valider qu'ils peuvent coexister sans collision et identifier les risques.

## 1. Matrice de synthèse

| Dimension | VPS (production) | Kubernetes (base) | Cloud-demo (Jedha) |
|-----------|------------------|-------------------|---------------------|
| **Stockage DB** | `/opt/lyonflow/postgres_data` (volume Docker) | PVC `postgres-data-lyonflow-postgres-0` (StorageClass par défaut) | PVC 5Gi (réduit via patch `postgres-demo.yaml`) |
| **Identifiants DB** | `.env` (chmod 600, fichier local) | SealedSecret `lyonflow-secrets` (cluster-wide) | SealedSecret généré par `seal-secrets.sh` (éphémère par deploy) |
| **Network isolation** | Docker network `lyonflow_default` | Namespace `lyonflow` + NetworkPolicy | Cluster Kapsule Scaleway **séparé** (cluster éphémère neuf) |
| **Schéma DB** | `deploy/init-db.sql` (lecture unique au premier démarrage) | `deploy/init-db.sql` via ConfigMap `postgres-init` (monté comme init container) | idem (extends kubernetes/base via Kustomize) |
| **Backup DB** | `scripts/backup.sh` quotidien (systemd timer 03:00) | `kubernetes/base/postgres/backup-cronjob.yaml` (si configuré) | **Aucun** (DB détruite avec le cluster) |
| **Restore DB** | `scripts/restore.sh` | `pg_restore` manuel + `kubectl cp` (cf `kubernetes/scripts/migrate-vps.sh`) | N/A (éphémère) |
| **Monitoring** | `docker-compose.monitoring.yml` (Prometheus+Grafana+Alertmanager) | `kubernetes/base/monitoring/` (ServiceMonitors + PrometheusRule) | **Aucun** (1 replica, 2-4h de vie) |
| **ML training (GNN)** | CPU only, CronJob daily désactivé | `kubernetes/base/gnn-trainer/` (CPU/GPU, désactivé cloud-demo) | **Désactivé** (`$patch: delete` sur le CronJob) |
| **Compute** | VPS 6 CPU / 12 GB RAM | Cluster scalable (HPA) | 1 node POP2-4C-16G (suffisant pour 1 replica) |
| **Coût** | Fixe (VPS loué) | Variable (provider K8s, à choisir) | ~0,40 €/h × 4h = **~1,60 € par démo** |
| **Cycle de vie** | Continu (production) | Continu (futur production) | 2-4h par démo, détruit après |

## 2. Isolation entre contextes

### 2.1 VPS vs Cloud-demo : isolation PHYSIQUE

**État** : ✅ **isolation totale**

- **Réseau** : cloud-demo crée un **nouveau cluster Kapsule Scaleway** à chaque
  spin-up (`terraform apply`). Aucun peering réseau avec le VPS.
- **DNS** : cloud-demo utilise `*.lyonflow.demo.jedha.fr` (sous-domaine dédié
  de démo), pas le domaine prod `lyonflow.fr` du VPS.
- **Identifiants** : cloud-demo redéfinit ses propres secrets (POSTGRES_PASSWORD
  généré par `seal-secrets.sh` à partir d'un `.env` local). Aucun secret partagé
  avec le VPS.
- **DB** : cloud-demo crée une **nouvelle instance PostgreSQL** dans son cluster
  Kapsule. Aucun accès au PostgreSQL du VPS (`51.83.159.224:5432`).
- **Stockage** : PVC Scaleway Block Storage, isolé du volume `postgres_data` du VPS.

**Risque de contamination** : ✅ **nul** — un demo cloud-demo ne peut pas
toucher au VPS. La base PostgreSQL du VPS est protégée.

### 2.2 VPS vs Kubernetes (base) : isolation LOGIQUE

**État** : ⚠️ **à valider** avant déploiement K8s prod

- **Réseau** : K8s utilise un namespace `lyonflow` isolé. NetworkPolicy à
  configurer (déjà prévue dans `kubernetes/base/`).
- **Identifiants** : K8s utilise SealedSecret (chiffré au repo, déchiffré
  dans le cluster). Mais les secrets initiaux doivent correspondre à
  ceux utilisés par le VPS pour la migration des données.
- **DB** : K8s StatefulSet `postgres` (1 replica pour dev, plus en prod avec
  replicas + read-write). Le service DNS `postgres.lyonflow.svc.cluster.local`
  est interne au cluster.
- **Migration** : `kubernetes/scripts/migrate-vps.sh` (VPS → K8s) avec
  pg_dump + kubectl cp + pg_restore. Dry-run par défaut (`CONFIRM=yes`).

**Action requise avant production** :
1. Vérifier que les SealedSecrets de prod sont différents de ceux de démo.
2. Tester `migrate-vps.sh` sur un cluster de staging d'abord.
3. Documenter la procédure de switch DNS (lyonflow.fr → cluster K8s).

## 3. Garde-fous PostgreSQL (base prod)

### 3.1 VPS — base de prod (NE PAS TOUCHER)

```bash
# Connexion (chiffrement TLS recommandé, pas activé actuellement)
psql -h 51.83.159.224 -p 5432 -U lyonflow -d lyonflow

# Volume local (NE PAS supprimer /opt/lyonflow/postgres_data)
# 32 tables (bronze/silver/gold), 103 indexes, autovacuum
# Backup quotidien via systemd timer (Sprint VPS-2)
# Rétention 7j local + push offsite via backup-offsite
```

**État de la base au 2026-06-07** (estimé) :
- 32 tables (bronze.silver.gold)
- 103 indexes (BRIN sur time-series)
- Données depuis Phase 1 (Sprints 1-7)
- Backup vérifié OK lors du dernier deploy (Sprint VPS-2)

### 3.2 Cloud-demo — base jetable

- Nouvelle DB à chaque `spin-up.sh` (terraform + kustomize + sealed-secrets)
- Seed via `seed-demo-data.sh` (7 jours de données mock)
- **Détruit à chaque `tear-down.sh`** (`terraform destroy`)
- Aucune persistance entre 2 démos

### 3.3 Kubernetes base — DB à configurer pour prod

- StatefulSet `postgres` avec PVC
- Backup via CronJob (`backup-cronjob.yaml` dans `kubernetes/base/postgres/`)
- Pas encore déployé en prod (Phase 2 du plan)

## 4. Risques identifiés et mitigations

| Risque | Sévérité | Mitigation |
|--------|----------|------------|
| **DB VPS saturée** (disk 100% mentionné dans audit) | 🔴 Critique | Backup offsite + monitoring disk > 85% (alert dans `rules/system.yml`) |
| **Perte du `.env` VPS** (chmod 600) | 🟠 Majeure | Backup `.env` chiffré offsite + `.deploy.env` séparé |
| **cloud-demo touche le DNS prod** | 🟡 Mineure | Hosts dédiés `*.demo.jedha.fr` (patch ingress), pas de wildcard `*.lyonflow.fr` |
| **SealedSecret cloud-demo leak** dans git | 🟡 Mineure | `cloud-demo/.gitignore` exclut `.env` et `kubeconfig` |
| **ML inference drift** (modèle périmé) | 🟡 Mineure | MLflow tracking + retrain XGBoost hourly :25 (déjà en place) |
| **Cert TLS non renouvelé** | 🟠 Majeure | Alerte `TlsCertExpiringSoon` < 14j + certbot.timer systemd |
| **DB down cascade** (autres alertes DB) | 🟢 Info | Inhibitions dans alertmanager.yml |

## 5. Checklist avant démo Jedha

Avant chaque démo (avant `cloud-demo/scripts/spin-up.sh`) :

- [ ] `.env` cloud-demo rempli avec secrets Jedha-safe (pas les secrets VPS)
- [ ] DNS `*.demo.jedha.fr` pointe vers le futur cluster (sinon demo inaccessible)
- [ ] Offsite backup VPS à jour (au cas où démo tourne pendant l'event)
- [ ] `kubectl` et `terraform` installés sur la machine qui lance le spin-up
- [ ] Crédits Scaleway (compte Jedha) avec assez de fonds (~5 € pour 5 démos)
- [ ] Patrice dispo pour le `tear-down.sh` immédiat après la démo (pas de surprise de facturation)

## 6. Procédure d'urgence

### Si la démo cloud-demo échoue pendant la soutenance

```bash
# 1. Vérifier le statut
kubectl -n lyonflow get pods
kubectl -n lyonflow logs -f deployment/streamlit

# 2. Rollback (revient au dernier état fonctionnel)
kubectl -n lyonflow rollout undo deployment/streamlit
kubectl -n lyonflow rollout undo deployment/fastapi

# 3. Si vraiment cassé, fallback : montrer des screenshots + démo locale
streamlit run dashboard/Accueil.py  # sur le laptop
```

### Si le VPS est inaccessible pendant une démo

```bash
# 1. SSH via IP de secours (si configurée) ou console provider Scaleway
# 2. Vérifier l'état
systemctl status lyonflow
docker compose ps

# 3. Restart si besoin
sudo systemctl restart lyonflow
# ou manuellement :
cd /opt/lyonflow && docker compose up -d --build

# 4. Si DB corrompue, restore depuis backup
cd /opt/lyonflow && ./scripts/restore.sh backups/lyonflow_LATEST
```

## 7. Recommandations

### Court terme (post-démo Jedha)

1. **Tag les commits prod sur `vps`** avant chaque deploy (`make tag-vps`)
2. **Tester `migrate-vps.sh`** sur un cluster K8s de staging pour valider la
   procédure de migration
3. **Externaliser le monitoring** : actuellement sur le VPS, à terme sur
   un cluster monitoring séparé (Prometheus + Thanos pour la rétention long terme)

### Moyen terme (Phase 2 — Kubernetes prod)

1. **Activer la réplication PostgreSQL** (1 primary + 2 replicas) pour la haute dispo
2. **Migrer la base VPS** vers le cluster K8s via `migrate-vps.sh` (test staging d'abord)
3. **Renommer `vps` → `legacy-vps`** une fois la migration K8s validée (archive)

### Long terme (Phase 3+)

1. **Cloud SQL managé** (Scaleway DB ou RDS) au lieu de PostgreSQL self-hosted
2. **GitOps** avec ArgoCD pour deploy automatique sur push branche `vps` ou `main`
3. **Multi-régions** pour la résilience (DRP)

## 8. Conclusion

| Contexte | Statut | Action |
|----------|--------|--------|
| VPS (prod actuelle) | ✅ **intact, isolé, backup quotidien** | Aucune action immédiate. Tag avant chaque deploy. |
| Kubernetes (base) | ⚠️ **prêt pour staging** | Tester `migrate-vps.sh` + NetworkPolicy avant prod. |
| Cloud-demo (Jedha) | ✅ **isolé du VPS par construction** | OK pour démo 2-4h. Tear-down obligatoire après. |

**Aucun risque de contamination entre vps et cloud-demo.** Le VPS peut
continuer à tourner pendant les démos Jedha sans impact.

Le seul point d'attention est la **migration VPS → K8s** (Phase 2) qui
nécessite un test sur staging avant switch DNS.

---

*Document généré le 2026-06-07 par PDUCLOS (suite à audit VPS complet +
Sprints VPS-1 à VPS-4). Sources : docker-compose.yml, scripts/backup.sh,
.env.example, kubernetes/base/, cloud-demo/overlays/jedha-demo/.*
