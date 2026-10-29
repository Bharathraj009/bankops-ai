# Prometheus evidence collection

Set `BANKOPS_AGENT_PROMETHEUS_URL` to a trusted HTTP(S) Prometheus base URL
(default `http://localhost:9090`) and optionally
`BANKOPS_AGENT_PROMETHEUS_TIMEOUT_SECONDS` (default 5, positive finite, maximum 30).
A base path such as `/prometheus` is supported. Credentials, query parameters and
fragments are forbidden in the base URL. The URL is omitted from settings repr,
evidence and logs. Environment proxies are ignored, TLS verification remains on,
and redirects are not followed. In a container sharing Prometheus's network use
`http://prometheus:9090`; no Compose integration is added by this step.

Start the agent as documented in [README.md](README.md), then request:

```powershell
Invoke-RestMethod http://localhost:8000/evidence/prometheus | ConvertTo-Json -Depth 8
```

The endpoint performs only five fixed **GET /api/v1/query** requests. It does not
accept PromQL, label selectors or endpoint overrides from API callers. No polling
runs at startup or in the background, and `/health` never contacts Prometheus.
All five queries share one UTC evaluation time and a fixed five-minute window,
and match the existing BankOps Grafana dashboard expressions:

| Evidence name | Unit | Meaning |
| --- | --- | --- |
| `api_request_rate` | requests/second | Banking `/api/v1/` responses |
| `api_error_rate` | ratio, 0–1 | Fraction of responses with HTTP 4xx/5xx |
| `api_latency_p95` | seconds | Histogram-derived p95 response latency |
| `transfer_success_rate` | requests/second | New completed transfer HTTP outcomes |
| `transfer_failure_rate` | requests/second | Invalid, unknown-account, conflicting, rejected, server-error or other transfer outcomes |

Queries filter `job="banking-service"`; transfer queries filter
`operation="transfer"` and exclude matching retries and development funding.
Failed HTTP outcomes do not mean persisted FAILED transfer records. Queries
aggregate away all labels. Success/failure and error numerator zero fallbacks
only use observed counters; absent metrics remain missing. Idle histograms often
produce NaN, which is reported as missing, not zero.

## Evidence contract and failures

HTTP 200 means collection completed, not that all metrics or the banking service
are healthy. Inspect the evidence `status`: `ok` (five valid values), `partial`
(some valid), or `unavailable` (none valid). The payload contains fixed source,
target service and window, UTC `evaluated_at` and `collected_at`, and five metric
objects with `name`, `unit`, `status`, `value`, and `sampled_at`.

Per-metric statuses are `ok`, `missing`, `timeout`, `unavailable`, `query_error`
and `invalid_response`. Failed/missing values and sample times are null.
Finite observed zero remains zero. No automatic retries occur. Five bounded
concurrent requests have HTTP phase timeouts and individual wall-clock deadlines.
Responses are limited to 64 KiB per query. HTTP failures, connection problems,
Prometheus errors/warnings, malformed responses, multi-series/labeled responses,
negative values, invalid ratios and stale/future timestamps are handled without
returning raw exception or backend error text. Upstream cancellation still cancels
collection.

No account IDs, transfer IDs, balances, bodies, credentials, raw metric labels,
request headers or raw Prometheus payloads are exposed, persisted or logged.
Only finite aggregate values from the strict result shape become evidence. The
agent does not call banking APIs, databases, Prometheus administration endpoints,
an LLM, LangGraph or a remediation executor.

## Verification

On October 15, 2026, **61 tests passed** with warnings treated as errors. Coverage
includes exact dashboard query parity, GET-only calls, common evaluation times,
null/missing/non-finite values, partial results, deadline and transport failures,
redirect refusal, malformed/oversized/labeled results, sensitive-data exclusion,
configuration validation, route behavior and health independence. Integration
tests use a real local fake Prometheus HTTP server and a non-listening endpoint;
they require no banking services.

A separate live read-only collection against development Prometheus returned:

| Metric | Actual result |
| --- | --- |
| API request rate | ok, 0 requests/second |
| API error rate | ok, 0 |
| API p95 latency | missing, null |
| Transfer success rate | ok, 0 requests/second |
| Transfer failure rate | ok, 0 requests/second |

Snapshot status was `partial`, as expected during an idle five-minute window.
No banking traffic was generated to fabricate observations. The live snapshot
is recorded in ignored `step35-live-evidence.log`; test output is in ignored
`step35-tests.log`. All implementation changes are under `agent/`; banking code,
V1–V5, Compose and monitoring services are unchanged.

Protocol reference: [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/).
