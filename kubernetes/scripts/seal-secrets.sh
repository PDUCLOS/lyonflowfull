#!/usr/bin/env bash
# Convertit un fichier .env en SealedSecret prêt à commit.
#
# Usage :
#   ./scripts/seal-secrets.sh path/to/.env > base/secrets/sealed-secret.yaml
#
# Pré-requis :
#   - kubeseal installé (https://github.com/bitnami-labs/sealed-secrets/releases)
#   - sealed-secrets controller déployé (cf bootstrap-cluster.sh)
#   - .sealed-secrets/pub-cert.pem présent (cf bootstrap-cluster.sh)

set -euo pipefail

ENV_FILE="${1:-.env}"
NAMESPACE="lyonflow"
SECRET_NAME="lyonflow-secrets"
PUB_CERT="$(dirname "$0")/../.sealed-secrets/pub-cert.pem"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ Fichier env introuvable : $ENV_FILE" >&2
  exit 1
fi
if [ ! -f "$PUB_CERT" ]; then
  echo "❌ Clé publique introuvable : $PUB_CERT" >&2
  echo "   Lancer d'abord ./scripts/bootstrap-cluster.sh" >&2
  exit 1
fi

# Construit un Secret kube classique en mémoire (jamais écrit sur disque)
TMP_SECRET=$(mktemp)
trap 'rm -f "$TMP_SECRET"' EXIT

kubectl create secret generic "$SECRET_NAME" \
  --namespace="$NAMESPACE" \
  --from-env-file="$ENV_FILE" \
  --dry-run=client -o yaml > "$TMP_SECRET"

# Sceller (chiffre avec la clé publique du cluster cible)
kubeseal \
  --cert "$PUB_CERT" \
  --format yaml \
  --scope namespace-wide \
  < "$TMP_SECRET"
