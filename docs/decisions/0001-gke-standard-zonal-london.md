# 0001 — GKE Standard, zonal, London region

**Status:** accepted · 2026-10-07

## Context

The platform must look and behave like what a UK regulated buyer would accept, while keeping a self-funded demo budget around £100. Later phases need GPU nodes (vLLM), KServe, Argo Rollouts and policy controllers.

## Decision

- **GKE Standard** over Autopilot: full control of node pools, GPU spot pools that scale to zero, and no restrictions on admission webhooks used by KServe, Kyverno and Argo Rollouts.
- **Zonal** cluster in **`europe-west2-a` (London)**: UK data residency story; zonal management fee is covered by the GKE free tier; HA control plane is not needed for a demo (noted as a "what I'd change for a real bank" item).
- **Private nodes + Cloud NAT**, control plane restricted to the admin IP: no node has a public IP.
- **Dataplane V2** for NetworkPolicy enforcement (Phase 5) without installing Calico.
- **Spot nodes everywhere**, accepting pre-emption, because nothing stateful lives in the cluster yet.
- **Argo CD installed by Helm once; everything else via GitOps.**

## Consequences

- Spot pre-emption can briefly disrupt demos; acceptable.
- For a real bank: regional cluster, private endpoint via IAP/bastion, CMEK, Binary Authorization, separate projects per environment.
- GPU availability for `nvidia-l4` in `europe-west2-a` must be checked before Phase 6 (`gcloud compute accelerator-types list --filter=zone:europe-west2-a`).
