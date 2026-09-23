# deploy/systemd — Units systemd versionnés

Ce dossier contient les **units systemd versionnés** pour LyonFlow,
à installer sur le VPS via `make install-systemd` (cf. Makefile).

## État actuel (2026-09-23, Sprint 26)

| Fichier | État VPS | Description |
|---------|----------|-------------|
| `lyonflow-backup.service` | Installé | One-shot : exécute `scripts/backup-offsite.sh`. `OnFailure=lyonflow-backup-failed.service` |
| `lyonflow-backup.timer` | Installé (actif depuis le 2026-09-23) | Quotidien 03:00 UTC ± 15min random, `Persistent=true` |
| `lyonflow-backup-failed.service` | Installé | Déclenché si le backup échoue : `scripts/backup-failed-alert.sh` → alerte Telegram (credentials `.watchdog.env`) |

> ⚠️ Historique : le timer a été trouvé **désactivé du 2026-07-22 au 2026-09-22**
> (config rclone invalide, 0 backup pendant 2 mois, aucune alerte). D'où l'unit
> `OnFailure` : un backup qui échoue doit se voir.
>
> ⚠️ `Persistent=true` : `systemctl enable --now` déclenche un run **immédiat** de
> rattrapage. Vérifier `rclone lsd gdrive:` avant d'activer le timer.

## Installation

```bash
# Sur le VPS (en ssh)
cd /opt/lyonflow
sudo make install-systemd
```

Cette commande :
1. Copie `lyonflow-backup.{service,timer}` → `/etc/systemd/system/`
2. Crée `/opt/lyonflow/.backup-offsite.conf` (chmod 600) si manquant
3. `systemctl daemon-reload`
4. `systemctl enable --now lyonflow-backup.timer`
5. Affiche status + prochaine exécution

## Configuration pré-requise

Avant que le backup fonctionne, **une destination offsite doit être configurée** :

| Méthode | Setup | Quand l'utiliser |
|---------|-------|------------------|
| Google Drive (OAuth) | `sudo bash scripts/rclone-setup.sh` puis choisir `1` | Compte Gmail perso |
| Google Drive (Service Account) | Créer un SA dans GCP, fournir le JSON | Automation, pas d'OAuth |
| SSH distant | Avoir un serveur backup, définir `OFFSITE_SSH=user@host:path` | Serveur dédié |

Sans destination, le service fail clean (exit 1 + message clair).

## Politique de backup (rappel AGENTS.md, Règle 12)

**JAMAIS de backup persistant sur le VPS** :
- preflight : la destination (`rclone mkdir`/`lsd` ou `ssh mkdir`) est testée **avant**
  de lancer `pg_dump` — sinon un `pg_dump` orphelin survit dans le container avec un
  lock partagé sur toutes les tables (incident 2026-09-22)
- pg_dump streamé via pipe vers `gzip | gpg | rclone rcat` (ou ssh), `application_name=lyonflow-backup`
- Rien n'est écrit sur `/opt/lyonflow/backups/` par ce flux
- **Purge automatique** (Sprint 26) après chaque upload, dans `/opt/lyonflow/.backup-offsite.conf` :

| Variable | Défaut | Rôle |
|----------|--------|------|
| `BACKUP_RETENTION_DAYS` | 14 | supprime les backups plus vieux |
| `BACKUP_KEEP_MIN` | 2 | garde toujours les N plus récents, quoi qu'il arrive |
| `BACKUP_MAX_TOTAL_GB` | (auto) | plafond cumulé ; VPS : `150` |
| `BACKUP_MAX_QUOTA_PCT` | 30 | si pas de plafond explicite : % du quota total de la destination (`rclone about` / `df` distant), fallback 10 Go |

Ordre de suppression : du plus vieux au plus récent, jamais sous `BACKUP_KEEP_MIN`.
Ordre de grandeur : DB 32 Go → dump gz **3,7 Go en 22 min** (2026-09-23).

### Restaurer

```bash
rclone cat 'gdrive:backups/lyonflow/<fichier>.dump.gz' | gunzip | pg_restore -U lyonflow -d lyonflow
```

## Troubleshooting

```bash
# Status timer
sudo systemctl status lyonflow-backup.timer

# Next run
sudo systemctl list-timers | grep lyonflow

# Run manuel immédiat
sudo systemctl start lyonflow-backup.service

# Logs
sudo journalctl -u lyonflow-backup.service -f

# Dernière erreur
sudo journalctl -u lyonflow-backup.service -n 50 --no-pager

# Preflight KO ("failed when making oauth client") = token rclone invalide/révoqué.
# Refaire l'OAuth : sur le Mac `rclone authorize "drive"`, coller la ligne {...}
# dans ~/rclone-token.json, puis :
#   cat ~/rclone-token.json | ssh ubuntu@VPS "sudo tee /opt/lyonflow/.rclone.token >/dev/null && \
#     sudo bash -c 'grep -v \"^token = \" /opt/lyonflow/.rclone.conf > /tmp/rc && \
#     printf \"token = %s\n\" \"\$(tr -d \"\\n\" < /opt/lyonflow/.rclone.token)\" >> /tmp/rc && \
#     cat /tmp/rc > /opt/lyonflow/.rclone.conf && rm -f /opt/lyonflow/.rclone.token /tmp/rc'"
# Test : sudo bash -c 'source /opt/lyonflow/.backup-offsite.conf; rclone --config "$RCLONE_CONFIG" lsd gdrive:'

# Backup orphelin (pg_dump toujours actif après échec) :
docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='lyonflow-backup'"
```

## Convention de nommage

- `lyonflow-*.service` / `lyonflow-*.timer` : préfixe commun
- Les fichiers `.service` vont en `WantedBy=multi-user.target`
- Les fichiers `.timer` vont en `WantedBy=timers.target`
- Toujours `SyslogIdentifier=lyonflow-*` pour grep facile dans journalctl
