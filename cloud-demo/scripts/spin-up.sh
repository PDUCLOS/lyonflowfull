#!/usr/bin/env bash
# Demarre cluster ephemere demo Jedha : provision + bootstrap + deploy + seed.
# Duree : ~10-15 min. Cout : ~0,40 €/h (POP2 x2).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."

log() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

# 1. Terraform apply
log "[1/5] Provision cluster Kapsule (terraform)"
cd "$ROOT/terraform"
terraform init -upgrade
terraform apply -auto-approve

# 2. Kubeconfig
export KUBECONFIG="$ROOT/kubeconfig"
log "[2/5] Cluster pret. Nodes :"
kubectl get nodes

# 3. Bootstrap
log "[3/5] Bootstrap cluster (ingress + cert-manager + sealed-secrets)"
"$ROOT/../kubernetes/scripts/bootstrap-cluster.sh"

# 4. Sceller secrets + deploy
log "[4/5] Sealing secrets + deploy overlay jedha-demo"
ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ Pas de fichier $ENV_FILE — copier depuis kubernetes/.env.example et remplir"
  exit 1
fi
"$ROOT/../kubernetes/scripts/seal-secrets.sh" "$ENV_FILE" \
  > "$ROOT/overlays/jedha-demo/sealed-secret.yaml"

kustomize build "$ROOT/overlays/jedha-demo" | kubectl apply -f -

log "Attente du rollout (5 min max)"
kubectl -n lyonflow rollout status statefulset/postgres --timeout=5m
kubectl -n lyonflow rollout status deployment/fastapi   --timeout=5m
kubectl -n lyonflow rollout status deployment/streamlit --timeout=5m

# 5. Seed
log "[5/5] Seed demo data (7 jours)"
"$SCRIPT_DIR/seed-demo-data.sh"

LB_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo
echo "✅ Demo prete"
echo "   LB IP      : $LB_IP"
echo "   App URL    : https://lyonflow.demo.jedha.fr"
echo "   API URL    : https://api.lyonflow.demo.jedha.fr"
echo
echo "   ⚠️  Penser a tear-down apres demo :"
echo "      $SCRIPT_DIR/tear-down.sh"
