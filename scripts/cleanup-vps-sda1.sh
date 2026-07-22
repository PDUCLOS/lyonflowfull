#!/bin/bash
# LyonFlow VPS — Nettoyage disque sda1
# Actions : vire volumes orphelins + docker system prune
# À lancer UNE SEULE FOIS depuis le VPS en SSH

set -e
cd /opt/lyonflow

echo "=== 1. Stop MinIO ==="
docker compose stop minio

echo ""
echo "=== 2. Migrer MinIO (déjà fait : données sur /mnt/postgres-data/minio) ==="
echo "    (le docker-compose.yml pointe déjà vers /mnt/postgres-data/minio)"

echo ""
echo "=== 3. Suppression volumes orphelins ==="
echo "    lyonflow_minio_data       (Docker volume, plus utilisé)"
echo "    lyonflow-pgdata           (21GB ORPHELIN, postgres = bind mount sdb)"
echo "    lyonflow_airflow_data     (0B orphelin)"
echo "    2 hash volumes            (0B orphelins)"

docker volume rm lyonflow_minio_data
docker volume rm lyonflow-pgdata
docker volume rm lyonflow_airflow_data
docker volume rm 57e4c39e836b3890c35407aee47292b2a13da2ce3c718a0fe50a0b0bce7c2bd5
docker volume rm b6a0651846ac4f990fa48715605bbb3c5c7b5f75544d989302d3ba112eb1a109

echo ""
echo "=== 4. Relance MinIO avec bind mount sur sdb ==="
docker compose up -d minio
sleep 5
docker ps -a --filter "name=lyonflow-minio" --format "table {{.Names}}\t{{.Status}}"

echo ""
echo "=== 5. MinIO health check ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:9000/minio/health/live

echo ""
echo "=== 6. Buckets présents (on doit voir lyonflow-bronze et lyonflow-gold) ==="
docker exec lyonflow-minio ls /data

echo ""
echo "=== 7. Docker system prune (libère ~58 GB d'images inutilisées) ==="
echo "Les images lyonflow-airflow-* n'existent plus (rebuild en cours)"
echo "Les images lyonflow-api et lyonflow-streamlit seront supprimées"
echo "        Il faudra 'make build' pour les reconstruire"
docker system prune -af

echo ""
echo "=== 8. ESPACE DISQUE FINAL ==="
df -h / /mnt/postgres-data
echo ""
echo "=== 9. Docker system df FINAL ==="
docker system df
echo ""
echo "=== 10. Volumes restants ==="
docker volume ls

echo ""
echo "=== 11. Containers status ==="
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"

echo ""
echo "TERMINÉ. Tu devrais avoir ~70-80 GB de libre sur /"
