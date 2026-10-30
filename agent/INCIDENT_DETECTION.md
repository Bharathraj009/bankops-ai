# Deterministic incident detection

`GET /incidents/detect` collects seven aggregate Prometheus queries and evaluates
four metrics rules. When configured, it also collects bounded Airflow summaries
and evaluates reconciliation/workflow rules; see [Airflow evidence](AIRFLOW_EVIDENCE.md).
Detection performs read-only collection on request. The separate
[LangGraph investigation endpoint](WORKFLOW.md) assembles supporting evidence and
runs local retrieval/optional analysis. Process health remains independent of
external evidence sources.

```powershell
Invoke-RestMethod http://localhost:8000/incidents/detect | ConvertTo-Json -Depth 12
```

HTTP 200 means evaluation completed, not that the system is healthy. Inspect
`state`, `triggered_rules`, individual `rules`, and the embedded `evidence`.
The response includes UTC `detected_at`, evidence evaluation/collection times,
per-metric sample times, observed values and traffic, and applied thresholds.
The rule evaluator is a pure function of evidence, settings and decision time.

## Rules and configuration

All variables have prefix **`BANKOPS_AGENT_`**. Ratios are fractions, not percentages;
latency is in seconds; traffic/failure rates are HTTP outcomes per second over
the existing five-minute window.

| Variable suffix | Default | Meaning |
| --- | --- | --- |
| `INCIDENT_HTTP_ERROR_RATIO` | 0.05 | Trigger `high_http_error_rate` at 5% or higher |
| `INCIDENT_P95_SECONDS` | 1 | Trigger `elevated_p95_latency` at 1 second or higher |
| `INCIDENT_TRANSFER_FAILURE_RATE` | 0.05 | Trigger `high_transfer_failure_rate` at 0.05 failed outcomes/second or higher |
| `INCIDENT_MIN_API_REQUEST_RATE` | 0.1 | Minimum API traffic for error/latency rules |
| `INCIDENT_MIN_TRANSFER_REQUEST_RATE` | 0.1 | Minimum transfer traffic for failure rule |
| `INCIDENT_MAX_EVIDENCE_AGE_SECONDS` | 60 | Maximum snapshot/sample age (1–300 seconds) |

Thresholds and traffic minimums must be positive finite numbers; the HTTP error
threshold must not exceed 1. Comparisons are inclusive: value **>= threshold**
triggers, traffic **>= minimum** permits evaluation. Lower traffic is insufficient
data, even when the observed value is zero. The transfer threshold is an absolute
failure rate; this step does not infer changes relative to a historical baseline.

`banking_unavailable` fires independently of traffic when
`min(up{job="banking-service"})` is **0**. This means at least one configured
banking scrape target is unreachable/unhealthy from Prometheus's perspective;
it does not prove a root cause or that every business endpoint is down. An absent
target or failed Prometheus request is **unknown**, not proof of banking outage.

For detection only, the collector adds two fixed, unlabeled aggregates to its
original five metrics:

- `banking_availability`: `min(up{job="banking-service"})`, restricted to 0 or 1.
- `transfer_request_rate`: total rate of `bankops_transfer_outcomes_total` for
  `job="banking-service",operation="transfer"`.

Transfer traffic includes all transfer HTTP outcomes, including matching retries;
the failure numerator excludes retries and development funding, as before.
Failure outcomes do not imply persisted FAILED transfer records.

## State and data quality

- **incident**: at least one evaluable rule fired. Confirmed incidents take
  precedence over missing evidence for other rules.
- **healthy**: all four rules are healthy, all seven metrics are present, valid
  and fresh, traffic minimums are met, and the evidence snapshot is complete.
- **insufficient_data**: no rule fired and any rule/data requirement cannot be
  evaluated. Idle traffic, missing p95, failed queries, stale/future samples,
  non-finite values, duplicate metrics and invalid units never become healthy.

Rule reasons are bounded codes: `service_up`, `service_down`, `threshold_reached`,
`below_threshold`, `low_traffic`, `missing_or_invalid_evidence`. The full evidence
is included so data gaps remain visible, including a missing success counter
that is not directly consumed by a rule. `triggered_rules` contains only confirmed
incidents; insufficient-data rules are listed individually but do not fire.

All seven queries share one evaluation timestamp and remain bounded, aggregate,
GET-only operations. Existing deadlines, size limits, redirect refusal and
sensitive-data restrictions apply. Raw labels, server messages, credentials and
banking identifiers are never returned or logged. No evidence payload is logged.
See [PROMETHEUS_EVIDENCE.md](PROMETHEUS_EVIDENCE.md) for collector failure behavior.

## Tests

Run the complete agent suite from `agent/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -W error
```

All **118 tests passed** on October 15, 2026. Coverage includes every rule's
trigger boundary, healthy outcomes, configurable thresholds/traffic minimums,
missing/invalid/stale evidence, outage/partial-data precedence, deterministic
output, configuration validation and real HTTP integration for every rule using
a local fake Prometheus. Existing health, logging and evidence tests also pass.
No banking services are needed for the automated tests. Output is recorded in
ignored `step36-tests.log`. All implementation changes are confined to `agent/`.

A live read-only development snapshot returned `insufficient_data`: availability
was 1 (`service_up`), HTTP and transfer traffic were below their minimums, and
idle-window p95 was missing. No rules fired, and the idle service was not falsely
classified healthy. Full timestamped output is in ignored
`step36-live-detection.log`. No banking requests were generated for this check.
