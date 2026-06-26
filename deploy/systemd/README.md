# deploy/systemd — Units systemd versionnés

Ce dossier contient les **units systemd versionnés** pour LyonFlow,
à installer sur le VPS via `make install-systemd` (cf. Makefile).

## État actuel (2026-06-22)

| Fichier | État VPS | Description |
|---------|----------|-------------|
| `lyonflow-backup.service` | ✅ Installé | One-shot : exécute `scripts/backup-offsite.sh` |
| `lyonflow-backup.timer` | ✅ Installé (actif) | Quotidien 03:00 UTC ± 15min random |

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

## Politique de backup (rappel CLAUDE.md)

**JAMAIS de backup persistant sur le VPS** :
- pg_dump streamé via pipe vers `gzip | gpg | rclone rcat` (ou ssh)
- Rien n'est écrit sur `/opt/lyonflow/backups/` par ce flux
- Rétention gérée par le service distant (Google Drive auto-versions, SSH via cron externe)

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
```

## Convention de nommage

- `lyonflow-*.service` / `lyonflow-*.timer` : préfixe commun
- Les fichiers `.service` vont en `WantedBy=multi-user.target`
- Les fichiers `.timer` vont en `WantedBy=timers.target`
- Toujours `SyslogIdentifier=lyonflow-*` pour grep facile dans journalctl
