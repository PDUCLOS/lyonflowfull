# =============================================================================
# docs/VPS_HARDENING.md — Durcissement du VPS production
# =============================================================================
# Sprint VPS-1 : checklist sécurité post-déploiement.
# À exécuter UNE FOIS sur le VPS, pas à chaque deploy.
# =============================================================================

# Durcissement VPS LyonFlow

Ce document décrit les étapes de durcissement du VPS (51.83.159.224) après
le premier déploiement. À exécuter **une seule fois** (idempotent).

## 0. 🔴 Règle backup OFFSITE (AVANT TOUT)

**JAMAIS de backup persistant sur le VPS.** Le VPS est full à 100%
(96G/96G, 583M libre). Tout backup local est impossible ET interdit.

Le backup va **directement offsite** via `scripts/backup-offsite.sh` :
- Stream `pg_dump | gzip | gpg | rclone rcat gdrive:...` (rien sur disque VPS)
- OU ssh vers serveur backup privé (`OFFSITE_SSH=user@host:path`)

Setup one-time sur le VPS :
```bash
# 1. Installer rclone
curl https://rclone.org/install.sh | sudo bash

# 2. Setup Google Drive (OAuth interactif)
rclone config
# > New remote > name: gdrive > type: drive > scope: 1 (full) >
# > root_folder_id: 1TO-4OwTlFr5s3v9-apu1MbA5jZ-yfNDR
# > service_account: blank > auto-config: Y
# > Suivre lien Google > copier token > OK
#
# Le root_folder_id correspond au folder dedie 'backups/lyonflow' cree par Patrice.
# Avec ce root_folder_id, tous les chemins rclone sont relatifs a ce folder
# (gdrive:2026-06-07_xxx.dump.gz.gpg au lieu de gdrive:backups/lyonflow/...).

# 3. Tester
echo "hello" | rclone rcat gdrive:backups/lyonflow/test.txt
rclone ls gdrive:backups/lyonflow/  # doit afficher test.txt

# 4. Premier backup
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  'GDRIVE_BACKUP_DEST=backups/lyonflow bash /opt/lyonflow/scripts/backup-offsite.sh'
```

Cron déjà en place via `lyonflow-backup.timer` (Sprint VPS-2) —
configurer le `.service` pour appeler `backup-offsite.sh` au lieu de
`backup.sh` (voir `scripts/systemd/lyonflow-backup.service`).

**Cleanup immédiat** : supprimer les 476M de backups déjà sur le VPS
(avant la nouvelle règle) :
```bash
ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224 \
  'sudo rm -rf /opt/lyonflow/backups/* && echo OK'
```

## 1. Firewall UFW (Uncomplicated Firewall)

```bash
# Politique par défaut : tout bloquer en entrée, autoriser sortie
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH (limiter les tentatives via fail2ban plus tard)
sudo ufw allow 22/tcp comment 'SSH'

# HTTP/HTTPS (Nginx reverse proxy uniquement)
sudo ufw allow 80/tcp comment 'HTTP -> redirect HTTPS'
sudo ufw allow 443/tcp comment 'HTTPS'

# PostgreSQL : NE PAS exposer publiquement
# (déjà bindé sur 127.0.0.1 dans docker-compose.yml)

# MinIO : NE PAS exposer publiquement
# (déjà bindé sur 127.0.0.1 dans docker-compose.yml)

# Activer UFW
sudo ufw enable
sudo ufw status verbose
```

## 2. fail2ban (anti brute-force SSH)

```bash
sudo apt install -y fail2ban

# Configurer pour SSH : 3 tentatives max, ban 1h
sudo tee /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/auth.log
EOF

sudo systemctl restart fail2ban
sudo fail2ban-client status sshd
```

## 3. logrotate (rotation des logs Docker + Nginx)

```bash
# /etc/logrotate.d/docker-containers
sudo tee /etc/logrotate.d/docker-containers << 'EOF'
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    size 10M
    missingok
    notifempty
    copytruncate
}
EOF

# /etc/logrotate.d/nginx
sudo tee /etc/logrotate.d/nginx << 'EOF'
/var/log/nginx/*.log {
    rotate 14
    daily
    compress
    size 50M
    missingok
    notifempty
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 $(cat /var/run/nginx.pid)
    endscript
}
EOF

sudo systemctl restart logrotate
```

## 4. SSH hardening

Éditer `/etc/ssh/sshd_config` :
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers ubuntu
```

Puis :
```bash
sudo systemctl restart sshd
```

## 5. Mises à jour automatiques de sécurité

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## 6. Monitoring disque (le VPS a 100GB SSD, souvent à 100%)

```bash
# Alerte si disque > 85%
sudo tee /etc/cron.daily/disk-check << 'EOF'
#!/bin/bash
THRESHOLD=85
USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "[ALERT] Disk usage ${USAGE}% on $(hostname)" | mail -s "Disk Alert" root
fi
EOF
sudo chmod +x /etc/cron.daily/disk-check
```

## 7. Vérification finale

```bash
# Stack up ?
docker compose ps

# API health ?
curl -fsS http://localhost/api/health

# SSL valide ?
curl -vI https://lyonflow.fr 2>&1 | grep -E "subject|issuer|expire"

# DB backup tourne ?
systemctl list-timers | grep lyonflow-backup

# fail2ban actif ?
sudo fail2ban-client status
```

## Notes

- Ne JAMAIS désactiver UFW même en debug (sinon exposition publique DB/MinIO)
- Le backup cron est géré par `lyonflow-backup.timer` (cf Makefile `backup-vps`)
- Pour toute modif, refaire un `make deploy-vps` qui vérifie tout
