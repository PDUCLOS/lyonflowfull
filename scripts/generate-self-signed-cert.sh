#!/usr/bin/env bash
# Génère un cert TLS self-signed pour nginx tant que Let's Encrypt n'est pas en place.
# Path = ce que ssl.conf attend (/etc/letsencrypt/live/lyonflow/).
# Pour passer en Let's Encrypt prod : remplacer ces fichiers par les vrais certs
# via certbot et retirer le bind mount certs dans docker-compose.yml.

set -euo pipefail

CERT_DIR="${CERT_DIR:-./nginx/certs}"
HOST="${1:-51.83.159.224}"
DAYS="${DAYS:-365}"

mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days "$DAYS" -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=${HOST}/O=LyonFlow-self-signed"

chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"

echo "OK: certs generated in $CERT_DIR (host=$HOST, days=$DAYS)"
ls -la "$CERT_DIR"
