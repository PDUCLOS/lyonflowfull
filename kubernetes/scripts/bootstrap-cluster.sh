#!/usr/bin/env bash
# Bootstrap d'un cluster K8s pour LyonFlowFull (idempotent).
#
# Pré-requis :
#   - kubectl pointé sur le cluster cible
#   - helm 3.12+
#   - permissions cluster-admin (création CRDs, namespaces)
#
# Usage : ./scripts/bootstrap-cluster.sh

set -euo pipefail

NAMESPACE="lyonflow"
INGRESS_NS="ingress-nginx"
SEALED_NS="kube-system"
CERT_NS="cert-manager"

log() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

# 1. Namespaces
log "Création namespaces"
for ns in "$NAMESPACE" "$INGRESS_NS" "$CERT_NS"; do
  kubectl get ns "$ns" >/dev/null 2>&1 \
    || kubectl create namespace "$ns"
  kubectl label ns "$ns" name="$ns" --overwrite
done

# 2. Ingress NGINX controller
log "Installation ingress-nginx"
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace "$INGRESS_NS" \
  --set controller.kind=Deployment \
  --set controller.replicaCount=2 \
  --set controller.metrics.enabled=true \
  --set controller.service.externalTrafficPolicy=Local \
  --wait --timeout 5m

# 3. cert-manager (TLS Let's Encrypt)
log "Installation cert-manager"
helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace "$CERT_NS" \
  --set installCRDs=true \
  --wait --timeout 5m

# 4. ClusterIssuer Let's Encrypt
log "Création ClusterIssuer Let's Encrypt prod"
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: patrice.noel.duclos@gmail.com
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - http01:
          ingress:
            class: nginx
EOF

# 5. Sealed Secrets controller
log "Installation sealed-secrets"
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace "$SEALED_NS" \
  --set fullnameOverride=sealed-secrets-controller \
  --wait --timeout 5m

# 6. Récupération de la clé publique pour kubeseal
log "Export de la clé publique sealed-secrets"
mkdir -p "$(dirname "$0")/../.sealed-secrets"
kubeseal --controller-name=sealed-secrets-controller \
  --controller-namespace="$SEALED_NS" \
  --fetch-cert > "$(dirname "$0")/../.sealed-secrets/pub-cert.pem"

log "Bootstrap terminé. Prochaines étapes :"
echo "  1. Remplir un fichier .env (cf .env.example)"
echo "  2. ./scripts/seal-secrets.sh .env > base/secrets/sealed-secret.yaml"
echo "  3. kustomize build overlays/dev | kubectl apply -f -"
