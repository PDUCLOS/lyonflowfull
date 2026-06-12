# =============================================================================
# kubernetes/base/velero/ — Backup cluster complet (Velero + Scaleway Object Storage)
# =============================================================================
# Sprint k8s Phase 2 : backup cluster (pas juste DB) avec Velero.
#
# Velero sauvegarde :
#   - Toutes les ressources K8s (Deployments, Services, ConfigMaps, etc.)
#   - Persistent volumes (snapshots Scaleway Block Storage)
#   - Restore complet ou partiel
#
# Storage backend : Scaleway Object Storage (S3-compatible, pas cher)
# =============================================================================

# Note : ce fichier est un template. Pour l'activer :
#   1. helm repo add vmware-tanzu https://vmware-tanzu.github.io/helm-charts
#   2. helm install velero vmware-tanzu/velero --namespace velero --create-namespace \
#        --set configuration.backupStorageLocation[0].name=default \
#        --set configuration.backupStorageLocation[0].provider=aws \
#        --set configuration.backupStorageLocation[0].bucket=lyonflow-velero \
#        --set configuration.backupStorageLocation[0].config.region=fr-par \
#        --set configuration.backupStorageLocation[0].config.s3ForcePathStyle=true \
#        --set configuration.backupStorageLocation[0].config.s3Url=https://s3.fr-par.scw.cloud \
#        --set credentials.existingSecret=velero-credentials \
#        --set deployRestic=true \
#        --set restic.disableNativeSnapshots=true
#   3. Creer le secret velero-credentials (access_key + secret_key Scaleway)
#   4. Appliquer les Schedule + BackupStorageLocation ci-dessous

---
# Schedule : backup quotidien du namespace lyonflow a 02h00 UTC
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: lyonflow-daily
  namespace: velero
spec:
  schedule: "0 2 * * *"
  template:
    includedNamespaces:
      - lyonflow
    # Snapshot des PVC (necessite restic)
    snapshotVolumes: true
    ttl: 720h  # 30 jours retention
  paused: false
---
# Schedule : backup weekly complet (tous namespaces, garde 90j)
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: lyonflow-weekly-full
  namespace: velero
spec:
  schedule: "0 3 * * 0"  # dimanche 03h
  template:
    includedNamespaces:
      - "*"
    snapshotVolumes: true
    ttl: 2160h  # 90 jours retention
  paused: false
---
# BackupStorageLocation : Scaleway Object Storage (S3-compatible)
# Note : ce manifeste est indicatif. La config reelle se fait via Helm values
# lors de l'install Velero.
# apiVersion: velero.io/v1
# kind: BackupStorageLocation
# metadata:
#   name: default
#   namespace: velero
# spec:
#   provider: aws
#   objectStorage:
#     bucket: lyonflow-velero
#   config:
#     region: fr-par
#     s3ForcePathStyle: "true"
#     s3Url: https://s3.fr-par.scw.cloud
