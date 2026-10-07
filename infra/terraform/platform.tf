# --- CPU inference pool (vLLM on CPU until GPU quota is granted) ---------

resource "google_container_node_pool" "inference" {
  name     = "inference"
  cluster  = google_container_cluster.this.id
  location = var.zone

  autoscaling {
    min_node_count = 0
    max_node_count = 2
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    # N2 = Intel with AVX-512, which the vLLM CPU backend needs.
    machine_type = var.inference_machine_type
    spot         = true
    disk_type    = "pd-balanced"
    disk_size_gb = 100

    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    labels = {
      pool = "inference"
    }

    taint {
      key    = "workload"
      value  = "inference"
      effect = "NO_SCHEDULE"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}

# --- MLflow artifact store + identity -------------------------------------

resource "google_storage_bucket" "mlflow" {
  name                        = "${var.project_id}-mlflow"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = true
  }
}

resource "google_service_account" "mlflow" {
  account_id   = "${var.name}-mlflow"
  display_name = "MLflow tracking server"
}

resource "google_storage_bucket_iam_member" "mlflow" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mlflow.email}"
}

# Kubernetes SA mlops/mlflow acts as the Google SA (Workload Identity).
resource "google_service_account_iam_member" "mlflow_wi" {
  service_account_id = google_service_account.mlflow.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[mlops/mlflow]"

  depends_on = [google_container_cluster.this]
}

# --- Keyless CI: GitHub Actions -> Artifact Registry ----------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Only this repository's main branch can publish images.
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "ci" {
  account_id   = "${var.name}-ci"
  display_name = "CI image publisher"
}

resource "google_artifact_registry_repository_iam_member" "ci" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
