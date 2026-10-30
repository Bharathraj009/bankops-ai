# Post-remediation verification (Step 51)

Verification assesses the recorded execution, not whether an incident is resolved.
It supports both CHECK_SERVICE_HEALTH and REFRESH_INCIDENT_EVIDENCE. No action,
collector, LLM, shell command, banking API or financial write is dispatched.
Existing execution records contain bounded outcome codes rather than evidence
snapshots; this limitation is explicit rather than filled with new assumptions.

## Contract and authorization

With the existing isolated approval store and role credentials configured:

- POST /remediation/proposals/{proposalId}/verify requires the human reviewer
  credential and JSON `{"basis":"recorded_execution"}`. Returns 201 once.
- GET /remediation/proposals/{proposalId}/verification allows either approval
  role and returns the immutable record, including after a restart.
- Duplicate/concurrent verification returns 409; absent execution/verification
  returns 404; malformed input 400; unauthorized requests 401/403; unavailable
  storage 503. The existing bounded request parsing and safe errors apply.

The response includes proposal_id, status, reason, verified_at (UTC), basis,
execution_sha256 (digest of the assessed execution including its audit), and
incident_resolution, which is always NOT_DETERMINED. It contains no raw evidence,
credentials, personal information or banking values.

| Recorded observation | Verification status |
| --- | --- |
| Valid terminal success with action-compatible outcome and audit/seal | EXECUTION_SUCCEEDED |
| Valid terminal failure (including timeout/unavailable/cancelled) | EXECUTION_FAILED |
| RUNNING execution or inconsistent binding/audit/outcome | VERIFICATION_INCONCLUSIVE |

A valid `service_down` result verifies that the health check executed successfully;
it does not indicate recovery. `evidence_partial` verifies a completed collection
with limitations. Neither establishes that an incident is resolved. Missing raw
evidence precludes independently checking the historical service observation.
Malformed persisted records fail closed with 503 rather than inventing a result.

## Persistence, failures and limits

Additive SQLite tables execution_verifications and verification_audit share the
independent approval store. A single BEGIN IMMEDIATE snapshot validates the human
approval fingerprint, exact action, execution fingerprint, ordered audit and
timestamps, then commits one immutable verification plus its VERIFIED audit event.
The proposal primary key arbitrates concurrent writers across service instances.
Database triggers reject updates/deletes to verification records and audit.
Original proposals, executions and their audit history are unchanged.

No network I/O occurs in verification, so provider timeouts cannot cause new
requests or action retries. Recorded timeouts remain EXECUTION_FAILED. SQLite
lock waits are bounded by the existing five-second connection timeout; errors
roll back and return 503. A crash before commit leaves no partial record; after
commit the same record is readable on restart. A RUNNING execution may finish
later, but its already-created inconclusive verification remains the historical
snapshot and cannot be overwritten. Review the execution separately.

Fresh evidence collection is intentionally not supported by this endpoint: it
is unnecessary for checking the recorded execution and would not prove what
happened historically. Requests for fresh collection, URLs, commands or extra
parameters are rejected. Authorized investigators can use the existing read-only
investigation endpoints separately; those observations do not alter verification.
Remediation execution remains disabled by default, including production. Recorded
verification does not require re-enabling execution. Without approval configuration,
the endpoint is unavailable. No banking code, migrations or monitoring changed.

## Verification results

Results are recorded below after the complete test run. Tests cover both actions,
all failure outcomes, RUNNING and inconsistent records, reviewer authorization,
missing data, retries, immutable storage, atomic audit rollback, concurrent
independent connections, and restart persistence. The real loopback integration
verifies seven recorded executions across process restarts with zero additional
source requests, unchanged execution records, and one audit event per verification.

Final automated results:

- Agent full suite: **438 passed**, warnings treated as errors (91.99 seconds).
- Banking full suite: **202 passed**, zero failures/errors/skips, isolated
  PostgreSQL 17 container (BUILD SUCCESS). Test container and volume removed.
- Dependency check: no broken requirements.
- Real-process integration: seven immutable verification records and seven
  verification audit events survived an additional service restart; duplicate
  verification returned 409, original execution responses remained identical,
  and verification generated zero additional evidence-source requests.
- Concurrent verification: four independent store connections produced one
  success and three duplicate rejections. Injected audit-write failure rolled
  back the entire verification. Database update/delete attempts were rejected.
- V1–V5 SHA-256 checksums match the pre-existing values. Banking code and
  monitoring configuration were not changed. No development banking data was
  accessed or modified by this step; banking tests used only isolated PostgreSQL.

Limitations: these results verify recorded execution outcomes, not historical
source accuracy or incident resolution. No live remediation or provider calls
were made. No fresh-evidence authorization mechanism is added: fresh collection
requests are rejected by this recorded-only contract.
