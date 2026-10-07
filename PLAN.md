# LLM Pilot-to-Production Platform — Build Plan

**Owner:** Human Layer AI Ltd · **Created:** 2026-10-07
**Purpose:** a public, enterprise-grade reference build that proves one offer:

> *"I take your GenAI/agent pilots into production on Kubernetes — fast, observable, cost-controlled, and audit-ready for regulators."*

Evidence for this positioning: `~/reports/MLOps demand UK 2026.md`.

---

## 1. The problem (reference scenario)

Framed honestly as a **reference scenario**, not a client engagement:

> A UK bank has a working GenAI pilot — an internal assistant that answers staff questions about lending policy. It runs on a data scientist's notebook calling a hosted API. Risk and IT won't let it go live because:

| # | Blocker | What the bank's risk/IT team actually asks |
|---|---|---|
| B1 | **Data residency & cost** | "Customer data can't leave our tenancy, and the API bill is unpredictable." |
| B2 | **No observability** | "When it gives a wrong answer, how do we find out, and why?" |
| B3 | **Unsafe releases** | "How do we change the model or prompt without breaking it for 5,000 staff?" |
| B4 | **No model governance** | "PRA SS1/23 says every model — including AI and vendor models — must be in our inventory, validated, and monitored. Where's the evidence?" |
| B5 | **Security** | "PII in prompts, prompt injection, who can call it, network exposure." |

Each blocker maps to a component and a **measured** result below. Every number in the final write-up must come from running this build.

---

## 2. Target architecture

```
           staff app / curl
                 │
        ┌────────▼─────────┐
        │  AI Gateway      │  LiteLLM proxy: API keys, rate limits,
        │                  │  PII redaction (Presidio), injection checks   ← B5
        └────────┬─────────┘
                 │  OpenTelemetry traces ──────────────► Langfuse (self-hosted) ← B2
        ┌────────▼─────────┐
        │  KServe          │  vLLM runtime, Qwen2.5-1.5B-Instruct (Apache-2.0)
        │  InferenceService│  stable + canary revisions                      ← B1
        └────────┬─────────┘
                 │  vLLM metrics ──► Prometheus/Grafana ──► KEDA autoscaling ← B1
                 │
   Argo Rollouts canary ◄── AnalysisTemplate: eval score, error rate, p95   ← B3
                 │
   MLflow 3 registry + model inventory + release audit log (Git + MLflow)  ← B4
                 │
   Argo CD (GitOps) · Terraform (GKE) · Kyverno policies · NetworkPolicies ← B5
```

**Cluster target: Google Cloud (GKE)** — no local cluster.
- GKE Standard, zonal, `europe-west2` (London), private spot nodes. See `docs/decisions/0001-gke-standard-zonal-london.md`.
- Spot L4 GPU pool added in Phase 6, scales to zero.
- **Budget cap: ~£100 total** — set `billing_account_id` so Terraform creates a budget alert, and `make destroy` whenever not actively working.

---

## 3. Phases

Assumes part-time (~10–15 h/week). Each phase ends with something demo-able and committed.

### Phase 0 — Foundations (week 1)
- [ ] New public GitHub repo `llm-pilot-to-production` under your own account.
- [x] Repo layout: `infra/` (Terraform), `platform/` (Helm/Kustomize), `gitops/` (Argo CD apps), `evals/`, `governance/`, `docs/`.
- [x] `make up` → GKE cluster (Terraform) with cert-manager, Prometheus/Grafana, Argo CD. Ingress deferred to Phase 1 (gateway).
- [x] GitHub Actions: terraform validate, tflint, yamllint, kubeconform, Trivy IaC scan, gitleaks.
- **Demo:** one command brings up an empty, GitOps-managed platform.

### Phase 1 — Serve the model (weeks 2–3) · B1
- [ ] KServe + vLLM `ServingRuntime`; `InferenceService` for Qwen2.5-1.5B-Instruct. Try KServe `LLMInferenceService` if the installed version supports it.
- [ ] OpenAI-compatible endpoint behind the gateway.
- [ ] Load test with `k6` or `vllm bench`: record p50/p95 latency, tokens/sec, at 1/10/50 concurrent users.
- **Demo:** curl the bank assistant; Grafana shows vLLM metrics.

### Phase 1b — Assistant UI (weeks 3–4) · the face of the demo
An internal "Lending Policy Assistant" that a bank's staff would actually use, and that a non-technical buyer understands in 30 seconds.

**Stack:** Next.js (App Router) + TypeScript, Tailwind + shadcn/ui, streaming via the OpenAI-compatible API through the gateway (never directly to the model).

**User experience**
- [ ] Streaming chat with markdown, copy, regenerate, stop; conversation history per user.
- [ ] **Release badge** on every answer: model + prompt version and *stable / canary* — makes the Phase 3 canary visible to the audience.
- [ ] **Safety indicators:** "2 personal details redacted before reaching the model" (Phase 5), refusal messages that explain why.
- [ ] 👍/👎 + comment feedback, sent to Langfuse against the trace (Phase 2).
- [ ] Clear disclaimer banner ("AI-generated — verify against the policy manual"), graceful handling of rate limits, timeouts and model unavailability.
- [ ] Polished design: dark/light themes, responsive, empty states, suggested questions, loading skeletons.

**Release console (admin view, filled in Phases 3–4)**
- [ ] Live rollout status (stable vs canary %, step, analysis results), eval scores per release, rollback history.
- [ ] Model inventory and per-release audit records — the "show me evidence for model X" screen for risk teams.
- [ ] Deep links to Langfuse traces and Grafana dashboards.

**Enterprise requirements**
- [ ] **SSO:** OIDC sign-in (Google Workspace now; Entra ID documented), roles `staff` and `risk-admin`; console restricted to `risk-admin`.
- [ ] **Security:** server-side calls only (no API keys in the browser), strict CSP and security headers, CSRF protection, input length limits, non-root distroless image, signed with cosign, Trivy-scanned.
- [ ] **Exposure:** GKE Gateway + Google-managed TLS on a subdomain (e.g. `assistant.demo.humanlayer.uk`), Cloud Armor rate limiting; optional IAP in front.
- [ ] **Accessibility:** WCAG 2.2 AA, keyboard navigable, axe checks in CI.
- [ ] **Quality gates in CI:** unit tests, Playwright end-to-end (streaming, feedback, error states), Lighthouse budget (performance/accessibility ≥ 90).
- [ ] **Observability:** OpenTelemetry from browser request → gateway → model in one trace; web vitals to Grafana.
- [ ] Deployed by Argo CD like everything else; two replicas, PodDisruptionBudget, HPA.
- **Demo:** sign in with SSO, ask a lending question, watch the answer stream with its release badge, give feedback, then open the console and show the matching trace and audit record.

### Phase 2 — Observability (week 4) · B2
- [ ] Self-hosted Langfuse via Helm; OpenTelemetry tracing from gateway → model.
- [ ] Grafana dashboard: requests, queue depth, TTFT, tokens/sec, GPU util (cloud), cost/1k requests.
- [ ] Alerts: p95 latency, error rate, queue backlog.
- **Demo:** trace a bad answer end-to-end from prompt to response.

### Phase 3 — Evaluation-gated canary releases (weeks 5–6) · B3  ← headline feature
- [ ] `evals/`: 50–100 lending-policy Q&A cases + refusal/safety cases; scoring with promptfoo (deterministic checks + LLM-as-judge).
- [ ] Argo Rollouts canary: 10% → 50% → 100%, gated by an `AnalysisTemplate` that checks eval pass rate, error rate and p95 from Prometheus.
- [ ] Deliberately ship a worse prompt/model → show automatic rollback.
- **Demo (the money shot):** a bad release is caught and rolled back with no human involved — recorded as a 2-minute video.

### Phase 4 — Governance & audit trail (week 7) · B4
- [ ] MLflow 3: register model + prompt versions with eval results attached.
- [ ] `governance/model-inventory.yaml`: id, owner, purpose, risk tier, vendor/open-source, validation date, monitoring links.
- [ ] Release audit record auto-generated per rollout (who, what changed, eval results, approval, rollout outcome) — committed to Git.
- [ ] `docs/ss1-23-mapping.md`: map each artefact to SS1/23's five principles (model identification & risk classification; governance; development, implementation & use; independent validation; risk mitigants). Note EU AI Act record-keeping/logging alignment. *State clearly this is an engineering aid, not legal/compliance advice.*
- **Demo:** "Show me evidence for model X" answered in one click.

### Phase 5 — Security hardening (week 8) · B5
- [ ] Presidio PII redaction in the gateway; prompt-injection test cases added to evals.
- [ ] Kyverno: signed images only (cosign), no privileged pods, resource limits required.
- [ ] Default-deny NetworkPolicies; GKE Workload Identity, no static secrets.
- **Demo:** PII in a prompt is redacted in both the model input and the traces.

### Phase 6 — GPU on GKE + cost benchmark (week 9) · B1
- [ ] `gpu_pool_enabled = true`: spot L4 pool (GKE installs NVIDIA drivers).
- [ ] KEDA scaling on vLLM `num_requests_waiting`; scale GPU pool to zero when idle.
- [ ] Benchmark: latency, throughput, **£ per 1k requests** vs the hosted-API baseline. Destroy the cluster.
- **Demo:** cost and latency table with real numbers.

### Phase 7 — Package it to sell (week 10)
- [ ] `docs/case-study.md` (template below), architecture diagram, 3–5 min demo video.
- [ ] LinkedIn post + website page; link from Upwork/Toptal profiles.
- [ ] Turn into the **readiness assessment** checklist (offer ladder step 1).
- [ ] Pitch a discounted fixed-price pilot to 1–2 UK fintechs/scale-ups in exchange for a publishable anonymised case study.

---

## 4. Case study template (honest framing)

**Title:** *Reference build: taking a bank's GenAI pilot to audit-ready production on Kubernetes*

1. **The problem** — the five blockers (B1–B5), in the buyer's words.
2. **Constraints** — data residency, regulator expectations (SS1/23), small ops team, cost ceiling.
3. **Architecture & key decisions** — with the trade-offs (e.g. self-hosted 1.5B model vs hosted API).
4. **Measured results** — only numbers from this build: p95 latency, tokens/sec, £/1k requests, rollback time, % of releases with full audit evidence.
5. **What I'd do differently at a real bank** — shows judgement (bigger model, HA, change-board integration, DR).
6. **How this becomes your project** — link to the assessment offer.

Wording rule: say *"reference build"* / *"I built"*, never *"for a client"* until a real client signs off.

---

## 5. Reuse from existing work

- `~/humanlayer-platform/agents/mlops/model_deployment_agent.py` is currently a prompt + code templates (FastAPI/PyTorch serving), not a running system. Reuse its instruction text as the seed for a **release assistant** that drafts the Phase 4 audit record and rollout notes — a nice "AI operating the AI platform" touch, added only after Phases 1–4 work.
- `~/github-repos/digits-recognizer-kubeflow` is an unmodified Cisco fork: don't reuse it as evidence; add a credit line to its README or archive it.

---

## 6. Definition of done

- [ ] `make up` works from a clean clone, documented in README.
- [ ] Demo video shows: request → trace → bad release → automatic rollback → audit record.
- [ ] Results table filled with measured numbers.
- [ ] Case study published; repo pinned on GitHub; linked from the offer.
- [ ] Cloud resources destroyed; total spend recorded.
