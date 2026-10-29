# Step 48: approval integration verification

Verification on October 15, 2026 used an isolated loopback Uvicorn service,
an ephemeral listening port, a temporary SQLite file and two independently
generated synthetic role credentials. Only credential hashes were passed to
the service process. No real human credential or production approval database
was used. Test automation simulated the two distinct authenticated roles.

The test starts a real OS process, sends HTTP requests, terminates the process,
starts a new process against the same test database, and compares the complete
proposal responses. It does not merely reconstruct an in-process app object.

## Observed HTTP results

| Check | Actual result |
| --- | --- |
| Proposer creates synthetic proposal | 201, PENDING, server-generated UUID, CREATED event |
| Human-reviewer role reads proposal | 200 |
| Separate reviewer approves first proposal | 200, APPROVED |
| Separate reviewer rejects second proposal | 200, REJECTED |
| Proposer tries approving own proposal | 403; no decision recorded |
| Reviewer tries creating a proposal | 403 |
| Missing credentials on create/decision | 401 |
| Invalid credential | 401 |
| Repeat matching approval | 409 |
| Rejection after approval | 409 |
| Concurrent approval and rejection on third proposal | Exactly one 200 and one 409 |
| Review after actual service-process restart | 200; complete records identical |
| Production environment with default configuration | 503 for proposal creation; approvals remain disabled |

The three synthetic proposals had exactly six audit rows: one CREATED and one
terminal decision for each. Audit timestamps matched proposal creation/decision
timestamps, were timezone-aware, and were chronologically ordered. Database
attempts to edit/delete audit records were rejected and the six rows remained.
Existing approval tests additionally cover state immutability, concurrent app
instances, oversized/malicious input, storage failures and audit-failure rollback.

## No execution or banking changes

The subprocess fixture installs an unconditional guard against outbound socket
connections, subprocess launches and shell commands during service operation.
The successful verification recorded **zero such attempts**. Approval records
intent only; no executor, remediation, banking client or live LLM call was used.

An initial fixture run flagged Python 3.12's Windows platform-version probe
(`cmd /c ver`). This was incidental platform metadata discovery, not remediation.
The fixture now obtains that metadata through the native Windows API instead;
the execution guard was retained and assertions were not weakened. Production
application code did not need a change.

Read-only, repeatable-read transactions captured development table counts and
full-row content fingerprints before and after verification. All matched:

| Development table | Before | After | Content fingerprint |
| --- | ---: | ---: | --- |
| accounts | 3 | 3 | unchanged |
| transfers | 2 | 2 | unchanged |
| ledger_entries | 4 | 4 | unchanged |

No account, transfer or ledger row was created, updated or deleted by approval
verification. Fingerprints were computed inside PostgreSQL; no raw financial
row data was exported. Both snapshot transactions were rolled back. Banking
regression tests used a separate disposable PostgreSQL instance. Development
PostgreSQL, Spring Boot and monitoring services were not restarted or reconfigured.

## Reproduction

Final results: **395 agent tests passed** with warnings treated as errors;
**202 banking tests passed** with zero failures, errors or skips. Dependency
validation reported no broken requirements. V1–V5 hashes match the prior
baseline. The disposable banking-test container and its test-only volume were
removed; all isolated approval service processes were stopped. Approval remains
disabled in default/production configuration. No live inference occurred.

From `agent/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_approval_process_integration.py -q -s -W error
.\.venv\Scripts\python.exe -m pytest -q -W error
```

The first command prints an allowlisted HTTP/status verification summary; no
credentials, request headers or private database paths are printed. Fixtures
stop their own service processes and use pytest temporary storage. To repeat
the full banking suite, select a disposable PostgreSQL instance through the
existing `BANKOPS_TEST_DB_*` environment variables, never development credentials.
See [APPROVALS.md](APPROVALS.md) for configuration and authentication limitations.
