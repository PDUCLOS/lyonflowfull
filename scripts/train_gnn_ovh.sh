#!/bin/bash
# =============================================================================
# train_gnn_ovh.sh — Pipeline GNN training hebdomadaire via OVH AI Training
# =============================================================================
#
# Architecture (option 3 — ovhai data upload, pas de S3 externe) :
#   1. Export PostgreSQL → Parquet local (/tmp/gnn_export/)
#   2. ovhai data upload → stockage interne OVH AI Training
#   3. ovhai job run → GPU V100, monte les données, entraîne
#   4. ovhai data download → récupère model.pt
#   5. Copie model.pt → /opt/lyonflow/models/ + register MLflow
#
# Cron : dimanche 03h00
#   0 3 * * 0  root  /opt/lyonflow/scripts/train_gnn_ovh.sh >> /opt/lyonflow/logs/gnn_training.log 2>&1
#
# Prérequis :
#   - ovhai CLI installé et authentifié (ovhai login)
#   - Image Docker pushée sur le registry OVH
#   - PostgreSQL accessible avec gold.fact_traffic_series peuplée
# =============================================================================

set -euo pipefail

# --- Config ---
REGION="GRA"
IMAGE="${LYONFLOW_GNN_IMAGE:-ghcr.io/pduclos/lyonflow-gnn-training:latest}"
GPU_MODEL="${LYONFLOW_GNN_GPU:-V100S}"
EXPORT_DIR="/tmp/gnn_export"
MODELS_DIR="/opt/lyonflow/models"
DATA_CONTAINER="lyonflow-gnn-data"
OUTPUT_CONTAINER="lyonflow-gnn-output"
TIMEOUT_SECONDS=1800
POLL_INTERVAL=30
MAX_POLLS=60
LOG_PREFIX="[gnn-train]"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_PREFIX $*"; }

# --- Step 1 : Export data ---
log "Step 1/5 — Exporting training data from PostgreSQL..."
rm -rf "$EXPORT_DIR"
cd /opt/lyonflow
python3 scripts/export_gnn_data.py --output-dir "$EXPORT_DIR" --days 7

if [ ! -f "$EXPORT_DIR/features.parquet" ]; then
    log "ERROR: Export failed — features.parquet missing"
    exit 1
fi

EXPORT_SIZE=$(du -sh "$EXPORT_DIR" | cut -f1)
log "  Export: $EXPORT_SIZE"

# --- Step 2 : Upload data to OVH AI Training storage ---
log "Step 2/5 — Uploading data to OVH AI Training..."
ovhai data upload "$EXPORT_DIR" "${DATA_CONTAINER}@${REGION}" --remove

# --- Step 3 : Launch GPU job ---
log "Step 3/5 — Submitting GPU job ($GPU_MODEL)..."
JOB_ID=$(ovhai job run "$IMAGE" \
    --name "lyonflow-gnn-$(date +%Y%m%d)" \
    --gpu 1 \
    --gpu-model "$GPU_MODEL" \
    --volume "${DATA_CONTAINER}@${REGION}:/data:ro:cache" \
    --volume "${OUTPUT_CONTAINER}@${REGION}:/output:rw" \
    --timeout "$TIMEOUT_SECONDS" \
    --output json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

log "  Job submitted: $JOB_ID"

# --- Wait for job completion ---
log "  Waiting for job (poll every ${POLL_INTERVAL}s, max ${MAX_POLLS} polls)..."
for i in $(seq 1 "$MAX_POLLS"); do
    STATUS=$(ovhai job get "$JOB_ID" --output json 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['state'])")

    case "$STATUS" in
        DONE)
            log "  Job completed successfully"
            break
            ;;
        FAILED|ERROR|TIMEOUT)
            log "ERROR: Job $STATUS"
            ovhai job logs "$JOB_ID" 2>/dev/null || true
            exit 1
            ;;
        *)
            if [ "$((i % 4))" -eq 0 ]; then
                log "  Still running ($STATUS)... poll $i/$MAX_POLLS"
            fi
            sleep "$POLL_INTERVAL"
            ;;
    esac

    if [ "$i" -eq "$MAX_POLLS" ]; then
        log "ERROR: Timeout waiting for job"
        ovhai job stop "$JOB_ID" 2>/dev/null || true
        exit 1
    fi
done

# Print job logs
log "  --- Job logs ---"
ovhai job logs "$JOB_ID" 2>/dev/null || true
log "  --- End logs ---"

# --- Step 4 : Download trained model ---
log "Step 4/5 — Downloading trained model..."
DOWNLOAD_DIR="/tmp/gnn_output"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"
ovhai data download "${OUTPUT_CONTAINER}@${REGION}" "$DOWNLOAD_DIR"

if [ ! -f "$DOWNLOAD_DIR/stgcn_h60.pt" ]; then
    log "ERROR: Model file not found in output"
    ls -la "$DOWNLOAD_DIR"
    exit 1
fi

# --- Step 5 : Deploy model ---
log "Step 5/5 — Deploying model..."
mkdir -p "$MODELS_DIR"
cp "$DOWNLOAD_DIR/stgcn_h60.pt" "$MODELS_DIR/stgcn_h60.pt"
cp "$DOWNLOAD_DIR/train_meta.json" "$MODELS_DIR/stgcn_train_meta.json" 2>/dev/null || true

# Register in MLflow (best-effort)
python3 -c "
import json, sys
sys.path.insert(0, '/opt/lyonflow')
try:
    from src.ml.mlflow_integration import MLflowTracker, is_mlflow_available
    if not is_mlflow_available():
        print('MLflow not available — skipping registration')
        sys.exit(0)
    meta = json.load(open('$DOWNLOAD_DIR/train_meta.json'))
    tracker = MLflowTracker('stgcn_traffic')
    with tracker.start_run(run_name='stgcn_h60_weekly') as _:
        tracker.log_params({
            'n_nodes': meta['n_nodes'],
            'n_edges': meta['n_edges'],
            'n_params': meta['n_params'],
            'epochs': meta['epochs_run'],
            'device': meta['device'],
            'gpu': meta.get('gpu', 'unknown'),
        })
        tracker.log_metrics({
            'mae_kmh': meta['mae_kmh'],
            'rmse_kmh': meta['rmse_kmh'],
            'val_loss': meta['best_val_loss'],
            'training_seconds': meta['elapsed_seconds'],
        })
        tracker.log_artifact('$MODELS_DIR/stgcn_h60.pt')
    print(f\"MLflow: registered (MAE={meta['mae_kmh']:.2f} km/h)\")
except Exception as e:
    print(f'MLflow registration failed (non-blocking): {e}')
" 2>&1 || true

# Cleanup
rm -rf "$EXPORT_DIR" "$DOWNLOAD_DIR"

# Print summary
if [ -f "$MODELS_DIR/stgcn_train_meta.json" ]; then
    python3 -c "
import json
m = json.load(open('$MODELS_DIR/stgcn_train_meta.json'))
print(f\"  Nodes: {m['n_nodes']}, Edges: {m['n_edges']}, Params: {m['n_params']}\")
print(f\"  MAE: {m['mae_kmh']:.2f} km/h, RMSE: {m['rmse_kmh']:.2f} km/h\")
print(f\"  Training: {m['elapsed_seconds']:.0f}s on {m.get('gpu', 'CPU')}\")
" 2>&1 || true
fi

log "Pipeline complete. Model deployed to $MODELS_DIR/stgcn_h60.pt"
