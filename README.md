# LLM Pilot-to-Production Platform

A reference build by **Human Layer AI Ltd**: taking a GenAI pilot to secure, observable, cost-controlled, audit-ready production on Kubernetes (GKE).

**Scenario:** a UK bank's internal GenAI assistant is stuck in pilot. Risk and IT block go-live over data residency, cost, observability, unsafe releases, model governance (PRA SS1/23) and security. This repo solves each blocker and measures the result. See [PLAN.md](PLAN.md).

> This is a reference build, not a client engagement. All results are measured on this platform.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | GKE foundations, GitOps, monitoring, CI | ✅ code ready |
| 1 | KServe + vLLM serving | ⏳ |
| 2 | Tracing & dashboards (OpenTelemetry, Langfuse) | ⏳ |
| 3 | Evaluation-gated canary releases (Argo Rollouts) | ⏳ |
| 4 | Governance: model inventory, audit trail, SS1/23 mapping | ⏳ |
| 5 | Security hardening | ⏳ |
| 6 | GPU serving + cost benchmark | ⏳ |

## Architecture (Phase 0)

- **GKE Standard, zonal, `europe-west2` (London)** — private nodes, Cloud NAT egress, control plane locked to the admin IP, Workload Identity, Shielded Nodes, Dataplane V2 (NetworkPolicy enforcement), least-privilege node service account, spot `e2-standard-4` system pool (1–3 nodes).
- **GitOps:** Argo CD app-of-apps (`gitops/apps/`) manages cert-manager and kube-prometheus-stack.
- **Cost controls:** spot nodes, autoscaling, optional billing budget alert, GPU pool disabled until Phase 6.
- **CI:** `terraform fmt/validate`, tflint, yamllint, kubeconform, Trivy IaC scan, gitleaks.

Design decisions: [docs/decisions/](docs/decisions/).

## Quick start

Prerequisites: `gcloud` (authenticated), `terraform`, `kubectl`, `helm`, and a **dedicated GCP project** with billing enabled.

```bash
gcloud config set project <project-id>
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # set project_id, optional budget

make bootstrap   # one-off: APIs + versioned state bucket
make init
make plan        # review!
make apply       # creates billable resources
make platform    # Argo CD + GitOps hand-over
make argocd      # UI on https://localhost:8080
make grafana     # UI on http://localhost:3000

make destroy     # tear everything down when not in use
```

`make lint` runs the CI checks locally.

## Repository layout

```
infra/terraform/   GKE, network, registry, budget
platform/argocd/   Argo CD install values (the only non-GitOps component)
gitops/bootstrap/  root app-of-apps
gitops/apps/       platform components, synced by Argo CD
evals/             evaluation sets (Phase 3)
governance/        model inventory & audit records (Phase 4)
docs/decisions/    architecture decision records
```
