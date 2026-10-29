# Step 50: remediation integration verification

Verification used real loopback HTTP, three separate agent service-process
lifetimes, temporary SQLite storage and independently generated synthetic
proposer/reviewer credentials. Remediation was enabled only in these isolated
test processes. LLM inference remained disabled.

A threaded local HTTP fixture supplied synthetic Prometheus and Jaeger responses;
a temporary JSONL file supplied allowlisted WARN evidence. No SDK mock transport
was used for this integration case: the real collectors issued HTTP requests
to the fixture and the real engine persisted its results.

## Actual outcomes

| Check | Observed result |
| --- | --- |
| APPROVED CHECK_SERVICE_HEALTH | HTTP 200, SUCCEEDED / `service_up` |
| APPROVED REFRESH_INCIDENT_EVIDENCE, all sources available | HTTP 200, SUCCEEDED / `evidence_refreshed` |
| Valid down-service observation | SUCCEEDED / `service_down`; no restart or other action |
| Missing Jaeger source with usable metrics/logs | SUCCEEDED / `evidence_partial` |
| All sources unavailable/missing | FAILED / `source_unavailable` |
| Slow source exceeds engine timeout | FAILED / `timeout` |
| PENDING / REJECTED proposal execution | HTTP 409; no evidence requests |
| No execution credential | HTTP 401; no evidence requests |
| Proposer attempts execution | HTTP 403; no evidence requests |
| Requested action differs from approved action | HTTP 409; no evidence requests |
| Arbitrary service URL or command parameter | HTTP 400; no evidence requests |
| Attempted proposal action edit | HTTP 405 |
| Duplicate execution | HTTP 409; zero additional evidence requests |
| Concurrent execution | One HTTP 200, one HTTP 409; only one query set |
| Actual service-process restart | Successful execution records/audits identical; replays 409 |
| Further restart after failures | All seven execution records identical, including failures; replays 409 |

The isolated source recorded exactly **52 HTTP requests**, all GETs to the two
configured paths `/api/v1/query` and `/api/v3/traces`. No reviewer/proposer bearer
credential reached the source. Health execution uses seven fixed Prometheus
queries; evidence refresh adds one Jaeger query and reads the local JSONL file.
Duplicate/failure replay checks observed no new requests. This verifies no
automatic retry, repair request or fallback execution.

Seven executions produced exactly **14 execution audit events**: RUNNING and
one terminal event each. Audit timestamps matched `started_at` / `completed_at`,
were timezone-aware and chronologically ordered. Audit edits/deletes were
rejected; row counts stayed unchanged. Existing execution tests additionally
verify immutable parameters, modified approval/reviewer seals, legacy-action
denial, cross-instance races, cancellation, audit rollback and default-disabled
production configuration.

## Isolation and banking integrity

The service fixture permits outbound sockets only to its explicitly configured
loopback evidence port. Other connections, subprocess launches and shell calls
are blocked and recorded. **Zero forbidden attempts** occurred. Windows platform
metadata uses the fixture's native API stub so it does not launch version-query
commands. Existing approval-only integration retains its all-connections-denied
guard. This test-only change does not modify production execution behavior.

Development banking tables were inspected before and after using repeatable-read,
read-only PostgreSQL transactions. Full-row fingerprints were calculated inside
the database; raw banking rows were not exported. Both transactions rolled back.

| Table | Before | After | Content fingerprint |
| --- | ---: | ---: | --- |
| accounts | 3 | 3 | unchanged |
| transfers | 2 | 2 | unchanged |
| ledger_entries | 4 | 4 | unchanged |

Banking regression tests used a separate disposable PostgreSQL instance. There
were no development banking writes, production remediation enablement, live LLM
requests, financial API calls, arbitrary URLs or shell actions. Existing banking
code, V1–V5, Compose, monitoring and API contracts are preserved.

## Reproduction and limitations

Final verification on October 15, 2026: **421 agent tests passed** with warnings
treated as errors; **202 banking tests passed**, zero failures/errors/skips,
against disposable PostgreSQL 17. Dependency validation passed. V1–V5 hashes
match the prior baseline. All isolated agent service processes were stopped;
the disposable banking-test container and test-only volume were removed.
Production/default execution remains disabled.

From `agent/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_remediation_process_integration.py -q -s -W error
.\.venv\Scripts\python.exe -m pytest -q -W error
```

The focused test prints an allowlisted `REMEDIATION_PROCESS_VERIFICATION` summary,
without credentials, raw evidence or private paths. Temporary services bind
ephemeral loopback ports and are stopped by fixture cleanup. No production
approval or execution store is configured by this test.

These are actual HTTP/action executions against **synthetic sources**, not a
production outage or production collector-connectivity test. Health means a
fresh Prometheus availability observation; it is not a direct application
health probe. Partial evidence does not establish health or causality. Timeout
can leave source-server work running briefly after client cancellation; the
durable claim still prevents redispatch. A crash or final-audit persistence
failure can leave RUNNING indefinitely, with no automatic recovery or retry.
Filesystem/database owners remain trusted. See [REMEDIATION.md](REMEDIATION.md)
and [APPROVALS.md](APPROVALS.md) for these foundation limits.
