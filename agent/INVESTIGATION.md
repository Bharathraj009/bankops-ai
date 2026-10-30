# Unified incident investigation

`GET /incidents/investigate` assembles an on-demand evidence report from the
seven-query Prometheus detection snapshot, optional Airflow summaries, Jaeger
traces and a trusted local JSONL source. Metrics/detection and supporting-source
collection run concurrently. The GET endpoint returns evidence and correlations;
the separate [workflow POST](WORKFLOW.md) adds LangGraph orchestration, local
retrieval and optional validated analysis. Query parameters receive HTTP 400;
unsupported methods receive HTTP 405.

## Response contract

HTTP 200 returns structured evidence even when dependencies are unavailable:

| Field | Meaning |
| --- | --- |
| `started_at`, `completed_at` | UTC investigation timestamps |
| `evidence_mode` | Operational evidence or the separate synthetic-demo profile |
| `evidence_status` | `complete`, `partial`, or `unavailable`; independent of incident status |
| `detection.state` | Existing `healthy`, `incident`, or `insufficient_data` decision |
| `detection.detected_at` | Rule evaluation timestamp, immediately after metrics collection |
| `detection.triggered_rules` | Existing bounded rule IDs; empty when none triggered |
| `detection.rules` | Each rule's state, reason, observation, threshold and minimum traffic |
| `detection.evidence` | Timestamped Prometheus metrics, units, individual statuses and snapshot status |
| `traces` | Existing timestamped Jaeger evidence with sanitized trace/span summaries, source status and truncation |
| `logs` | Existing timestamped WARN/ERROR evidence with source status and truncation |
| `observed_facts` | Counts of returned traces, failed traces, slow spans, log events, WARNs and ERRORs |
| `correlations` | Exact diagnostic-ID groups described below |
| `possible_explanations` | Always `[]`: causal explanations are not assessed at this stage |

Evidence is `complete` only when all three source statuses are `ok`. Otherwise,
it is `partial` if any metric is `ok` or any trace/log event was returned, and
`unavailable` if none was returned. A valid zero-valued metric counts as an
observation. `missing` and `not_configured` remain explicit in their source
objects; absence does not become a healthy observation. Completeness describes
collection, not freshness or health: the existing detector independently checks
freshness, validity, traffic and thresholds. Partial metrics can confirm an
incident while other rules remain insufficient-data. Missing supporting traces
or logs do not invalidate a metrics decision, including a healthy one.

For example, a report may contain `detection.state="incident"`,
`detection.triggered_rules=["high_http_error_rate"]`,
`evidence_status="partial"`, `traces.status="timeout"` and
`logs.status="not_configured"`. It reports the threshold observation, without
claiming why the HTTP error rate increased.

## Correlation and interpretation

Each correlation contains `trace_id`, `correlation_id`, `trace_present`, and
`log_event_indexes` (zero-based indexes into `logs.events`). Events are grouped
by the exact pair of available validated IDs. Missing IDs remain null; events
with neither ID have no group. `trace_present` is true only when that exact
trace ID appears in returned Jaeger evidence. Matching correlation IDs group
log events but do not manufacture trace links. No timestamp-based fuzzy match,
financial identifier, or request path is used.

Correlation establishes shared diagnostic identifiers, not causality. Counts
refer only to the bounded returned sample, not total traffic, total failures,
or exhaustive trace coverage. Collector windows may differ and snapshots are
not atomic. The thresholds describe symptoms, not a root cause. Empty evidence
and absent explanations are never filled with guesses.

## Failure isolation, limits and privacy

An unexpected source exception is replaced by that source's `unavailable`
evidence, without exception text or filesystem paths. Remote collectors retain
their native timeout/error statuses. Orchestration adds a deadline of the
configured remote timeout plus one second and a five-second log deadline;
expiration of these outer deadlines yields `unavailable`. Timed-out file work
runs in a worker thread and cannot forcibly interrupt a stalled OS read.
Request cancellation propagates rather than generating a misleading report.

All existing environment configuration, field allowlists, aggregate-only
metrics, time windows, byte caps, trace/span counts and log event limits apply
unchanged. There are at most as many correlation groups and index references
as returned log events (maximum 500). No raw messages, stack traces, arbitrary
span attributes, account/transfer IDs, credentials, bodies or personal data are
added to reports or logs. The endpoint never accepts sources, paths, PromQL,
service names or other collection parameters from a caller.

Logs are disabled unless explicitly configured. Current banking safe events
are INFO and are excluded from WARN/ERROR evidence, so healthy metrics with
missing log support commonly produce `evidence_status="partial"`.

See [INCIDENT_DETECTION.md](INCIDENT_DETECTION.md),
[PROMETHEUS_EVIDENCE.md](PROMETHEUS_EVIDENCE.md),
[TRACE_EVIDENCE.md](TRACE_EVIDENCE.md), and [LOG_EVIDENCE.md](LOG_EVIDENCE.md)
for source configuration and detailed limitations.

## Verification

October 15, 2026: **208 agent tests passed**, with warnings treated as errors.
Investigation coverage includes healthy/incident/insufficient-data decisions,
partial metrics, missing support, independent and total source failures,
upstream HTTP errors/timeouts, exact and absent correlations, privacy, result
limits, concurrent collection, deadlines, and cancellation. HTTP integration
uses the actual collectors with mocked HTTP transports and temporary JSONL.
Existing collectors also retain their real local HTTP server integration tests.
Dependency validation reported no broken requirements.

The existing banking regression suite passed **202 tests**, zero failures,
errors or skips, against disposable PostgreSQL 17. The test container was
removed. V1–V5 hashes match the prior baseline. No banking source, migrations,
Compose or monitoring configuration changed; development services were not
restarted or reconfigured.
