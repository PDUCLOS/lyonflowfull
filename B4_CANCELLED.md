# B4 (setup-backup-offsite) — CANCELLED par décision user

**Date** : 2026-06-09 15:45 UTC
**Décision** : Patrice (owner projet) — « annule le B4 pour le moment »
**Statut** : **CANCELLED / DEFERRED** — sera re-spawné quand une destination de backup sera tranchée

## Contexte

Le task `setup-backup-offsite` (B4) visait à mettre en place un backup PostgreSQL
offsite quotidien avec systemd timer (règle projet CLAUDE.md : JAMAIS de backup
persistant sur le VPS, full 100%, obligation offsite via rclone/SSH/S3).

Le producer (session `mvs_8c42d8d4ac5b4e36b964c2d12e88e4c9`) a travaillé le
sujet mais Patrice a reporté la décision de destination (Google Drive OAuth vs
Service Account vs SSH vs S3) à plus tard.

## Pourquoi cancellation (vs partial work / B4-LITE)

Patrice a explicitement tranché : **B4 OFF, pas B4-LITE**. Plus clean pour le
plan, évite de polluer le VPS avec des units systemd non-activées qui
pourraient confusionner un futur ops.

Conséquences :
- Pas d'install des 3 units systemd sur le VPS
- Pas de enable --now du timer
- Pas de dry-run du script
- Pas de backup offsite réel
- Pas de test de restore en DB jetable
- Le verifier marquera FAIL ce cycle (attendu)

## État technique laissé en l'état (rollback complet du producer)

| Élément | État |
|---|---|
| `/opt/lyonflow/scripts/backup-offsite.sh` | ✅ présent, **version Sprint VPS-2 d'origine** (refactor producer reverté) |
| `/opt/lyonflow/scripts/backup.sh` | ✅ présent, inchangé |
| `/opt/lyonflow/scripts/restore.sh` | ✅ présent, inchangé |
| `/opt/lyonflow/scripts/test-restore.sh` | ❌ absent (supprimé lors du rollback) |
| `/opt/lyonflow/scripts/notify-backup-failure.sh` | ❌ absent (supprimé lors du rollback) |
| `/opt/lyonflow/scripts/notify-backup-success.sh` | ❌ absent (supprimé lors du rollback) |
| `/etc/systemd/system/lyonflow-backup.service` | ❌ absent (supprimé lors du rollback) |
| `/etc/systemd/system/lyonflow-backup.timer` | ❌ absent (supprimé lors du rollback) |
| `/etc/systemd/system/lyonflow-backup-notify@.service` | ❌ absent (supprimé lors du rollback) |
| `/opt/lyonflow/backups/` | ❌ absent (règle respectée : pas de backup local) |
| `systemctl list-timers \| grep lyonflow-backup` | vide (aucun timer armé) |
| `rclone` | v1.74.3 installé, remote `gdrive:` configuré (folder ID `1TO-4OwTlFr5s3v9-apu1MbA5jZ-yfNDR`), **token OAuth toujours vide** |
| Container `lyonflow-postgres` | healthy, intact |

## Pré-requis pour re-spawn B4 plus tard

Quand Patrice aura une destination, re-spawner un producer B4 avec un brief
propre incluant :
1. **Destination choisie** parmi :
   - A1 : Google Drive via OAuth (user fait le flow sur son Mac, copie token)
   - A2 : Google Drive via Service Account JSON key
   - B : SSH distant (user@host:/path + clé SSH)
   - C : S3 / Backblaze B2 / autre
2. **Credentials fournis** (token, JSON, ou chemin SSH)
3. **Autorisation explicite d'installer** (cp + daemon-reload + enable --now timer)
4. **Autorisation de faire 1 backup réel** + 1 test de restore en DB jetable

Le code Sprint VPS-2 (scripts/backup-offsite.sh, scripts/restore.sh,
scripts/systemd/lyonflow-backup.{service,timer}) est déjà en place et
fonctionnel. Le producer n'aura qu'à :
- Lancer les commandes de config destination (déjà documentées dans le brief
  original et le deliverable du producer précédent)
- cp + daemon-reload + enable --now
- 1 backup réel + 1 restore test
- Vérifier timer listé

## Leçons

1. **Stand-by vs verifier deadlock** : quand un user met un task en pause
   explicite, le verifier va FAIL le producer même si le producer respecte
   le stand-by. La résolution correcte est soit (a) cancellation explicite
   (ce qui s'est passé), soit (b) escalation user pour débloquer. Ne pas
   faire de partial work « B4-LITE » qui pollue l'état technique sans
   résoudre la condition PASS.

2. **Rollback scriptable** : le VPS a `git` en place, donc `git checkout
   HEAD -- <files>` restaure les fichiers originaux en 1 commande. Les
   nouveaux fichiers untracked sont supprimables avec `rm` direct (pas de
   risque de pollution git).

3. **Documentation cancellation** : laisser une trace écrite (ce fichier)
   permet au prochain producer B4 (futur re-spawn) de comprendre
   l'historique sans avoir à lire des centaines de lignes de communication
   inter-sessions.
