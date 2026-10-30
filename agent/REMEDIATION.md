# Approved read-only execution

Actual loopback HTTP, failure and process-restart verification is recorded in
[REMEDIATION_VERIFICATION.md](REMEDIATION_VERIFICATION.md).

Execution is **disabled by default**. The engine supports exactly `CHECK_SERVICE_HEALTH` and `REFRESH_INCIDENT_EVIDENCE`. It never
restarts/scales a service, executes a shell, runs an LLM, or changes banking data.
The legacy proposal action names remain supported by approval APIs for backward
compatibility, but they are **not executable**.

## Enablement and endpoints

First configure the isolated approval store and separate proposer/reviewer
credentials as described in [APPROVALS.md](APPROVALS.md). Execution additionally
requires `BANKOPS_AGENT_REMEDIATION_ENABLED=true`. Leave it unset/false outside
an explicitly approved environment. `BANKOPS_AGENT_REMEDIATION_TIMEOUT_SECONDS`
defaults to 15, with bounds greater than zero and at most 60 seconds.

Use the existing create and human approve endpoints to create an immutable
proposal with action `CHECK_SERVICE_HEALTH` or `REFRESH_INCIDENT_EVIDENCE` and
the existing bounded evidence references. These actions have exactly one
server-defined parameter: **`service=banking-service`**. There are no caller
configurable URLs, commands, arguments, hosts, accounts or financial values.
This fixed parameter is part of the safe action's definition, even though the
existing proposal response shape is unchanged.

Endpoints:

| Endpoint | Authorization | Behavior |
| --- | --- | --- |
| `POST /remediation/proposals/{proposalId}/execute` | Human reviewer only | Claim once and run the approved read-only operation |
| `GET /remediation/proposals/{proposalId}/execution` | Either valid approval role | Read execution status and audit, including when execution is disabled |

Execution request:

```json
{"action":"CHECK_SERVICE_HEALTH","parameters":{"service":"banking-service"}}
```

The action must exactly match the approved proposal; parameters must exactly
match the server-defined target. Extra fields, arbitrary URLs and shell content
are rejected. Existing body-size, generic validation-error and authentication
controls are reused. The proposer cannot approve or execute its proposal.

Responses contain `proposal_id`, `action`, `parameters`, `status`, `started_at`,
`completed_at`, `outcome` and ordered execution `audit` events. A completed
operation returns HTTP 200 even if its recorded status is FAILED. `401/403`
mean authentication/role rejection, `400` invalid input, `404` unknown record,
`409` unapproved/unsupported/changed/already-claimed proposal, and `503` disabled
or unavailable storage. Safe error text never exposes SQL, credentials or paths.

## Approval binding and persistence

Legacy SQLite tables/rows/check constraints/audits are preserved. Additive
`read_only_proposals` / `read_only_audit` tables hold new safe-action proposals
behind the same existing approval APIs. Existing IDs are protected against
cross-table collisions. New approval bindings, execution records and execution
audit tables are stored in the same independent approval database, never in
banking PostgreSQL or Flyway migrations.

Human approval atomically seals a SHA-256 fingerprint of the complete proposal,
its approval metadata and audit, and the fixed parameters. The execution claim
requires APPROVED state, the authorized human-reviewer principal, the matching
decision audit/timestamp and matching fingerprint. PENDING, REJECTED, legacy
actions, absent seals or changed content cannot execute. Normal database
triggers already reject proposal edits; the fingerprint adds a second check.
It is an integrity binding, not a signature or protection against a malicious
filesystem/database owner. The existing trusted-directory and credential
custody requirements remain essential.

`BEGIN IMMEDIATE` and a unique proposal execution key atomically reserve
RUNNING state before dispatch. Start and completion audit records are generated
by triggers in the same transactions as their state updates. Only RUNNING can
transition to SUCCEEDED or FAILED; terminal records, binding rows and audit
history cannot be edited/deleted through ordinary database operations. Audit
insert failure rolls back its matching state update.

Claims survive process restarts. Duplicate/concurrent requests receive 409,
including after failure or timeout. There are **no automatic retries**. A crash
after claiming, cancellation during claim, or failed final audit persistence
can leave RUNNING indefinitely. This deliberately fails closed: there is no
automatic release, re-execution, stale-claim cleanup or recovery endpoint.
The engine provides durable at-most-once dispatch, not guaranteed execution
or distributed exactly-once completion. Completion failure never authorizes
another dispatch.

## Actual operations and safe results

- **CHECK_SERVICE_HEALTH:** reuses the existing fixed Prometheus detection
  queries and freshness validation for `banking_availability`. A valid up/down
  observation yields SUCCEEDED with `service_up`/`service_down`. A down service
  is an observation, not an action failure. Missing/invalid evidence yields
  FAILED / `source_unavailable`. This is a scrape-availability check, not a new
  direct banking health URL call.
- **REFRESH_INCIDENT_EVIDENCE:** reuses the existing read-only investigation
  orchestration (Prometheus, Jaeger, JSONL) without entering the LLM graph.
  Complete/partial evidence yields SUCCEEDED with `evidence_refreshed` or
  `evidence_partial`; no usable evidence yields FAILED / `source_unavailable`.

Only startup-configured evidence collectors are used, with their fixed request
paths and existing privacy/window/result-size limits. No URL can be supplied by
an API caller, proposal or model. Only bounded outcome categories are persisted;
raw evidence, identifiers, messages and exception text are not added to execution
records. Unexpected handler errors yield FAILED / `internal_failure`; timeouts
yield `timeout`, and cancellation after claim attempts to persist `cancelled`.
Timeouts do not forcibly interrupt a stalled OS worker-thread read, but claims
remain consumed. No financial or infrastructure-changing operation is available.

Existing LangGraph and investigation response contracts are unchanged. The graph
does not gain an execution tool/node or reviewer credentials. Explicit authorized
API requests are the only new execution entry point. Approval alone never
dispatches anything.

## Tests

Tests use temporary SQLite files, synthetic credentials/evidence and mocked
HTTP transports. Coverage includes both handlers, authorization, exact action
and parameter matching, pending/rejected/legacy denial, modified approval
bindings, cross-instance concurrency, restart persistence, timeout/failure/
cancellation, atomic audit rollback, immutable execution data, additive legacy
database upgrade, read-only GET requests, and disabled production defaults.

## Verification results

October 15, 2026: **420 agent tests passed**, with warnings treated as errors,
including **25 execution tests** and the existing approval/process-restart
integration tests. Approval binding and execution audit failures rolled back
their matching state changes; concurrent requests dispatched once. Source
exceptions, absent evidence, timeouts and cancellation produced bounded failed
outcomes. Modified content/reviewer audit, wrong actions/parameters, legacy
actions and unauthorized roles were denied before dispatch.

The banking suite passed **202 tests**, zero failures/errors/skips, against
disposable PostgreSQL 17. Its container and test-only volume were removed.
Dependency validation passed and V1–V5 hashes match the baseline. No live LLM,
shell action, banking API write, account/transfer/balance/ledger modification or
monitoring change was performed. New handler executions used synthetic evidence
and mock transports. Production/default execution remains disabled.

Post-execution verification is documented in [POST_REMEDIATION_VERIFICATION.md](POST_REMEDIATION_VERIFICATION.md).
