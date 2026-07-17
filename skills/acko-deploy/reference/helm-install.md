# Helm install — chart variants and OTel wiring

ACKO ships as an OCI Helm chart bundling operator + webhook + Cluster Manager UI (`api` + `web`), all enabled by default. cert-manager must be installed first (provisions the webhook TLS cert):

```bash
helm repo add jetstack https://charts.jetstack.io && helm repo update jetstack
helm install cert-manager jetstack/cert-manager -n cert-manager \
  --create-namespace --set crds.enabled=true --wait

helm install acko oci://ghcr.io/aerospike-ce-ecosystem/charts/aerospike-ce-kubernetes-operator \
  -n aerospike-operator --create-namespace
```

## UI backend / database

The UI `api` pod stores connection metadata (not Aerospike data). Default backend is embedded **SQLite** on a 1Gi PVC; the chart **never deploys PostgreSQL**. UI web frontend listens on 3100 (`kubectl port-forward svc/acko-aerospike-ce-kubernetes-operator-ui-web 3100:3100`).

SQLite is single-writer, so the chart pins `ui.replicaCount=1` and **fails the install if raised** — use external PostgreSQL for a multi-replica UI.

## Install variants

| Goal | Flags |
|------|-------|
| Operator only, no UI | `--set ui.api.enabled=false --set ui.web.enabled=false` |
| External PostgreSQL (HA) | `--set ui.database.type=postgresql --set ui.database.postgresql.databaseUrl="postgresql://..."` (or `...existingSecret`) |
| CRDs managed separately (GitOps) | `--set crds.install=false` |

## OpenTelemetry export (operator)

Off by default; needs **both** `observability.otel.enabled=true` AND a non-empty `observability.otel.endpoint` (either alone is inert / fails rendering). Exports **OTLP/gRPC only** — scheme-less `host:port` is normalized to `http://`, so pass `https://` for a TLS collector. With `networkPolicy.enabled`/`cilium.enabled`, the chart auto-adds the collector egress rule (`observability.otel.collectorPort`, default `4317`). The chart never deploys a collector. See **acko-operations** for runtime enable/verify.
