# Human approval and read-only execution dashboard

The governance workspace connects proposal review, approved read-only execution
and recorded-result verification through authenticated agent APIs. Each action
requires the appropriate role credential and an explicit confirmation.

## Setup and actual API boundaries

Configure an existing authorized agent independently. The UI never enables an
approval database or remediation feature. In frontend/:

```powershell
$env:BANKOPS_GOVERNANCE_API_TARGET='http://127.0.0.1:8000'
npm run dev
```

Open /approvals or /remediation. The target is a Vite server-only variable (fallback:
investigation target, then monitoring target, then localhost:8000). Never use VITE_*
variables for credentials. Production requires a trusted TLS/same-origin gateway.
The static build does not contain a proxy or embedded role keys.

Development/preview proxies permit only UUID-scoped existing endpoints:

| Method | Agent endpoint |
| --- | --- |
| GET | /remediation/proposals/{id} |
| GET | /remediation/proposals/{id}/execution |
| GET | /remediation/proposals/{id}/verification |
| POST | /remediation/proposals/{id}/approve |
| POST | /remediation/proposals/{id}/reject |
| POST | /remediation/proposals/{id}/execute |
| POST | /remediation/proposals/{id}/verify |

Other paths, methods and query parameters are rejected. There is no proposal-list
API, identity-discovery API or separate audit feed. Load real proposals by UUID
from the existing trusted proposer integration. This dashboard consumes proposals;
it does not add a proposal-creation workflow or fabricate a global proposal queue.
Proposal evidence references are proposer assertions, not persisted incident proof.
Links open current investigation context, not historical evidence for that proposal.

## Credential and role handling

Enter one role credential at a time into a password input. It is retained only in
a private React ref, the input is cleared on submission, and nothing is written to
localStorage/sessionStorage, URLs, source files or logs. Clear credential and records
removes all authorized data and the token from the session. Page reload/app unmount
also discards it. The session survives in-app navigation, so clear it when finished.
Requests send the bearer credential only to the fixed governance API prefix and
refuse redirects. They do not send cookies or credentials to investigation/LLM APIs.

Role selection is a workspace mode, not server attestation or an authorization
claim. The backend determines the real role on every request. Proposer mode is
read-only here; approve/reject/execute/verify require a separately held reviewer
credential. A proposer token placed into reviewer mode still receives 403; 401/403
clear the credential and all authorized records. No backend role requirements are
bypassed. The agent exposes logical proposal_service/human_reviewer principals,
not personal identity, physical human presence, MFA or SSO. Keep reviewer secrets
out of automation and AI systems; this frontend does not introduce those identity
capabilities.

## Deliberate state transitions

Every approve, reject, execute and verify POST requires a native confirmation
showing the exact proposal/action and reason, fixed parameter or verification basis.
A synchronous guard prevents duplicate clicks. No state-changing request is ever
retried automatically. There is no automatic approval, execution or verification.

After any mutation or uncertain response, further mutations are locked until an
explicit read refresh. Reads collect proposal/execution/verification independently;
404 means absent as of that read, while failed lookups remain unavailable and
block execution. Records are timestamped snapshots, not one cross-endpoint atomic
snapshot. HTTP 409 indicates a decision/claim/verification conflict; the user must
read current records. Disabled/unavailable services produce safe errors without
rendering upstream bodies, SQL, credentials or paths.

PENDING proposals can be approved or rejected by the reviewer. Decisions are
terminal. Only APPROVED proposals for CHECK_SERVICE_HEALTH or
REFRESH_INCIDENT_EVIDENCE can execute, bound to the returned approved action and
fixed service=banking-service. Legacy proposal actions may be reviewed but never
executed. No commands, URLs, account identifiers or financial parameters can be
entered. Backend fingerprints, authorization, at-most-once claims and disabled
execution settings remain authoritative.

Execution states RUNNING, SUCCEEDED and FAILED are preserved exactly, including
bounded outcomes such as service_down, evidence_partial or timeout. RUNNING is not
authorization to retry. Verification explicitly sends basis=recorded_execution;
it assesses existing results without another action or fresh collection. A RUNNING
verification can produce a permanent VERIFICATION_INCONCLUSIVE snapshot; the UI
warns before confirmation. Existing verification records cannot be overwritten.
Incident resolution is always NOT_DETERMINED. Success and partial evidence never
establish recovery.

The authorized proposal/execution audit arrays are displayed read-only with server
timestamps. Proposal actors are displayed only as supplied by the contract. Execution
audit has no actor field, so none is invented. Verification exposes a record/time/
human_reviewer, not a separate VERIFIED audit-event feed. No edit/delete action
exists. Immutability is enforced by the existing backend store, not claimed as a
new frontend persistence guarantee.

## Privacy, limits and accessibility

Strict DTO allowlisting validates IDs, fixed actions, statuses, actors, decision
categories, audit order/timestamps, targets and verification resolution. Unknown
fields are discarded. Execution SHA-256 metadata is validated but not displayed.
Responses are streamed with a 32 KiB cap. Read/decision/verification deadlines are
15 seconds; execution is bounded to 75 seconds to accommodate existing backend
limits. Client cancellation cannot prove a backend write did not commit. No action
is resumed after reload; re-enter credentials and read the proposal first.

Native dialogs, labeled forms, keyboard navigation, status/error announcements,
responsive cards, backend audit timelines, theme tokens and reduced-motion support
reuse the existing design system. Every visible control performs a real local or
contract-supported action. No new dependencies were added.

## Isolated verification

The helper testing/governance_agent.py requires --isolated-test-only and binds to
localhost:18062. It creates a private fixture SQLite database under ignored
.cache/step61, generates distinct synthetic role secrets, stores their hashes in
the test app's settings, and writes the raw test secrets only to its ignored
private session manifest for the browser test. They are never printed or put in
source. Browser tracing/video are disabled for these credential-bearing tests.

Only this environment=test fixture enables execution. Its collectors are synthetic
in-memory sources; no live banking, database, monitoring, Airflow or LLM source is
called. Production/default settings remain disabled and unchanged. Actual agent
API authorization, store constraints, approval seals, execution engine and
verification logic run unchanged. The fixture contains pending proposals plus
explicit interrupted/timeout/legacy scenarios prepared through the existing store.

Start with a fresh .cache/step61 fixture directory. Retain or archive old fixture
SQLite files separately before a new lifecycle run; do not reset banking data.

```powershell
# frontend/ terminal 1, existing Python 3.12 environment
../agent/.venv/Scripts/python.exe testing/governance_agent.py --isolated-test-only

# frontend/ terminal 2
$env:BANKOPS_GOVERNANCE_API_TARGET='http://127.0.0.1:18062'
npx vite --host 127.0.0.1 --port 5178 --strictPort

# frontend/ terminal 3
$env:BANKOPS_SYNTHETIC_GOVERNANCE='step61-local-only'
npx playwright test --config playwright.governance.config.ts --grep lifecycle
# Restart ONLY the fixture agent, keeping the same SQLite file/session manifest.
npx playwright test --config playwright.governance.config.ts --grep 'restart persistence'
../agent/.venv/Scripts/python.exe testing/check_governance_fixture.py
```

The audit check targets only that fixture SQLite file. Eight attempted audit
updates/deletes are rejected by existing triggers; every attempt is explicitly
rolled back and a logical database fingerprint confirms no change. Never run this
fixture checker against an operational approval database. Stop the two temporary
processes and remove the generated raw test-secret manifest afterwards.

## Actual results: 2026-10-16 (America/Chicago)

| Check | Result |
| --- | --- |
| Full frontend component/API suite | 74 passed across five files |
| Full desktop/mobile Chromium suite | 22 passed |
| Isolated real-HTTP lifecycle/auth/concurrency | 1 browser test passed |
| Real service restart/persistent records | 1 browser test passed |
| Isolated audit guard checks | 8 rejected attempts, all rolled back |
| Lint, strict TypeScript, formatting | Passed |
| Production build | Passed; governance lazy chunk approximately 6.8 KB gzip |

Screenshots were inspected for desktop, mobile and actual isolated records. Browser
tracing/video remained off for credential-bearing tests. Existing banking,
monitoring and incident frontend regressions were included. Separate banking,
agent and Airflow unit suites were not rerun because their implementations and
contracts were unchanged; the isolated tests exercise the real agent APIs,
authorization, stores, execution and verification mechanisms directly.

Both allowlisted actions completed through explicit approve/execute/verify UI
confirmations. Separate proposer/reviewer custody was tested; a proposer token
spoofing reviewer mode received 403 and the UI cleared it. Competing pending
decisions returned 200/409; competing execution claims returned 200/409. Repeated
execute/verify returned 409. Rejected/legacy proposals could not execute. RUNNING
and timeout records returned inconclusive and failed verification respectively.

Service restart preserved proposal decisions, execution results, verification
records and audit history, without redispatch. The isolated database held eight
proposals, five execution records, four verification records, sixteen proposal
audit events, nine execution audit events and four verification audit events.
All eight audit-mutation attempts were rejected and rolled back with unchanged
logical SQLite contents.

Read-only banking checks before and after matched full-row aggregate fingerprints
and counts for all accounts (3), transfers (2) and ledger entries (4). V1-V5 hashes
match the pre-existing values. No banking records were modified. No production
feature enablement, live remediation, LLM call or Airflow change occurred.

Temporary verification processes were stopped after the checks and the generated
raw test-credential manifest was removed. The synthetic SQLite database was retained
for inspection. Existing development services were left running. A normal dashboard
session requires an independently configured backend; unconfigured/disabled features
remain unavailable. Per-person identity, role discovery, a global proposal listing,
and an API for full verification-audit events remain backend contract limitations.
