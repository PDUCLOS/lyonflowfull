#!/usr/bin/env bash
# Stoppe cluster ephemere demo Jedha : destroy total.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."

log() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

# Confirmation
if [ "${CONFIRM:-no}" != "yes" ]; then
  echo "⚠️  Tear-down complet (cluster + LB + storage + DNS records crees)"
  echo "    Relancer : CONFIRM=yes $0"
  exit 1
fi

# 1. Drop ingress + LB + ressources Kustomize (cleanup avant terraform)
export KUBECONFIG="$ROOT/kubeconfig"
log "[1/3] Cleanup ressources K8s"
kustomize build "$ROOT/overlays/jedha-demo" | kubectl delete -f - --ignore-not-found || true
helm -n monitoring uninstall kps --ignore-not-found || true
helm -n lyonflow uninstall airflow --ignore-not-found || true

# 2. Terraform destroy
log "[2/3] Destroy cluster Kapsule"
cd "$ROOT/terraform"
terraform destroy -auto-approve

# 3. Cleanup local
log "[3/3] Cleanup fichiers locaux"
rm -f "$ROOT/kubeconfig" \
      "$ROOT/overlays/jedha-demo/sealed-secret.yaml" \
      "$ROOT/.env"

echo "✅ Cluster supprime, facturation arretee"
