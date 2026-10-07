# Runbooks

One section per alert in `platform/observability/rules.yaml`. Start every investigation from the **Platform Health** dashboard (`make grafana`), then follow the alert's section.

## AssistantHighErrorRate
**Meaning:** over 5% of assistant answers failed for 5 minutes. Users see "temporarily unavailable".
1. Check **ModelServerDown** / **ModelQueueBacklog**: most errors are the model being down or timing out.
2. `kubectl -n llm logs -l app.kubernetes.io/name=assistant-api --tail=50` and look for `model call failed`.
3. If errors started with a release, check the Rollouts dashboard: the canary analysis should already be aborting it. If it was promoted, roll back: `kubectl argo rollouts undo assistant-api -n llm`.

## AssistantSlowFirstToken
**Meaning:** p95 time to first token is above 20s for 10 minutes.
1. **Model Server** dashboard: is the queue growing? Prompt tokens/s at the ceiling? On CPU, prefill of long prompts dominates.
2. Short term: reduce `ASSISTANT_RETRIEVAL_K` or `ASSISTANT_MAX_TOKENS` via a release. Long term: GPU pool (Phase 6) or more model replicas.

## AssistantNoReadyPods
**Meaning:** no assistant-api pod is ready; the assistant is down.
1. `kubectl -n llm get pods -l app.kubernetes.io/name=assistant-api` and `describe` a failing pod.
2. Image pull errors: check the latest `release(assistant-api)` commit and that the build pipeline passed.
3. Crash loop: read the logs. Startup does not depend on MLflow or the model, so a crash is a code or config error: roll back.

## ModelServerDown
**Meaning:** Prometheus cannot scrape any vLLM pod.
1. `kubectl -n llm get pods -l app.kubernetes.io/name=model-server -o wide`.
2. Pending: the inference pool is scaling from zero or hit quota (`CPUS_ALL_REGIONS`). Check `kubectl get events -n llm`.
3. Spot pre-emption: the pod reschedules automatically; expect ~5 minutes including model download and warm-up.

## ModelQueueBacklog
**Meaning:** more than 5 requests waiting at vLLM for 5 minutes. Capacity is exhausted.
1. Confirm on the Model Server dashboard (running vs queued).
2. Reduce load (rate limit) or add capacity (replicas / GPU).

## ReleaseRolledBack
**Meaning:** an assistant-api canary failed the release gate and Argo Rollouts put all traffic back on stable. **Users are not affected**; this is the gate working.
1. `kubectl argo rollouts get rollout assistant-api -n llm` shows the failed analysis.
2. MLflow → experiment `release-gate` → the run for that release: `results.json` lists every failed case and why.
3. Fix and release again. To clear the alert without a new release: `kubectl argo rollouts retry rollout assistant-api -n llm` (re-runs the gate) or revert the Git commit.

## ArgoAppNotHealthy
**Meaning:** a GitOps-managed component has been Degraded/Missing for 5 minutes.
1. `kubectl -n argocd get applications` and open the app in the Argo CD UI (`make argocd`).
2. Drill into the unhealthy resource; usually a pod in CrashLoopBackOff or ImagePullBackOff.

## ArgoAppOutOfSync
**Meaning:** the cluster differs from Git for 10 minutes; a sync is failing.
1. Argo CD UI → app → *Sync status* shows the error (invalid manifest, missing CRD, webhook rejection).
2. Fix in Git. Never fix by hand in the cluster: self-heal will revert it.

## MLflowUnavailable
**Meaning:** MLflow is down. The assistant keeps answering, but traces, feedback and release-gate evidence are not recorded. Do not promote releases until it is back, because the audit trail would be incomplete.
1. `kubectl -n mlops get pods` and logs of `deploy/mlflow`.
2. Database: `kubectl -n mlops get cluster mlflow-db` (CloudNativePG) must be healthy.
