# Scaleway Kapsule ephemere — cluster K8s pour demo Jedha
#
# Usage :
#   cd cloud-demo/terraform
#   terraform init
#   terraform apply -auto-approve
#   # → outputs : kubeconfig, lb_ip, cluster_id
#
# Tear-down :
#   terraform destroy -auto-approve

terraform {
  required_version = ">= 1.7"
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.40"
    }
  }
}

provider "scaleway" {
  zone   = var.zone
  region = var.region
}

resource "scaleway_k8s_cluster" "demo" {
  name                  = "lyonflow-demo-jedha"
  description           = "Cluster ephemere demo soutenance RNCP 38777"
  version               = "1.29"
  cni                   = "cilium"
  delete_additional_resources = true
  type                  = "kapsule"

  autoscaler_config {
    disable_scale_down               = false
    scale_down_delay_after_add       = "10m"
    scale_down_unneeded_time         = "10m"
    estimator                        = "binpacking"
    expander                         = "least-waste"
    ignore_daemonsets_utilization    = true
  }

  auto_upgrade {
    enable                        = false
    maintenance_window_start_hour = 3
    maintenance_window_day        = "monday"
  }

  tags = ["demo", "jedha", "ephemere"]
}

resource "scaleway_k8s_pool" "system" {
  cluster_id  = scaleway_k8s_cluster.demo.id
  name        = "system"
  node_type   = "POP2-2C-8G"
  size        = 1
  min_size    = 1
  max_size    = 2
  autoscaling = true
  autohealing = true
  zone        = var.zone

  tags = ["demo", "system"]
}

resource "scaleway_k8s_pool" "workload" {
  cluster_id  = scaleway_k8s_cluster.demo.id
  name        = "workload"
  node_type   = "POP2-4C-16G"
  size        = 1
  min_size    = 1
  max_size    = 3
  autoscaling = true
  autohealing = true
  zone        = var.zone

  tags = ["demo", "workload"]
}

# Pool GPU optionnel (decommente pour activer)
# resource "scaleway_k8s_pool" "gpu" {
#   cluster_id = scaleway_k8s_cluster.demo.id
#   name       = "gpu"
#   node_type  = "GPU-3070-S"
#   size       = 1
#   min_size   = 0
#   max_size   = 1
#   autoscaling = true
#   zone       = var.zone
#   tags = ["demo", "gpu"]
# }

# Kubeconfig export
resource "local_sensitive_file" "kubeconfig" {
  content  = scaleway_k8s_cluster.demo.kubeconfig[0].config_file
  filename = "${path.module}/../kubeconfig"
}
