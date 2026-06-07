variable "region" {
  description = "Scaleway region"
  type        = string
  default     = "fr-par"
}

variable "zone" {
  description = "Scaleway zone"
  type        = string
  default     = "fr-par-1"
}

variable "demo_host" {
  description = "Hostname principal pour la demo (DNS deja existant)"
  type        = string
  default     = "lyonflow.demo.jedha.fr"
}
