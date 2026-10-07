# Project comes from terraform.tfvars, so other gcloud work is unaffected.
PROJECT_ID   ?= $(shell sed -n 's/^project_id *= *"\(.*\)"/\1/p' infra/terraform/terraform.tfvars 2>/dev/null)
REGION       ?= europe-west2
ZONE         ?= europe-west2-a
NAME         ?= llm-p2p
STATE_BUCKET ?= $(PROJECT_ID)-tfstate
ARGOCD_CHART ?= 10.9.6

TF       := terraform -chdir=infra/terraform
MY_IP    := $(shell curl -s https://checkip.amazonaws.com)
TF_VARS  := -var project_id=$(PROJECT_ID) -var 'admin_cidrs=["$(MY_IP)/32"]'

.PHONY: help bootstrap init plan apply credentials platform up argocd grafana destroy lint

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'
	@echo "  project: $(PROJECT_ID)  zone: $(ZONE)"

bootstrap: ## One-off: enable base APIs and create the versioned Terraform state bucket
	gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com storage.googleapis.com --project $(PROJECT_ID)
	gcloud storage buckets describe gs://$(STATE_BUCKET) --project $(PROJECT_ID) >/dev/null 2>&1 || \
	  gcloud storage buckets create gs://$(STATE_BUCKET) --project $(PROJECT_ID) --location $(REGION) \
	    --uniform-bucket-level-access --public-access-prevention
	gcloud storage buckets update gs://$(STATE_BUCKET) --versioning

init: ## terraform init against the GCS state bucket
	$(TF) init -backend-config="bucket=$(STATE_BUCKET)"

plan: ## terraform plan (control plane locked to your current IP)
	$(TF) plan $(TF_VARS) -out=tfplan

apply: ## Apply the saved plan (creates billable resources)
	$(TF) apply tfplan

credentials: ## Point kubectl at the cluster
	gcloud container clusters get-credentials $(NAME) --zone $(ZONE) --project $(PROJECT_ID)

platform: credentials ## Install Argo CD, create the Grafana secret, hand over to GitOps
	kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n monitoring get secret grafana-admin >/dev/null 2>&1 || \
	  kubectl -n monitoring create secret generic grafana-admin \
	    --from-literal=admin-user=admin --from-literal=admin-password="$$(openssl rand -base64 24)"
	helm upgrade --install argocd argo-cd --repo https://argoproj.github.io/argo-helm \
	  --version $(ARGOCD_CHART) --namespace argocd --create-namespace \
	  -f platform/argocd/values.yaml --wait
	kubectl apply -f gitops/bootstrap/root-app.yaml

up: init plan apply platform ## Everything, end to end

argocd: ## Argo CD UI on https://localhost:8080 (prints admin password)
	@kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
	kubectl -n argocd port-forward svc/argocd-server 8080:443

grafana: ## Grafana on http://localhost:3000 (prints admin password)
	@kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo
	kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80

destroy: ## Tear down all cloud resources (state bucket is kept)
	@read -p "Destroy $(NAME) in $(PROJECT_ID)? Type the project id: " ans && [ "$$ans" = "$(PROJECT_ID)" ]
	$(TF) destroy $(TF_VARS)

lint: ## Same checks as CI
	terraform fmt -check -recursive infra
	$(TF) init -backend=false -input=false >/dev/null && $(TF) validate
	kubeconform -strict -summary -ignore-missing-schemas \
	  -schema-location default \
	  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
	  gitops/
	trivy config --severity HIGH,CRITICAL --exit-code 1 .
