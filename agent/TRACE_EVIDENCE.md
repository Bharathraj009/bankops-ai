# Jaeger trace evidence

`GET /evidence/traces` performs one read-only search of recent `banking-service`
traces using Jaeger v3's `GET /api/v3/traces`. There is no polling or background
collection. `/health` does not contact Jaeger, and the existing Prometheus and
incident endpoints retain their behavior. No banking API/database calls, LLMs,
LangGraph, RCA or remediation are added.

```powershell
Invoke-RestMethod http://localhost:8000/evidence/traces | ConvertTo-Json -Depth 12
```

## Environment configuration

All names have prefix **`BANKOPS_AGENT_`**:

| Suffix | Default | Bounds |
| --- | --- | --- |
| `JAEGER_URL` | `http://localhost:16686` | HTTP(S) base URL; no credentials, query or fragment |
| `JAEGER_TIMEOUT_SECONDS` | 5 | Positive finite, maximum 30 seconds |
| `JAEGER_WINDOW_SECONDS` | 300 | 1–3,600 seconds |
| `JAEGER_MAX_TRACES` | 10 | 1–50 |
| `JAEGER_MAX_SPANS_PER_TRACE` | 100 | 1–500 |
| `JAEGER_MAX_TOTAL_SPANS` | 500 | 1–2,000 across all returned traces |
| `JAEGER_SLOW_SPAN_SECONDS` | 1 | Positive finite, maximum 3,600 seconds |

The URL can include a proxy base path. A future agent container sharing Jaeger's
Compose network should use `http://jaeger:16686`. This step does not add it to
Compose or change monitoring services. No caller-supplied service names, trace
IDs, attributes, search expressions or limit overrides are accepted by the API.

The fixed search supplies `query.service_name=banking-service`, RFC3339 start/end
times, bounded `query.search_depth`, and `query.raw_traces=true`. Redirects and
environment proxies are disabled; TLS verification stays enabled. A wall-clock
deadline and HTTP phase timeout bound the request. Responses are capped at
**1 MiB**; oversized responses are rejected rather than exposing incomplete JSON.
Both a single JSON result and newline-delimited gRPC-gateway result envelopes
are supported. There are no retries or follow-up trace fetches.

## Evidence contract

HTTP 200 means collection completed. `status` is `ok`, `missing`, `partial`,
`timeout`, `unavailable`, or `invalid_response`, rather than a banking health
judgment. Evidence includes UTC search bounds, collection timestamp, configured
slow-span threshold, truncation indicator, and bounded trace summaries.

Each trace contains a validated 128-bit hex trace ID, constant service name,
earliest retained span timestamp, duration of the retained span interval, failed
indicator, slow/failed span counts, truncation indicator and safe span evidence.
Each span contains only its validated hex span ID, bounded name, constant service,
UTC start time, duration in seconds, and `failed`/`slow` booleans. Slow means
duration **>= configured threshold**. Failure means OpenTelemetry ERROR status
or the recognized numeric HTTP status attribute in the 500–599 range. HTTP 4xx
alone does not imply server failure; a transfer operation's explicit ERROR still
counts as a failed span. Exception text is never included.

Only resource groups whose sole `service.name` is `banking-service` are retained.
Only completed spans starting inside the requested window and ending no later
than the snapshot end are retained. Other services and out-of-window spans are
excluded. Returned traces are newest-first; spans are ordered by start time and
span ID. Trace IDs are grouping keys, not lookup requests to another endpoint.

Span names are restricted to `http.request`, `transfer.create`, `transfer.read`,
`transfer.fund`, `db.call`; all other names become `other`. Arbitrary service
names, operation names, attributes, SQL, URLs, request bodies, credentials,
account/transfer IDs, baggage, events, links and status messages are not returned
or logged. Only the known numeric HTTP status indicator is inspected to derive
a boolean; no attribute values are copied to evidence.

Client-side caps apply even if the backend ignores its search limit. Hitting a
trace/span quota sets `truncated=true` and `status=partial`; duplicate/malformed
span records are dropped and also make status partial. Summaries describe only
retained banking spans, not necessarily a complete distributed trace. They must
not be treated as complete timing/error counts when limits/filtering apply.
Nonexistent recent data yields `missing` with an empty trace list. This includes
Jaeger v2.22's specific HTTP 404 `No traces found` response; unrelated 404 responses
remain `unavailable`. HTTP failures,
timeouts, malformed payloads and backend errors return bounded states without
raw server or exception messages. Empty/missing evidence never proves health.

## Verification

The complete agent suite passed on October 15, 2026: **156 tests**, with warnings
treated as errors. Tests cover read-only bounded search parameters, privacy
projection and unknown-name redaction, service/window filtering, timing and error
indicators, all output limits, duplicates, JSON/stream envelopes, missing results,
timeouts, redirects, malformed/oversized responses, configuration validation,
and real HTTP endpoint integration against a local fake Jaeger. Existing agent
health, logging, Prometheus and detection tests also pass. Test output is in
ignored `step37-tests.log`.

The final Docker image built successfully. A live, read-only search of the
existing Jaeger returned `missing` with an empty trace list for the recent
five-minute window. The timestamped sanitized result is in ignored
`step37-live-traces.log`. No banking traffic was generated to seed data.
All changes are confined to `agent/`; banking code, V1–V5, Compose and monitoring
services remain unchanged.

Protocol reference: [Jaeger QueryService v3](https://github.com/jaegertracing/jaeger-idl/blob/main/proto/api_v3/query_service.proto).
