# 0002 — Serving and release architecture

**Status:** accepted · 2026-10-07

## Context

The headline feature is an **evaluation-gated canary release**: a new model *or* prompt goes to a share of traffic, an automated evaluation decides promote or roll back, and every release leaves an audit record. The cluster is small (a few spot nodes, GPU quota pending), so every extra system has to earn its place.

## Decision

1. **vLLM serves the model as a plain Deployment** (`model-server-<version>`), CPU image now, GPU image in Phase 6. Each model version is its own Deployment and Service, so two models can run side by side during a release.
2. **`assistant-api` is the unit of release.** A release = an `assistant-api` image + config: system prompt version, model endpoint, retrieval settings. It does retrieval over the policy manual, PII redaction, prompt-injection screening, rate limiting, tracing, and returns release metadata (`release`, `prompt_version`, `model`, `track`) with every answer.
3. **Argo Rollouts manages `assistant-api`** with a canary strategy. An `AnalysisTemplate` runs the evaluation suite as a Job against the canary and checks error rate from Prometheus; failure aborts and rolls back automatically.
4. **MLflow 3** is the system of record: prompt and model registry, GenAI traces, user feedback, evaluation runs. Backed by CloudNativePG Postgres and a GCS artifact bucket via Workload Identity.
5. **Prometheus/Grafana** for platform and model metrics (vLLM exposes them natively).

## Alternatives considered

- **KServe `InferenceService`**: good model-serving API, but its built-in canary needs Knative (Serverless mode), and its generated Deployments can't be driven by Argo Rollouts. Deferred: model servers can move to KServe later without changing the release design, since releases happen at `assistant-api`.
- **LiteLLM / a separate AI gateway**: adds a service and a database for features (keys, limits, redaction) that one internal API covers here. A real bank with many AI apps should centralise these in a gateway.
- **Langfuse** (in the original plan): excellent, but self-hosting needs ClickHouse, Redis and object storage — too heavy for this cluster. MLflow 3 covers traces, feedback and registries in one tool and appears more often in UK job adverts.

## Consequences

- Canary weight is set by replica ratio (no service-mesh traffic splitting): 1 stable + 1 canary = 50%. Enough for the demo; a mesh or Gateway API plugin gives finer weights.
- Model swaps are releases too: deploy `model-server-v2`, then release an `assistant-api` version pointing at it.
