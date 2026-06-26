# LyonFlow — Guide de déploiement

## Vue d'ensemble

Ce guide couvre le déploiement de LyonFlow sur :
- **Local** (Docker Compose, dev)
- **VPS unique** (production, 1 serveur)
- **K8s** (à venir — Sprint 6+, dans un répertoire dédié)

## 1. Préparation locale

### Pré-requis

- **Docker 24+** et **Docker Compose v2+**
- **6 CPU, 12 GB RAM, 100 GB SSD** (minimum recommandé)
- **Python 3.12+** (dev local sans Docker uniquement)
- **psql client** (pour initialiser la DB)

### Configuration

```bash
# 1. Cloner
git clone https://github.com/PDUCLOS/lyonflowfull.git
cd lyonflow

# 2. Copier .env
cp .env.example .env

# 3. Générer les secrets forts
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)" >> .env.tmp
echo "MINIO_ROOT_PASSWORD=$(openssl rand -base64 24)" >> .env.tmp
echo "AIRFLOW_FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env.tmp
echo "AIRFLOW_SECRET_KEY=$(openssl rand -base64 32)" >> .env.tmp
echo "AIRFLOW_ADMIN_PASSWORD=$(openssl rand -base64 16)" >> .env.tmp
echo "LYONFLOW_API_KEY=$(openssl rand -base64 32)" >> .env.tmp
echo "PERSONA_PRO_TCL_PASSWORD=$(openssl rand -base64 16)" >> .env.tmp
echo "PERSONA_ELU_PASSWORD=$(openssl rand -base64 16)" >> .env.tmp
mv .env.tmp .env
chmod 600 .env

# 4. Éditer .env
# Vérifier que toutes les valeurs sont remplies
grep -E '^[A-Z_]+=' .env | wc -l  # doit être >= 12
```

### Démarrage

```bash
# Construire et démarrer tous les services
docker compose up -d --build

# Vérifier l'état
docker compose ps

# Logs
docker compose logs -f streamlit
docker compose logs -f airflow-webserver
docker compose logs -f api

# Initialisation DB (premier démarrage uniquement)
# Le init-db.sql est auto-exécuté par le container postgres
# Vérifier :
docker compose exec postgres psql -U lyonflow -d lyonflow -c "\dt bronze.*"
```

### Health check

```bash
# Nginx (public) — endpoint dédié /nginx-health (texte brut 200 ok)
curl http://localhost/nginx-health
# → "ok"

# API health
curl http://localhost/api/health
# → {"status":"ok","version":"0.1.0","db":true,"timestamp":"..."}

# Airflow (interne)
docker compose exec airflow-webserver airflow dags list
```

> **⚠️ Healthcheck Docker Nginx (depuis VPS-6)** : la commande interne est
> `wget --spider -q http://127.0.0.1/nginx-health` (IPv4 forcée). **Ne pas
> remettre `localhost`** : Alpine `wget` résout en IPv6 `::1` → Nginx n'écoute
> qu'en IPv4 → healthcheck échoue en boucle.

## 2. Déploiement sur VPS unique

### Préparation VPS

```bash
# 1. SSH
ssh deploy@vps-ip

# 2. Créer utilisateur deploy (si pas déjà fait)
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy
sudo mkdir -p /opt/lyonflow
sudo chown deploy:deploy /opt/lyonflow

# 3. Configurer SSH key
ssh-copy-id -i ~/.ssh/lyonflow_deploy.pub deploy@vps-ip
```

### Premier déploiement

```bash
# Sur le VPS
cd /opt/lyonflow
git clone https://github.com/PDUCLOS/lyonflowfull.git .
cp .env.example .env
# Éditer .env (voir section 1.3)
docker compose up -d --build
```

### Mise à jour

```bash
# Sur le VPS
cd /opt/lyonflow
git pull origin main
docker compose build
docker compose up -d
# Migrer la DB si nécessaire :
docker compose exec postgres psql -U lyonflow -d lyonflow -f /docker-entrypoint-initdb.d/migrations.sql
```

### Health check VPS

```bash
# Public
curl http://vps-ip/nginx-health
curl http://vps-ip/api/health

# Logs
docker compose logs --tail=100 -f streamlit
```

## 3. Backup et restauration

### Backup PostgreSQL

```bash
# Dump complet
docker compose exec postgres pg_dump -U lyonflow -d lyonflow -Fc \
  -f /tmp/lyonflow_$(date +%Y%m%d).dump

# Copier hors du container
docker cp lyonflow-postgres:/tmp/lyonflow_*.dump ./backups/
```

### Backup MinIO

```bash
# Mirror local
docker run --rm \
  -v /opt/lyonflow/backups/minio:/backup \
  -e MC_HOST_local=http://minio:9000 \
  --network lyonflow_default \
  minio/mc mirror local/lyonflow-bronze /backup/bronze
```

### Automatisation (cron)

```bash
# /etc/cron.d/lyonflow-backup
0 3 * * * deploy cd /opt/lyonflow && bash scripts/backup.sh
```

## 4. SSL / HTTPS (Let's Encrypt)

```bash
# Installer certbot
sudo apt install certbot

# Générer les certs
sudo certbot certonly --standalone -d lyonflow.example.com

# Monter dans Nginx
# Voir nginx/nginx-ssl.conf (à venir)

# Auto-renewal
echo "0 3 * * * certbot renew --quiet" | sudo crontab -
```

## 5. Monitoring

### Logs centralisés

```bash
# Tous les services
docker compose logs -f --tail=100

# Service spécifique
docker compose logs -f streamlit

# Avec timestamps
docker compose logs -f --timestamps streamlit
```

### Prometheus + Grafana (Sprint 6+)

À venir : `docker compose --profile monitoring up -d` ajoutera :
- `prometheus` (port 9090)
- `grafana` (port 3000)
- `node-exporter` (host metrics)

### Alertes (Sprint 6+)

Webhook Slack/Discord via `LYONFLOW_ALERT_WEBHOOK_URL` :
```yaml
LYONFLOW_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## 6. Troubleshooting

### Container ne démarre pas

```bash
docker compose logs postgres
# Vérifier que POSTGRES_PASSWORD est défini
docker compose exec postgres env | grep POSTGRES
```

### DB connection refused

```bash
# Vérifier que postgres est healthy
docker compose ps postgres
# → STATUS doit être "Up (healthy)"

# Tester depuis un autre container
docker compose exec api python -c "from src.db import test_connection; print(test_connection())"
```

### Streamlit crash au boot

```bash
docker compose logs streamlit | tail -50
# Souvent : persona_guard ou auth manquant
# Vérifier que src/persona/ est bien dans le context
```

### Port déjà utilisé

```bash
# Voir les ports occupés
sudo lsof -i :80
sudo lsof -i :8501
```

### Disk plein

```bash
# Voir Docker
docker system df

# Nettoyer images inutilisées
docker image prune -a

# Volumes orphelins
docker volume prune

# Attention : ne pas supprimer postgres_data/minio_data (data perte)
```

## 7. Sécurité en production

Avant de déployer en prod :

- [ ] Tous les secrets générés (mots de passe > 16 chars)
- [ ] `.env` en `chmod 600`
- [ ] `.env` dans .gitignore (✅ déjà)
- [ ] SSH key only (password auth désactivé)
- [ ] HTTPS activé (Let's Encrypt)
- [ ] Firewall ouvert uniquement 80/443/22
- [ ] Backup automatisé (cron)
- [ ] Logs centralisés (ELK, Loki, etc.)
- [ ] Alertes configurées
- [ ] Tests passent (`pytest tests/`)
- [ ] CI verte (GitHub Actions)
- [ ] Mises à jour OS automatiques (`unattended-upgrades`)

## 8. Migration vers K8s (à venir)

Quand le projet le justifiera :
- Répertoire dédié `k8s/` (à créer — pas dans ce repo pour l'instant)
- `kompose convert` depuis docker-compose.yml
- Manifests adaptés (Deployments, Services, Ingress, ConfigMaps, Secrets)
- Helm chart (à venir)

Pour l'instant : **Docker Compose est la bonne réponse** pour ce projet.
