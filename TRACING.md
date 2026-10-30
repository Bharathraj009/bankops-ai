# OpenTelemetry tracing

Dated verification sections below record historical fixture observations, not
current service state or performance benchmarks. For current startup use the
[local runbook](local/README.md).

Tracing uses OpenTelemetry SDK/API dependencies managed by Spring Boot 4.0.8's
BOM and Spring AOP. Explicit instrumentation is used instead of an agent or
automatic HTTP/JDBC instrumentation, so raw URLs, SQL, database parameters,
headers, payloads and exception messages cannot enter spans. No banking service
or repository implementation, transaction boundary, API body, or migration is
changed. Existing Micrometer metrics remain independent.

## Context and spans

Each business HTTP request creates a server span named `http.request`. A valid
W3C `traceparent` supplies the remote parent; missing, invalid or duplicate headers
start a fresh trace. The response includes a `traceparent` containing this server
span's context, which a caller can forward on its next request. Existing
`X-Correlation-ID` behavior is preserved. JSON events within requests include
`trace_id` (32 hex characters), `span_id` (16 hex characters), and `correlation_id`.
The log filter permits only validated identifiers, retaining the existing privacy
allowlist.

Transfer service boundaries create `transfer.create`, `transfer.read`, or
`transfer.fund` child spans. The operation span surrounds transaction completion,
including commit-time failures. Account and transfer repository boundaries create
`db.call` client spans with `db.system.name=postgresql`. These measure repository
calls, not individual wire-level statements. They never inspect SQL, method
arguments, return values, identifiers or amounts. All span names are fixed.
HTTP spans additionally contain only numeric `http.response.status_code`.
Failure status is recorded without exception text, stack traces or events.

Only W3C trace context is supported; vendor `tracestate` and `baggage` are
deliberately neither extracted nor forwarded because they may carry personal
data. Resource attributes contain only `service.name=banking-service`.
New traces are sampled; valid upstream sampling decisions are respected. The
SDK and scopes are local to the application, not registered in a global JVM
singleton. Context/MDC are restored after each scoped call. Error redispatches
reattach the original request context so error-response logs keep the same IDs.
Current banking APIs
are synchronous; arbitrary background executor propagation is not installed.

## Export and failure isolation

The `monitoring` profile now enables asynchronous OTLP/HTTP export to local Jaeger
at `http://localhost:4318/v1/traces`. Other profiles make no export calls unless
`bankops.tracing.otlp.enabled=true` is explicitly configured. The exporter uses
a bounded queue and short timeouts; see [JAEGER.md](JAEGER.md) for setup and limits.
Tests can still attach an in-memory exporter to verify finished spans.
This step does not add an outbound HTTP client: there are no outbound banking
HTTP calls to instrument. W3C extraction/injection is handled by the configured
OpenTelemetry propagator.

Processor start/end/export runtime failures and tracing scope failures are
isolated. Business work executes exactly once, outside tracing setup error
handlers. Its original exception is rethrown unchanged; failures are never
retried by instrumentation. Trace failures do not change balances, postings,
responses or idempotency behavior. Custom processors must not block indefinitely
or mutate business state; catastrophic JVM failures are not recoverable.

## Inspect logs

After rebuilding and restarting Spring Boot, send a request with a newly generated
parent context (do not use banking identifiers):

```powershell
$trace = [guid]::NewGuid().ToString('N')
$parent = [guid]::NewGuid().ToString('N').Substring(0,16)
$correlation = [guid]::NewGuid().ToString()
Invoke-WebRequest http://localhost:8080/api/v1/accounts/not-a-uuid -Headers @{
    traceparent = "00-$trace-$parent-01"
    'X-Correlation-ID' = $correlation
}
# Expected HTTP 400 with diagnostic response headers; no financial changes.
```

Filter JSON console records as described in [LOGGING.md](LOGGING.md):

```powershell
Get-Content backend/banking-service/target/application-console.log |
    Where-Object { $_.StartsWith('{') } |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object trace_id -eq $trace |
    Select-Object '@timestamp', trace_id, span_id, correlation_id, event_type, outcome
```

Existing processes require a rebuild and restart to load new dependencies.
Step 33 runtime verification restarts Spring Boot while preserving its profiles
and the existing database and monitoring containers.
See [OpenTelemetry's Java SDK documentation](https://opentelemetry.io/docs/languages/java/sdk/)
and [Spring Boot 4 observability](https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html).

## Verification — October 15, 2026

The final full isolated PostgreSQL suite passed: **201 tests, zero failures,
errors or skips**. The initial targeted run passed all 10 selected tests. Eight
new tests cover W3C remote parent and forwarded response context, HTTP/transfer/
database hierarchy, JSON trace correlation, bounded attributes and sensitive-data
exclusion, concurrent request isolation, SDK/processor failures, scoped MDC cleanup,
and error redispatch context restoration. Failure tests verify successful commit,
matching retry and insufficient-funds rollback still leave one transfer, two
postings and balances of 90/10.

The first full run exhausted PostgreSQL connections through cached test pools.
The new integration contexts now use two-connection pools and close after their
classes; production pool configuration and existing assertions are unchanged.
The final run includes all existing financial, idempotency, logging and metrics
tests. V1–V5 hashes are unchanged. The disposable database was removed, and the
existing development/monitoring services were left running.

Test output: `backend/banking-service/target/step32-tests.log`.
