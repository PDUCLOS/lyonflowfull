#!/usr/bin/env bash
# Lance le load test k6 dans le cluster + observe HPA.
# Usage : ./run-loadtest.sh [overlay]   (default: dev)

set -euo pipefail
OVERLAY="${1:-dev}"
NS="lyonflow"

# Detection host depuis l'overlay
if [ "$OVERLAY" = "prod" ]; then
  HOST="https://api.lyonflow.fr"
else
  HOST="https://api-dev.lyonflow.fr"
fi

echo "▶ Lancement k6 contre $HOST (cluster: $OVERLAY)"

# ConfigMap script
kubectl -n "$NS" create configmap k6-script \
  --from-file=k6-api.js="$(dirname "$0")/k6-api.js" \
  --dry-run=client -o yaml | kubectl apply -f -

# Job k6
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: k6-loadtest
  namespace: $NS
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:0.50.0
          args: ["run", "/scripts/k6-api.js"]
          env:
            - name: K6_API_BASE
              value: "$HOST"
            - name: K6_API_KEY
              valueFrom:
                secretKeyRef:
                  name: lyonflow-secrets
                  key: LYONFLOW_API_KEY
          volumeMounts:
            - name: scripts
              mountPath: /scripts
              readOnly: true
      volumes:
        - name: scripts
          configMap:
            name: k6-script
EOF

echo "▶ Job k6 lance. Observation HPA pendant le test :"
kubectl -n "$NS" get hpa -w &
HPA_PID=$!
trap "kill $HPA_PID 2>/dev/null || true" EXIT

# Suivi des logs k6 jusqu'a fin
kubectl -n "$NS" wait --for=condition=ready pod -l job-name=k6-loadtest --timeout=60s
kubectl -n "$NS" logs -f job/k6-loadtest

# Cleanup
kubectl -n "$NS" delete job k6-loadtest --ignore-not-found
kubectl -n "$NS" delete configmap k6-script --ignore-not-found
echo "✅ Test fini, voir resultats ci-dessus"
