variable "project_id" {
  description = "GCP project to deploy into. Use a dedicated project for this platform."
  type        = string
}

variable "name" {
  description = "Prefix for all resource names."
  type        = string
  default     = "llm-p2p"
}

variable "region" {
  description = "Region for network and registry. europe-west2 = London (UK data residency)."
  type        = string
  default     = "europe-west2"
}

variable "zone" {
  description = "Zone for the (zonal) GKE cluster. Must offer the GPU type if the GPU pool is enabled."
  type        = string
  default     = "europe-west2-a"
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach the GKE control plane (e.g. your IP /32)."
  type        = list(string)

  validation {
    condition     = length(var.admin_cidrs) > 0
    error_message = "Provide at least one admin CIDR; the control plane is not open to the internet."
  }
}

variable "system_machine_type" {
  description = "Machine type for the system node pool (Argo CD, monitoring, gateway)."
  type        = string
  default     = "e2-standard-4"
}

variable "system_max_nodes" {
  description = "Upper bound for system pool autoscaling."
  type        = number
  default     = 3
}

variable "gpu_pool_enabled" {
  description = "Create the spot GPU node pool (Phase 6). Scales to zero when idle."
  type        = bool
  default     = false
}

variable "gpu_machine_type" {
  description = "Machine type for the GPU pool."
  type        = string
  default     = "g2-standard-8"
}

variable "gpu_type" {
  description = "Accelerator type for the GPU pool."
  type        = string
  default     = "nvidia-l4"
}

variable "billing_account_id" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX) for the budget alert. Empty = no budget created."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Monthly budget for alerts, in the billing account's currency."
  type        = number
  default     = 100
}

variable "budget_currency" {
  description = "Must match the billing account currency."
  type        = string
  default     = "GBP"
}
