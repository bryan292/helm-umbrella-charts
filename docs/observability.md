# Platform observability

The AWS and Azure overlays install the same monitoring, Loki, Alloy and OpenCost releases.
An `observability` Flux Kustomization waits for `platform` so monitoring CRDs exist before
applying the PodMonitor, PrometheusRule and Grafana dashboard. All administrative Services
are ClusterIP and no Ingress/Gateway is provisioned. Use Kubernetes RBAC-authorized local
port-forwarding; do not expose these endpoints directly to the internet.

```sh
kubectl -n monitoring port-forward --address 127.0.0.1 svc/monitoring-grafana 3000:80
kubectl -n monitoring port-forward --address 127.0.0.1 svc/monitoring-kube-prometheus-prometheus 9090:9090
kubectl -n monitoring port-forward --address 127.0.0.1 svc/monitoring-kube-prometheus-alertmanager 9093:9093
```

Grafana retains its existing admin Secret. Retrieve credentials only through an authorized
local session; do not paste them into logs or tickets. The provisioned dashboard UID is
`multicloud-platform`, with Flux state/latency, CPU/memory requests and usage, estimated
node cost and Flux logs. OpenCost uses public provider pricing and fallback models; its
metrics are estimates, not billed spend, discounts or a budget. The OpenCost UI is disabled.
Billing reconciliation and budget enforcement belong to SPEC-012.

## Availability objective

`platform:reconciliation_available:ratio` is 1 only when all observed Flux resources in
`flux-system` are Ready and not suspended. It is 0 during missing telemetry. The dedicated
`observability-acceptance` probe is excluded from the SLI but still triggers the failure
alert. The target is 99.9% over 30 days, measured by samples of this platform reconciliation
indicator; it is not an application's request-success SLO or a guarantee of continuous
measurement during Prometheus downtime. Prometheus retains up to 35 days, bounded by a
24 GB retention size on the existing 30 GiB PVC. A fresh installation or size truncation
can yield a partial window: a 30-day panel does not certify 30 days of history.

- `FluxReconciliationFailure`: a resource remains not Ready for two minutes. Inspect the
  resource's conditions/events, referenced source revision and controller logs. Correct the
  cause and reconcile; do not silence by removing the metric.
- `FluxTelemetryMissing`: resource state metrics are absent for five minutes. Check
  kube-state-metrics readiness, custom-resource RBAC, scrape targets and Prometheus health.
- `PlatformReconciliationBudgetBurn`: availability below 99% in both 5-minute and 1-hour
  windows for five minutes. Inspect failing resources and the error-budget dashboard.

Flux 2.10 resource state comes from kube-state-metrics `gotk_resource_info`; controller
latency comes from the PodMonitor. Existing Kubernetes collectors remain enabled.

Alertmanager's default receiver remains local/null: firing alerts are visible in its API/UI
but are not delivered to email, Slack or paging. Configure a reviewed receiver and its
Secret when the owner selects a notification destination. The acceptance test refuses to
exercise failures if an external receiver is configured, preventing unsolicited messages.

## Logs and retention

Loki runs a single monolithic dev instance with a 10 GiB PVC and 72-hour retention (subject
to compaction delay). Its storage is filesystem-based, not an HA or disaster-recovery
backend. StatefulSet PVC auto-deletion is disabled and retention policies are explicit.
Alloy runs unprivileged as a Deployment with no hostPath mounts. Namespace-scoped Roles
permit only pod discovery/log reads in `flux-system` and `monitoring`; no Secret reads or
cloud credentials are granted. Application namespaces require a deliberate allowlist/RBAC
change. Centralized logs can contain application-provided sensitive text: access remains
administrative and log producers must redact secrets before emitting them.

## Acceptance and rollback

Run `scripts/validate.py` for both overlays and every pinned Helm render, and
`scripts/test-observability.py` for real PromQL and alert transition tests. The infrastructure
repository's `scripts/verify-observability.py --config CONFIG` checks private Services,
Flux metrics, rule health, logs, cost metrics and dashboard provisioning. Its optional
`--exercise` creates a dedicated Kustomization pointing at a missing path, observes the
alert in Prometheus and Alertmanager, then restores the empty `applications/dev` path and
waits for resolution. It retains the healthy probe and restores its path even on failure.
No production workload is deliberately interrupted or deleted.

Deploy using a reviewed full Git commit in the IaC `platform.commit` field and a saved
`kube_resources` plan. Do not switch to a mutable branch reference. For rollback of an
existing release, revert the configuration in a new reviewed commit while keeping its
resource names and storage settings. Returning directly to a commit that predates these
releases can cause Flux pruning/uninstall: prepare a retention-preserving rollback first.
No rollback or acceptance procedure automatically deletes cloud infrastructure or PVCs.

References: [Flux metrics](https://fluxcd.io/flux/monitoring/metrics/),
[Prometheus rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/),
[Alloy Kubernetes log source](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.kubernetes/).
