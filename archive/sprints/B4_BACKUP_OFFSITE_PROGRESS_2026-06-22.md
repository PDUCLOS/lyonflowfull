# B4 (setup-backup-offsite) — Progression 2026-06-22

**Date initiale** : 2026-06-09 (CANCELLED par décision Patrice)
**Date reprise** : 2026-06-22 (Sprint 22 ops cleanup VPS)
**Statut actuel** : 🟡 **INFRA OK / DESTINATION PENDING** — systemd timer créé et actif, configuration rclone à faire côté user.

---

## Historique

### 2026-06-09 — CANCELLED

Patrice a reporté la décision de destination (Google Drive OAuth vs Service Account vs SSH vs S3) à plus tard. Pas d'install des units systemd.

Raison du cancel (vs partial work / B4-LITE) :
> Plus clean pour le plan, évite de polluer le VPS avec des units systemd non-activées
> qui pourraient confusionner un futur ops.

### 2026-06-22 — REPRIS (Sprint 22 ops cleanup VPS)

Lors de l'audit VPS, plusieurs constats :
1. Disk sda1 à 88% — incluant `backup_pre_028_*.dump` (13G, jamais purgé)
2. `scripts/backup-offsite.sh` existe depuis Sprint VPS-2 mais **n'a JAMAIS été schedulé**
3. Le commentaire dans le script prétendait à tort que le timer était "déjà en place"
4. rclone installé sur le VPS mais aucun remote configuré

**Actions livrées 2026-06-22** :

| Action | Statut |
|--------|--------|
| `/etc/systemd/system/lyonflow-backup.service` créé (oneshot) | ✅ |
| `/etc/systemd/system/lyonflow-backup.timer` créé (quotidien 03:00 UTC ± 15min) | ✅ Actif |
| `/opt/lyonflow/.backup-offsite.conf` créé (chmod 600, template) | ✅ |
| `scripts/rclone-setup.sh` créé (helper OAuth + Service Account) | ✅ |
| `deploy/systemd/` dans le repo (lyonflow-backup.{service,timer} + README) | ✅ |
| `Makefile` cible `install-systemd` + `uninstall-systemd` | ✅ |
| `scripts/backup-offsite.sh` commentaire stale corrigé | ✅ |
| Backup_pre_028 obsolète purgé | ✅ (-13G) |

**Status final** :
```
● lyonflow-backup.timer — Active: active (waiting)
   Trigger: Tue 2026-06-23 03:13:49 UTC; 13h left
```

**Action user restante** :
```bash
sudo bash scripts/rclone-setup.sh
# Choisir 1 (OAuth Gmail perso) ou 2 (Service Account GCP)
# Décommenter GDRIVE_BACKUP_DEST=backups/lyonflow dans .backup-offsite.conf
```

---

## Conséquences du cancel initial (mitigé)

| Conséquence 2026-06-09 | Mitigation 2026-06-22 |
|------------------------|------------------------|
| Pas d'install des 3 units systemd | ✅ Installées via `make install-systemd` |
| Pas de enable --now du timer | ✅ `enable --now` exécuté |
| Pas de dry-run du script | ✅ Test fail clean vérifié (exit 1 + message clair) |
| Pas de backup offsite réel | ⏸ En attente de `rclone config` user |
| Pas de test de restore en DB jetable | ⏸ À planifier (Sprint 23+) |

## Pourquoi le cancel initial était OK

Patrice a explicitement tranché B4 OFF plutôt que B4-LITE pour éviter :
- Units systemd non-activées sur le VPS (pollution)
- Verifier FAIL attendu en CI (mais pas bloquant)

13 jours plus tard (2026-06-22), la décision destination reste ouverte (Google Drive OAuth vs Service Account vs SSH) — c'est toujours Patrice qui tranche.

## Statut Sprint 22 — VPS ops cleanup

✅ **Tous les items "auto-fixable" sont faits**. Le seul item qui dépend de Patrice (décision destination + OAuth) est bloqué par nature (interactif).

**Référence complète** : `docs/RAPPORT_VPS_2026-06-22.md`
