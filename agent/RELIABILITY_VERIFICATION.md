# Step 52: remediation audit and reliability verification

This step adds regression coverage without changing execution behavior or banking
code. Review covered APPROVALS.md, APPROVAL_VERIFICATION.md, REMEDIATION.md,
REMEDIATION_VERIFICATION.md and POST_REMEDIATION_VERIFICATION.md, plus the store,
engine, verification and real-process integration tests.

## Isolated lifecycle verification

`tests/test_reliability_process_integration.py` runs three separate agent process
lifetimes with a temporary SQLite database, synthetic role credentials and an
independent loopback HTTP evidence server. No live provider or banking API is
called. Only fixed configured evidence GET paths are accessible to the child
process; its audit hook rejects other outbound connections and commands.

Actual targeted result: **1 passed in 17.53 seconds**. It produced three execution
records, three verification records, five execution audit events, three verification
audit events, and exactly **22 read-only source requests** (7 health, 8 evidence
refresh, 7 health for the injected completion failure). Subsequent verification,
duplicate submissions and restarts produced zero additional source requests.

| Boundary | Observed result |
| --- | --- |
| PENDING safe-action proposal | Execution 409; verification 404 |
| Human approval | APPROVED with preserved decision audit |
| Concurrent approval (three requests) | One 200, two 409 |
| Concurrent execution (three requests, each action) | One 200, two 409; one query set |
| Successful health/evidence execution | SUCCEEDED, original audit preserved |
| Proposer/unauthenticated approval or verification | 403/401 |
| Rejected proposal | Conflicting approval and execution 409; verification 404 |
| Injected verification audit-write failure | 503; no partial verification; execution unchanged |
| Injected terminal execution audit-write failure | 503; durable RUNNING claim, no false terminal audit |
| Restart after either storage failure | Original execution and audit identical |
| Concurrent verification (three requests per execution) | One 201, two 409 |
| Incomplete execution verification | VERIFICATION_INCONCLUSIVE |
| Successful execution verification | EXECUTION_SUCCEEDED; incident_resolution NOT_DETERMINED |
| Further restart with execution disabled | Records unchanged; execute 503; verification replay 409 |
| Immutable history | UPDATE/DELETE rejected across all seven stage/binding/audit tables |
| Audit chronology | Approval, execution and verification timestamps ordered |

The previously uncovered boundary was loss of the terminal execution/audit commit
followed by cross-process verification. Deterministic trigger fault injection
confirmed the existing at-most-once design behaves conservatively; no runtime fix
or weakened assertion was needed. The test also connects concurrent requests and
all-stage audit checks into one complete lifecycle rather than testing each stage
only in isolation.

`EXECUTED` and `VERIFIED` describe workflow stages, not new proposal statuses.
Proposal states remain PENDING/APPROVED/REJECTED; execution and verification have
separate immutable histories and their own existing status vocabulary.

## Safety and remaining limitations

Only CHECK_SERVICE_HEALTH and REFRESH_INCIDENT_EVIDENCE are executable, with exact
server-defined service parameters. Existing regression tests reject legacy actions,
modified approval bindings, arbitrary URLs/commands/parameters, unauthorized roles,
and missing/invalid data. Timeout, unavailable and cancelled execution outcomes
remain failures; no automatic dispatch retry or incident-resolution claim is made.
Full-suite results include those existing regressions.

A dispatch whose completion could not be committed stays RUNNING indefinitely.
Restart recovers visibility, not automatic completion or redispatch. Its verification
is a permanent historical inconclusive snapshot. The test injects database failures
at the write boundary; it does not simulate power loss or filesystem corruption.
SQLite transactions protect atomicity; database/filesystem administrators remain
trusted. Synthetic services verify real HTTP behavior, not production recovery.

Verification checks recorded execution, not historical source accuracy. It never
collects fresh evidence or claims incident recovery. New proposal POSTs have no
idempotency contract and create independent proposals; duplicate decisions,
execution and verification for the same proposal are rejected. Role authentication
uses separate pre-provisioned shared credentials, not individual human identities.
Production execution and inference remain disabled by default. Existing LangGraph,
API response contracts, financial code, Flyway migrations and monitoring are
unchanged. Only the disposable test banking database is written by tests.

## Reproduction

From agent/:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reliability_process_integration.py -q -s -W error
.\.venv\Scripts\python.exe -m pytest -q -W error
```

Run the banking suite with the existing BANKOPS_TEST_DB_* variables pointed to a
disposable PostgreSQL database. Development data is checked only through read-only
aggregate counts and row-content digests; no banking rows or credentials appear
in the report. Final suite results and before/after checks follow below.

## Final actual results

- Complete agent suite: **439 passed**, warnings treated as errors, 128.69 seconds.
- Complete banking suite: **202 passed**, zero failures/errors/skips; BUILD SUCCESS,
  1 minute 47 seconds, disposable PostgreSQL 17. Container and test volume removed.
- Dependency validation: no broken requirements.
- V1–V5 SHA-256 checksums unchanged from the prior baseline.
- All isolated service processes were stopped by fixture cleanup.
- No runtime behavior changes were necessary; this step adds one end-to-end
  regression test and documentation. Production-disabled defaults are preserved.

Read-only development snapshots before and after the verification were identical:

| Table | Rows before / after | Row-content MD5 before / after |
| --- | --- | --- |
| accounts | 3 / 3 | df772bdf0304dc65296d25700ea38d41 |
| transfers | 2 / 2 | 73959676babf273b756172c65dfde71d |
| ledger_entries | 4 / 4 | c1904307e418d06e80aa85a3a4f9817e |

Each fingerprint hashes ordered per-row JSON digests inside a read-only repeatable
read transaction. These comparisons confirm the observed table contents remained
unchanged; they are not a backup or a cryptographic audit guarantee. No accounts,
transfers or ledger rows were created, deleted or updated in development.
