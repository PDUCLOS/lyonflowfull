output "cluster_id" {
  value       = scaleway_k8s_cluster.demo.id
  description = "ID du cluster Kapsule"
}

output "cluster_status" {
  value = scaleway_k8s_cluster.demo.status
}

output "kubeconfig_path" {
  value       = "${path.module}/../kubeconfig"
  description = "Chemin du kubeconfig genere localement"
}

output "next_steps" {
  value = <<-EOT

    Cluster pret. Etapes suivantes :

      export KUBECONFIG=$(pwd)/../kubeconfig
      kubectl get nodes

      # Bootstrap cluster (ingress-nginx, cert-manager, sealed-secrets)
      ../../kubernetes/scripts/bootstrap-cluster.sh

      # Sceller secrets demo
      cp ../../kubernetes/.env.demo.example .env
      ../../kubernetes/scripts/seal-secrets.sh .env \
        > ../overlays/jedha-demo/sealed-secret.yaml

      # Deploy
      kustomize build ../overlays/jedha-demo | kubectl apply -f -

      # Seed data 7j
      ../scripts/seed-demo-data.sh

  EOT
}
