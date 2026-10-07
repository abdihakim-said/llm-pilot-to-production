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
