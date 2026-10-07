"""Generate the Grafana dashboards in platform/observability/dashboards/.

Dashboards are code: edit here, run `python3 tools/gen_dashboards.py`, commit
the JSON. Grafana's sidecar loads them from ConfigMaps.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "platform/observability/dashboards"
DS = {"type": "prometheus", "uid": "prometheus"}


def _target(expr: str, legend: str = "", instant: bool = False, fmt: str = "time_series") -> dict:
    return {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": "A",
            "instant": instant, "range": not instant, "format": fmt}


def stat(title, expr, unit="short", x=0, y=0, w=6, thresholds=None, decimals=None):
    steps = [{"color": "green", "value": None}] + [
        {"color": c, "value": v} for v, c in (thresholds or [])
    ]
    return {
        "type": "stat", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": 4},
        "targets": [_target(expr, instant=True)],
        "options": {"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"]}},
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
                                     "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
    }


def ts(title, targets, unit="short", x=0, y=0, w=12, h=8, stack=False):
    return {
        "type": "timeseries", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [dict(_target(e, l), refId=chr(65 + i)) for i, (e, l) in enumerate(targets)],
        "fieldConfig": {"defaults": {"unit": unit, "custom": {
            "fillOpacity": 15, "lineWidth": 2, "showPoints": "never",
            "stacking": {"mode": "normal" if stack else "none"}}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi"}},
    }


def table(title, expr, x=0, y=0, w=12, h=8):
    return {
        "type": "table", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [_target(expr, instant=True, fmt="table")],
        "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True}}}],
        "options": {"showHeader": True},
    }


def row(title, y):
    return {"type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}}


def dashboard(uid, title, panels, description):
    for i, p in enumerate(panels, start=1):
        p["id"] = i
    return {
        "uid": uid, "title": title, "description": description, "tags": ["lending-assistant"],
        "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
        "time": {"from": "now-3h", "to": "now"}, "panels": panels,
        "templating": {"list": []}, "annotations": {"list": []}, "editable": False,
    }


P95 = "histogram_quantile(0.95, sum by (le{by}) (rate({m}_bucket[5m])))"
P50 = "histogram_quantile(0.50, sum by (le{by}) (rate({m}_bucket[5m])))"

service = dashboard("lending-assistant", "Lending Assistant — Service", [
    row("Now", 0),
    stat("Requests / min", "sum(rate(assistant_requests_total[5m])) * 60", x=0, y=1, decimals=1),
    stat("Error rate", 'sum(rate(assistant_requests_total{outcome="error"}[5m])) / clamp_min(sum(rate(assistant_requests_total[5m])), 1e-9)',
         unit="percentunit", x=6, y=1, thresholds=[(0.01, "orange"), (0.05, "red")]),
    stat("p95 answer time", P95.format(by="", m="assistant_request_seconds"), unit="s", x=12, y=1,
         thresholds=[(15, "orange"), (30, "red")]),
    stat("p95 time to first token", P95.format(by="", m="assistant_time_to_first_token_seconds"), unit="s", x=18, y=1,
         thresholds=[(10, "orange"), (20, "red")]),
    row("Traffic and releases", 5),
    ts("Requests by outcome", [("sum by (outcome) (rate(assistant_requests_total[5m])) * 60", "{{outcome}}")],
       unit="reqpm", x=0, y=6, stack=True),
    ts("Traffic by track (stable vs canary)", [("sum by (track, release) (rate(assistant_requests_total[5m])) * 60", "{{track}} {{release}}")],
       unit="reqpm", x=12, y=6),
    row("Latency", 14),
    ts("Answer time by track", [
        (P95.format(by=", track", m="assistant_request_seconds"), "p95 {{track}}"),
        (P50.format(by=", track", m="assistant_request_seconds"), "p50 {{track}}"),
    ], unit="s", x=0, y=15),
    ts("Time to first token by track", [
        (P95.format(by=", track", m="assistant_time_to_first_token_seconds"), "p95 {{track}}"),
        (P50.format(by=", track", m="assistant_time_to_first_token_seconds"), "p50 {{track}}"),
    ], unit="s", x=12, y=15),
    row("Safety and quality", 23),
    ts("Personal data redacted (per hour)", [("sum by (type) (increase(assistant_redactions_total[1h]))", "{{type}}")],
       x=0, y=24, w=8),
    ts("Blocked / out-of-scope (per hour)", [
        ('sum(increase(assistant_requests_total{outcome="blocked"}[1h]))', "prompt injection blocked"),
        ('sum(increase(assistant_requests_total{outcome="no_context"}[1h]))', "not in policy manual"),
    ], x=8, y=24, w=8),
    ts("User feedback (per hour)", [("sum by (value) (increase(assistant_feedback_total[1h]))", "{{value}}")],
       x=16, y=24, w=8),
], "Golden signals, release tracks and safety for the Lending Policy Assistant.")

model = dashboard("model-server", "Model Server — vLLM", [
    row("Now", 0),
    stat("Running requests", "sum(vllm:num_requests_running)", x=0, y=1),
    stat("Queued requests", "sum(vllm:num_requests_waiting)", x=6, y=1, thresholds=[(2, "orange"), (5, "red")]),
    stat("Generation tokens / s", "sum(rate(vllm:generation_tokens_total[5m]))", x=12, y=1, decimals=1),
    stat("KV cache used", "max(vllm:kv_cache_usage_perc)", unit="percentunit", x=18, y=1,
         thresholds=[(0.8, "orange"), (0.95, "red")]),
    row("Latency", 5),
    ts("Time to first token", [
        (P95.format(by="", m="vllm:time_to_first_token_seconds"), "p95"),
        (P50.format(by="", m="vllm:time_to_first_token_seconds"), "p50"),
    ], unit="s", x=0, y=6),
    ts("End-to-end request latency", [
        (P95.format(by="", m="vllm:e2e_request_latency_seconds"), "p95"),
        (P50.format(by="", m="vllm:e2e_request_latency_seconds"), "p50"),
    ], unit="s", x=12, y=6),
    row("Throughput and capacity", 14),
    ts("Tokens / s", [
        ("sum(rate(vllm:prompt_tokens_total[5m]))", "prompt (prefill)"),
        ("sum(rate(vllm:generation_tokens_total[5m]))", "generation (decode)"),
    ], x=0, y=15),
    ts("Model pod CPU and memory", [
        ('sum(rate(container_cpu_usage_seconds_total{namespace="llm", pod=~"model-server.*", container="vllm"}[5m]))', "CPU cores"),
        ('sum(container_memory_working_set_bytes{namespace="llm", pod=~"model-server.*", container="vllm"}) / 1e9', "memory GB"),
    ], x=12, y=15),
], "vLLM serving metrics: queueing, latency, throughput, KV cache and resource use.")

platform = dashboard("platform-health", "Platform Health", [
    row("Now", 0),
    stat("Firing alerts", 'count(ALERTS{alertstate="firing", alertname!~"Watchdog|InfoInhibitor"}) or vector(0)',
         x=0, y=1, thresholds=[(1, "orange"), (3, "red")]),
    stat("Pods not ready", 'sum(kube_pod_status_ready{condition="false", namespace!~"kube-system|gke-.*"}) or vector(0)',
         x=6, y=1, thresholds=[(1, "red")]),
    stat("Container restarts (1h)", "sum(increase(kube_pod_container_status_restarts_total[1h])) or vector(0)",
         x=12, y=1, decimals=0, thresholds=[(1, "orange"), (5, "red")]),
    stat("Argo CD apps not healthy", 'count(argocd_app_info{health_status!="Healthy"}) or vector(0)',
         x=18, y=1, thresholds=[(1, "orange")]),
    row("What needs attention", 5),
    table("Firing alerts", 'ALERTS{alertstate="firing", alertname!~"Watchdog|InfoInhibitor"}', x=0, y=6, w=12),
    table("Restarting containers (1h)", "increase(kube_pod_container_status_restarts_total[1h]) > 0", x=12, y=6, w=12),
    row("Delivery", 14),
    table("Argo CD applications", "argocd_app_info", x=0, y=15, w=12),
    table("Rollouts", "rollout_info", x=12, y=15, w=12),
    row("Capacity", 23),
    ts("CPU requested vs allocatable by pool", [
        ('sum by (label_pool) (kube_pod_container_resource_requests{resource="cpu"} * on(node) group_left(label_pool) kube_node_labels)', "requested {{label_pool}}"),
        ('sum by (label_pool) (kube_node_status_allocatable{resource="cpu"} * on(node) group_left(label_pool) kube_node_labels)', "allocatable {{label_pool}}"),
    ], unit="cores", x=0, y=24),
    ts("Memory requested vs allocatable by pool", [
        ('sum by (label_pool) (kube_pod_container_resource_requests{resource="memory"} * on(node) group_left(label_pool) kube_node_labels)', "requested {{label_pool}}"),
        ('sum by (label_pool) (kube_node_status_allocatable{resource="memory"} * on(node) group_left(label_pool) kube_node_labels)', "allocatable {{label_pool}}"),
    ], unit="bytes", x=12, y=24),
], "Alerts, restarts, GitOps sync, rollouts and cluster capacity at a glance.")

for d in (service, model, platform):
    (OUT / f"{d['uid']}.json").write_text(json.dumps(d, indent=2) + "\n")
    print("wrote", d["uid"])
