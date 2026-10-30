# Jaeger tracing backend

> For the complete current platform, use the [local runbook](local/README.md).
> The setup below describes the older root Compose/host-run arrangement, with
> different ports and manual database provisioning. Its dated observations are
> historical, not performance benchmarks or a statement that services run now.
> Root Compose requires `BANKOPS_POSTGRES_ADMIN_PASSWORD` and
> `BANKOPS_GRAFANA_ADMIN_PASSWORD`; `.env.example` alone does not provision the
> current migration/runtime identities. See [database setup](database/README.md).
> The root Compose Jaeger image is the upstream image; the passing hosted
> Jaeger scan covers the custom `local/Dockerfile.jaeger` used by the unified stack.

From the repository root:

```powershell
docker compose up -d --no-deps jaeger
```

The pinned Jaeger v2 all-in-one container exposes its UI at
<http://localhost:16686> and OTLP/HTTP ingestion at
`http://localhost:4318/v1/traces`. Both published ports bind only to `127.0.0.1`.
No additional Jaeger ports are published. The default storage is **transient
memory**: traces disappear when Jaeger restarts. Banking data remains in the
existing PostgreSQL volume. This is a local development backend.

Build and start Spring Boot with the existing `dev,monitoring` profiles, using the
database credential setup in [PROMETHEUS.md](PROMETHEUS.md). Reserve bootstrap
does not need to run for tracing. The `monitoring` profile enables
`bankops.tracing.otlp.enabled=true`; other profiles leave export disabled unless
explicitly enabled. `BANKOPS_OTLP_TRACES_ENDPOINT` can override the full OTLP HTTP
trace endpoint (include `/v1/traces`). For a future container-run banking service,
use the Compose address `http://jaeger:4318/v1/traces` instead of host localhost.

The OpenTelemetry exporter version is managed by Spring Boot's existing BOM.
Export runs on the SDK batch worker, with a queue of 1,024 spans, batches of at
most 128, a one-second schedule delay, a two-second HTTP timeout and a three-second
batch export timeout. A full queue drops tracing data. Exporter runtime errors
produce failed telemetry results; failures, connection loss and retries remain
off banking request threads. Financial work never waits for an export or flush.

Generate traffic using existing APIs, then select **banking-service** in Jaeger.
HTTP requests appear as `http.request`, transfer operations as `transfer.create`,
`transfer.read` or `transfer.fund`, and repository calls as `db.call`.
Use an existing transfer detail GET or a matching idempotent retry to inspect
transfer/database spans without moving new money. Allow a few seconds for batching.

Copy `trace_id` from a JSON application event into Jaeger's trace search, or open
`http://localhost:16686/trace/<trace_id>`. The response's W3C `traceparent` also
contains that trace ID. Existing correlation IDs and JSON log fields remain intact.
See [TRACING.md](TRACING.md) for the strict span and log privacy rules.

Jaeger v2.22's query API uses `/api/v3/services` and
`/api/v3/traces/<trace_id>`; the latter returns OTLP trace JSON. Use
`?raw_traces=true` to inspect stored application attributes without Jaeger's
query-time clock-skew warnings/enrichments. Legacy
`/api/services` is not available on this version. Inspect application span
attributes, resource attributes, status messages and events when auditing safety;
there should be no URLs, SQL, identifiers, amounts, bodies, secrets or baggage.

Stop only Jaeger with `docker compose stop jaeger`. Existing PostgreSQL,
Prometheus and Grafana are independent and remain running. Do not use
`docker compose down -v`.

References: [Jaeger getting started](https://www.jaegertracing.io/docs/2.22/getting-started/),
[Jaeger query API](https://github.com/jaegertracing/jaeger-idl/blob/main/proto/api_v3/query_service.proto).

## Actual verification — October 15, 2026

Spring Boot PID 12360 received a graceful console interrupt. After confirming it
exited, the rebuilt application started as PID **20436**, preserving
`dev,monitoring`, disabled reserve bootstrap and the V5 migration target. Existing
PostgreSQL, Prometheus and Grafana containers were not recreated or stopped.
Jaeger UI and OTLP bindings were verified as localhost-only.

| Existing API probe | Actual HTTP response | Jaeger spans |
| --- | --- | --- |
| Account read | 200 | 2 |
| Transfer details read | 200 | 3 |
| Matching transfer retry | 200 | 5 |
| Conflicting key reuse | 409 | 4 |
| Invalid transfer body | 400 | 1 |

All five traces (15 spans) were retrieved from Jaeger's raw query API. The
matching retry contained `http.request` → `transfer.create` → three `db.call`
children. Each trace's server span ID and trace ID matched both response context
and correlated structured JSON events. Example verified trace:
`093685c3678f4109b75f77f21cacc8d6` (historical transient trace; not a persistent evidence link).

Audits passed for bounded span names, resource/attribute allowlists, empty events,
links and exception text, and absent baggage/vendor tracestate. Banking account
and transfer identifiers, account numbers, idempotency keys, synthetic credential/
personal-data probes, bodies and amounts were absent from traces and JSON logs.
No new money movement occurred. Record counts stayed at 3 accounts, 2 transfers
and 4 ledger entries. Total balances and opening balances both remain USD
1,000,000; debits and credits both total USD 1,250. Balance-to-ledger mismatches: 0.

Prometheus target is **UP** and Grafana's data-source health is **OK**. Fresh
read-only/rejected traffic produced finite data in all six Grafana panels:
0.035091 requests/second, 50% deliberate request errors, p95 0.123412 seconds,
zero successful new transfers/second, 0.017545 failed requests/second, and
availability 1. An idle-window p95 initially had no observations; it returned
finite data after fresh scrapes. This is expected histogram behavior.

**202 tests passed**, zero failures, errors or skips, using isolated PostgreSQL.
The new test sends real OTLP batches to a rejecting HTTP receiver and verifies
that a transfer commits once, a matching retry is unchanged, and balances and
double-entry postings reconcile despite failed exports. V1–V5 hashes are unchanged.
The disposable test database was removed. All development and monitoring services
remain running.

Evidence is under `backend/banking-service/target/`: `step33-tests.log`,
`step33-requests.json`, `step33-jaeger-verification.json`, `step33-trace-*.json`,
`step33-monitoring-verification.json`, `step33-app.log` and `step33-app.pid`.
