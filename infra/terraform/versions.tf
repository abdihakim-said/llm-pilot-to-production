terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6"
    }
  }

  # Bucket is passed at init time: make init (see Makefile).
  backend "gcs" {
    prefix = "llm-pilot-to-production/infra"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # Needed for APIs (e.g. billing budgets) that bill quota to a project
  # when Terraform runs with user credentials.
  user_project_override = true
  billing_project       = var.project_id
}
