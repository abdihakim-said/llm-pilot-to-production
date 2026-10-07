output "cluster_name" {
  value = google_container_cluster.this.name
}

output "cluster_location" {
  value = google_container_cluster.this.location
}

output "get_credentials" {
  description = "Command to configure kubectl."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.this.name} --zone ${var.zone} --project ${var.project_id}"
}

output "registry" {
  description = "Docker registry for platform images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "mlflow_bucket" {
  value = google_storage_bucket.mlflow.name
}

output "mlflow_service_account" {
  value = google_service_account.mlflow.email
}

output "ci_service_account" {
  value = google_service_account.ci.email
}

output "wif_provider" {
  description = "Value for google-github-actions/auth workload_identity_provider."
  value       = google_iam_workload_identity_pool_provider.github.name
}
