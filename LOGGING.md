# Structured JSON logging

Dated verification sections below record historical fixture observations, not
current service state or performance benchmarks. For current startup use the
[local runbook](local/README.md).

BankOps uses Spring Boot 4's native ECS JSON console encoder, with no additional
logging dependency. Each accepted event includes `@timestamp`, `log.level`,
`service.name` (`banking-service`), `log.logger`, and `message`. ECS nests `log`
and `service` as JSON objects. Spring's startup banner is disabled.

HTTP requests receive an `X-Correlation-ID` response header. Supply exactly one
UUID in that request header to propagate it (normalized to lowercase); missing,
duplicate, oversized or malformed values produce a server-generated UUID. This
header is diagnostic only: it grants no permissions and does not provide
idempotency. Do not put financial identifiers or customer information in it.
The same value appears as `correlation_id` in request and transfer outcome logs.
MDC is established/restored around each servlet dispatch, including error and
async dispatches. It is not automatically propagated to arbitrary background
executor tasks. Existing APIs are synchronous.

Only two bounded `event_type` values are emitted:

- `http_request_completed`: HTTP status, without method, path, query or body.
- `transfer_outcome`: `operation` (`transfer`, `dev_funding`) and `outcome`
  (`completed`, `replayed`, `invalid_request`, `account_not_found`,
  `idempotency_conflict`, `rejected`, `server_error`, `other`).

Transfer HTTP outcomes are observed after service transactions return; completed
and retry responses preserve existing semantics. They do not describe a new
financial event for a matching retry, and rejected requests need not create a
persisted FAILED transfer. Metrics remain independent and unchanged.

Framework/SQL diagnostics are intentionally suppressed: their messages and
exceptions can contain sensitive values. A console appender allowlist also
blocks framework logs even if a logger is enabled at DEBUG. It rejects exception
payloads, unknown structured fields, and MDC other than validated correlation,
trace and span IDs. See [TRACING.md](TRACING.md) for W3C context propagation.
Neither request bodies, paths, account/transfer identifiers, account numbers,
balances, credentials, idempotency keys nor personal information are emitted.
Do not replace this appender with an unfiltered logger or add sensitive fields.
Missing safe diagnostic context causes an event to be dropped rather than
disclosing arbitrary MDC. Logging runtime failures are swallowed outside
financial transactions; they do not change responses, commits or retries.

Start the application normally and redirect its console to a local file:

```powershell
cd backend/banking-service
.\mvnw.cmd spring-boot:run *> target/application-console.log
```

Maven itself prints non-JSON build lines. Select JSON application records before
parsing and filter using PowerShell:

```powershell
$events = Get-Content target/application-console.log |
    Where-Object { $_.StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json }
$events | Where-Object event_type -eq 'transfer_outcome' |
    Select-Object '@timestamp', correlation_id, operation, outcome
$events | Where-Object correlation_id -eq 'your-request-uuid'
$events | Where-Object { $_.log.level -eq 'INFO' }
Get-Content target/application-console.log -Wait
```

Send a diagnostic request without moving money:

```powershell
$id = [guid]::NewGuid().ToString()
Invoke-WebRequest http://localhost:8080/actuator/health -Headers @{'X-Correlation-ID'=$id}
```

With the `monitoring` profile use port **8081** for health. The process already
running from earlier monitoring verification must be restarted to load this
logging configuration; repository changes do not hot-reload that JVM.

See [Spring Boot 4 structured logging](https://docs.spring.io/spring-boot/4.0/reference/features/logging.html#features.logging.structured).

## Verification

The full isolated PostgreSQL suite passed on October 14, 2026: **193 tests,
zero failures, errors or skips**. Six new tests cover JSON fields, correlation ID
propagation/generation and rejection, thread context cleanup, sensitive log
suppression (including explicitly enabled framework diagnostics), bounded transfer
outcomes, and logging failures during committed transfers and retries. The failure
test verifies balances of 90/10, one transfer and two ledger postings after a 10
transfer and matching retry, despite both log observers throwing exceptions.
Existing metrics and financial integrity tests also passed; V1–V5 hashes are
unchanged. The disposable test database was removed. Test output is saved in
`backend/banking-service/target/step30-tests.log`.
