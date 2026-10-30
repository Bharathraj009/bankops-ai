# Human approval workflow

Real-process, HTTP and banking-data checks for Step 48 are recorded in
[APPROVAL_VERIFICATION.md](APPROVAL_VERIFICATION.md).

The agent now stores typed remediation proposals in its **own SQLite database**.
Approval itself executes no remediation. The separately enabled, read-only
execution engine is documented in [REMEDIATION.md](REMEDIATION.md).
Banking accounts, transfers, ledger, migrations and
monitoring are not accessed or changed by this workflow.

The existing LangGraph ends after evidence assembly and RCA. It has no proposal
or approval tools, and all existing investigation/API response contracts remain
unchanged. A trusted proposer can separately submit an intention for human review.
Approval records a decision. Execution requires a separate reviewer request and
accepts exactly two read-only action types; legacy restart/scale actions are
non-executable.

## Configuration and role separation

The feature is unavailable by default (`503`); no database is created unless
`BANKOPS_AGENT_APPROVAL_DB_PATH` is explicitly set. Provision an existing private
local directory and configure:

| Environment variable | Meaning |
| --- | --- |
| `BANKOPS_AGENT_APPROVAL_DB_PATH` | Absolute local filename ending in `.sqlite3`; no memory/URI/UNC database |
| `BANKOPS_AGENT_APPROVAL_PROPOSER_TOKEN_SHA256` | Lowercase SHA-256 digest of the proposer bearer credential |
| `BANKOPS_AGENT_APPROVAL_REVIEWER_TOKEN_SHA256` | Different lowercase SHA-256 digest of the human-reviewer bearer credential |

Generate **two independent high-entropy secrets** through your secret manager
(e.g. at least 32 random bytes each). Store only their SHA-256 digests in the
server environment. Clients send the corresponding raw secret in
`Authorization: Bearer ...`; tokens must be 32–256 printable ASCII characters
without whitespace. Never put raw credentials into source, commands, reports,
proposal bodies or LLM context. Do not share the human reviewer credential
with an AI, proposer automation or the LLM provider. The application does not
automatically load `.env` files.

The proposer role can create and read proposals but **cannot approve or reject**.
The human reviewer role can read and decide, but cannot create proposals. Roles
are determined from constant-time credential-digest comparisons, never from a
request's claimed actor, status or AI output. Identical role digests are rejected
at configuration validation. Server-assigned audit principals are
`proposal_service` and `human_reviewer`; personal information is not recorded.

The workflow authenticates possession of a human-held credential, not physical
human presence. An operator must keep that credential out of automation. There
is one logical reviewer principal; per-person identity, MFA, SSO, revocation
history and multi-reviewer policies are not implemented. Restart with new digests
to rotate credentials. Use loopback or authenticated TLS ingress; never expose
bearer authentication over untrusted plain HTTP. The model receives no role
credential or approval capability through the graph.

## API contract

Every endpoint requires a valid role bearer credential. Query parameters are
rejected. Request JSON is capped at 4096 bytes; duplicate keys, unexpected fields
and invalid values receive a generic error without echoing input.

| Method and path | Role | Result |
| --- | --- | --- |
| `POST /remediation/proposals` | proposer | HTTP 201, server-generated UUID, PENDING proposal and CREATED audit event |
| `GET /remediation/proposals/{proposalId}` | either | HTTP 200 proposal with current state, decision metadata and ordered audit events |
| `POST /remediation/proposals/{proposalId}/approve` | human reviewer | HTTP 200, terminal APPROVED |
| `POST /remediation/proposals/{proposalId}/reject` | human reviewer | HTTP 200, terminal REJECTED |

Create body:

```json
{"action":"restart_banking_service","evidence_references":["rule.banking_unavailable"]}
```

Action names are a fixed catalog: `restart_banking_service`,
`scale_banking_service`, `investigate_dependency`, plus the read-only actions
`CHECK_SERVICE_HEALTH` and `REFRESH_INCIDENT_EVIDENCE`. Approval never dispatches
an operation; legacy actions remain non-executable. See [REMEDIATION.md](REMEDIATION.md)
for explicit, separately gated execution of the two read-only actions.
There are no commands, arguments, account identifiers, arbitrary target names,
free-text descriptions or execution parameters. Evidence reference values are
the four existing `rule.*` detection identifiers. References are assertions by
the proposer, **not independently persisted proof of an incident or RCA**; a
human must review the corresponding investigation evidence before approval.
The existing RCA's evidence-grounding checks are not altered or bypassed.

Approve/reject body:

```json
{"reason":"reviewed_evidence"}
```

Allowed reason categories are `reviewed_evidence`, `insufficient_evidence`,
`risk_unacceptable` and `alternative_required`. No client can supply actor,
state, proposal ID or timestamps in a body. Responses include `proposal_id`,
`action`, `evidence_references`, `status`, UTC `created_at` / `decided_at`, logical
`created_by` / `decided_by`, `decision_reason` and an ordered `audit` array of
event/actor/timestamp records. Pending decision fields are null. Normal
correlation-ID headers and safe HTTP logs remain unchanged.

Errors are bounded: `400` malformed UUID/body/query; `401` missing/invalid
credentials; `403` wrong role; `404` unknown proposal; `409` already decided;
`413` oversized body; `503` disabled/unavailable/locked storage. There is no
delete or metadata-edit endpoint. Unauthorized attempts cannot mutate state.

## State, persistence and audit integrity

Only `PENDING → APPROVED` or `PENDING → REJECTED` is allowed. Both terminal
states are immutable, including repeated matching decisions (HTTP 409). Every
proposal starts pending, including those suggested by automation.

SQLite `BEGIN IMMEDIATE` serializes writers across app instances; a guarded
decision transaction checks the pending state, applies the decision and reads
the resulting report before committing. Database triggers atomically record
creation and decision audit events. An audit failure rolls back the decision.
Readers use one snapshot so proposal status and audit cannot disagree under a
concurrent decision. No automatic retries are performed.

Database checks/triggers also reject terminal-state changes, metadata changes,
null or invalid decision metadata, proposal deletion, audit edits/deletions and
inconsistent audit inserts. Audit records are minimal and bounded to creation
plus one decision. They do not contain bearer secrets, evidence payloads or
personal data. Rejected authorization attempts are not stored in this audit.

Keep the database and its directory private to the service account; trust the
operator-selected local path and its ancestors. Symlinks/reparse points are
rejected on initialization. Filesystem owners can bypass application controls
or replace/drop database schema: this is not tamper-proof or signed storage.
Use proper ACLs, backups and secure deployment. No file path is accepted from
an API caller. The store uses a five-second SQLite busy timeout; storage failures
fail closed without exposing paths/SQL and do not disable existing health or
investigation APIs. Database files/journals are ignored by Git.

## Tests

Tests use separate temporary SQLite files, actual FastAPI HTTP requests and
independent application/store instances. They cover both decisions, persistence,
human-role separation, body/privacy validation, terminal-state guards, concurrent
conflicting decisions, atomic audit rollback, immutable audit, configuration and
storage failures, and proof that approval performs no external call or execution.

## Verification

October 15, 2026: **394 agent tests passed**, with warnings treated as errors,
including **32 approval tests**. The existing banking suite passed **202 tests**,
zero failures/errors/skips, against disposable PostgreSQL 17; its container was
removed. Dependency validation passed. V1–V5 hashes match the prior baseline.
No live inference, remediation, banking-data modification or monitoring change
was performed. The approval feature remains unconfigured and unavailable by
default; tests use isolated temporary SQLite storage and synthetic credentials.
