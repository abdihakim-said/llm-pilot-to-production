# Resume guide

_Last session: 2026-10-07. Compute was torn down with `make down`; state, registry, buckets and CI identity were kept._

## Bring it back (≈15–20 min)

```bash
cd ~/llm-pilot-to-production
gcloud auth application-default login --project hl-llm-p2p-261007   # if credentials expired
make up        # terraform (cluster, NAT) -> Argo CD -> GitOps syncs everything -> waits for healthy
make grafana   # dashboards: Platform Health, Lending Assistant, Model Server
```

`make plan` locks the control plane to your **current** IP. If your IP changes later, run `make plan apply` again.
If images were ever deleted from the registry: `make images`.

## What is done

| Phase | Status |
|---|---|
| 0 Foundations: private GKE (London), GitOps, CI | ✅ |
| 1 vLLM model server (CPU), assistant-api (RAG, PII redaction, injection screening, release metadata) | ✅ |
| 2 Observability: MLflow 3 traces/feedback, 3 Grafana dashboards, 9 alert rules + runbooks | ✅ (alerts have no external receiver yet, by choice) |
| 3 Release gate: 38-case evaluation suite on canary pods + error rate; auto-promote / auto-abort | ✅ working, **needs one improvement (below)** |
| Keyless CI: test → build → Trivy → cosign sign → digest pinned in GitOps | ✅ |

Measured on CPU (n2-standard-4, Qwen2.5-0.5B): pass rate 86.8%, safety 100%, p95 answer 10.2s, 12.4 tokens/s, model restart 121s.

## Next, in order

1. **Gate blind spot (found in the v2 demo):** prompt v2 dropped "answer only from extracts" and "cite the section" but still scored 86.8%, so it was promoted. Add behaviour checks: answer cites a retrieved section; out-of-scope must decline. Then re-run the v2 demo; it must be rolled back.
2. **Phase 1b UI:** Next.js assistant + release console (SSO, streaming, release badge, feedback). Needs a subdomain on humanlayer.uk for HTTPS.
3. **Phase 4 governance:** model inventory, release records, SS1/23 mapping doc.
4. **Phase 5 security:** NetworkPolicies (only UI + release gate may call assistant-api), Kyverno (signed images only, cosign keyless identity of this repo).
5. **Phase 6 GPU:** blocked, quota denied (`GPUS_ALL_REGIONS` 0, `CPUS_ALL_REGIONS` 12). Re-request in Cloud Console with a business justification after some billing history.
6. **Phase 7:** case study write-up, demo video.

## Known limitations (be honest in the case study)

- The 0.5B CPU model answers 2/3 out-of-scope questions instead of declining; retrieval scores overlap (measured), so no score cut-off. Needs a larger model or a relevance check.
- Single model replica with Recreate strategy: each model-server change is ~2 min of downtime (no quota for a second node).
- vLLM 0.31 on CPU cannot reload its compile cache (`'function' object has no attribute 'finalize_loading'`); weights are cached on a PVC.
- MLflow history lives in an in-cluster Postgres and is lost on `make down` (add CloudNativePG backups to GCS).
