# Local Airflow runtime verification — Step 55

## Runtime and isolation

`airflow/compose.yaml` is a separate Compose project named bankops-airflow. It
reuses the Step 54 Airflow **3.3.2 / Python 3.12** dependency configuration and
reconciliation/DAG modules. The root banking/monitoring Compose file is unchanged.
An unrelated Airflow 3.1.7 project was already running outside this repository;
it was inspected for its LocalExecutor approach and left unchanged.

Only two new services are needed:

- airflow: `airflow standalone` runs API, scheduler, DAG processor, triggerer and
  LocalExecutor processes in one container. One task slot; no Redis, Celery workers
  or distributed executor. SimpleAuth is development-only and authentication stays on.
- airflow-metadata: separate PostgreSQL 16 database, no published host port, with a
  named persistent metadata volume. Logs and preseeded local authentication also
  have separate persistent volumes. Banking PostgreSQL is not the metadata store.

UI: **http://127.0.0.1:18081**, username **localadmin**. Windows refused port 8081,
so verification used 18081. Only loopback is bound. Credentials are generated into
ignored airflow/.env.local or supplied through environment variables. No password
is printed or embedded in DAG code. Startup pre-seeds SimpleAuth's password file
so it does not generate/print a credential. The metadata URL and banking conninfo
are built in memory with proper escaping. Local API helper scripts disable proxies
and never print tokens. Docker/host administrators can access environment secrets;
this local development authentication is not a production deployment model.

## Read-only banking role

`runtime/provision.py` provisions bankops_reconciliation with LOGIN, NOSUPERUSER,
NOCREATEDB, NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS and no role memberships.
It grants CONNECT, schema USAGE, and SELECT only on accounts, transfers,
ledger_entries and flyway_schema_history. Its default_transaction_read_only is on.
The transaction refuses elevated or inherited rights, schema CREATE or banking
schema table INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER privileges, including PUBLIC grants.
An incompatible existing role is rejected rather than silently trusted.

No banking table or migration is changed. Role/grant configuration is the only
banking database administration performed. Role SQL is sent through stdin with
captured errors; neither password arguments nor raw errors are printed. Repeated
provisioning preserves locally generated credentials. Do not delete the credential
file or change metadata secrets casually: PostgreSQL initialization environment
variables do not rotate the password of an already initialized metadata volume.

Verification confirmed SELECT on all four tables and no write privileges. Even
with transaction_read_only explicitly off, a zero-row DELETE was denied by ACL
and rolled back. No affected rows were possible in that denial probe.

## Start, inspect and stop

From repository root (Python 3.12 plus the core reconciliation dependencies installed):

```powershell
.\airflow\.venv\Scripts\python.exe airflow/runtime/provision.py
docker compose -f airflow/compose.yaml --env-file airflow/.env.local up -d --build
.\airflow\.venv\Scripts\python.exe airflow/runtime/inspect_local.py
.\airflow\.venv\Scripts\python.exe airflow/runtime/verify_run.py --trigger-once
# Inspect the existing verification run without creating another:
.\airflow\.venv\Scripts\python.exe airflow/runtime/verify_run.py
```

The banking root Compose stack must already be running, with its bankops-ai_default
network and bankops-ai-postgres-1 container. The role provisioner intentionally
supports this local layout only. Read the UI password privately from your ignored
local configuration or secret manager; never paste credentials into a report.

verify_run.py persists the run identifier in ignored .local-run.json before trigger
submission to prevent blind retries. Inspect a failed submission rather than
deleting that file and submitting duplicates. Successful/failed completed runs
are paused automatically on subsequent inspection. Brief unpausing can also create
a due scheduled run; catchup=False does not mean zero scheduled execution on unpause.
A manual run can remain active across inspection; repeat inspection until terminal.

To release resources without losing metadata, logs or credentials:

```powershell
docker compose -f airflow/compose.yaml --env-file airflow/.env.local stop
```

Use `up -d` to resume. Do not use `down -v` unless intentionally destroying only
this local Airflow project's data. Banking and monitoring services are independent.

## Actual verification

Health endpoint `/api/v2/monitor/health` reported healthy metadata database,
scheduler, triggerer and DAG processor. Authenticated discovery found
bankops_daily_reconciliation, initially paused. Docker health additionally checks
metadata, scheduler and DAG processor status, not just an HTTP 200.

Manual run **step55_20261016T023857** completed successfully. All four tasks first
completed on attempt 1:

| Task | Actual state |
| --- | --- |
| validate_read_only_connectivity | success |
| execute_reconciliation | success |
| validate_results | success |
| execution_summary | success |

Its stored XCom was PASS / snapshot_checked with all four rule violation counts
zero. A separate direct reconciliation through the same SELECT-only role produced
the identical rule outcomes. XCom contained only aggregate findings and timestamps.
Unpausing also allowed one due scheduled run, scheduled__2026-10-16T00:00:00+00:00,
which succeeded. Only one manual DAG run was created. The DAG is paused after
verification to prevent further scheduled runs.

Recreating only the Airflow container retained the successful run and task records,
paused state and local authentication, proving metadata persistence. No metadata
or banking volume was removed. Initial WARNING-level logging hid the INFO summary;
the runtime was corrected to INFO. Only the existing manual run's summary task was
cleared for a controlled repeat; no reconciliation or financial task was rerun.
Final summary/log verification is recorded below.

Safe failure probes executed inside the real runtime used only a closed localhost
port and synthetic aggregate reports: unavailable connectivity was rejected,
INSUFFICIENT_DATA raised its distinct retryable exception, and synthetic violations
raised AirflowFailException without automatic retries. These probes did not contact
banking PostgreSQL or create fake financial entries. Automated tests additionally
exercise malformed/private XCom payload rejection and read-only rollback.

Before/after read-only repeatable-read table fingerprints matched:

| Table | Rows | Row-content MD5 before and after |
| --- | --- | --- |
| accounts | 3 | df772bdf0304dc65296d25700ea38d41 |
| transfers | 2 | 73959676babf273b756172c65dfde71d |
| ledger_entries | 4 | c1904307e418d06e80aa85a3a4f9817e |

These are ordered row-JSON fingerprints, not exported financial rows. They provide
observed content comparison, not a cryptographic audit or backup. No banking records
were created, deleted or updated. V1–V5 and banking APIs/monitoring remain unchanged.

## Resources and limits

Limits: Airflow 2304 MiB / 2 CPUs; metadata 384 MiB / 0.5 CPU. Total memory cap
**2688 MiB (2.625 GiB)**, suitable for this small local workload on a 16 GB laptop
subject to other running applications and Docker Desktop VM allocation.
Samples during startup/verification showed Airflow **1.061–1.186 GiB**, metadata
**61.01–62.33 MiB**; these are point samples, not measured peak memory. One sample
showed Airflow 68.13% CPU and metadata 5.76%; Docker percentages are per logical CPU.
The existing unrelated Airflow stack and monitoring consume additional resources.
No long-duration load, OOM recovery, HA or multi-worker scale test was performed.

Only the PASS path was scheduler-executed against real development data. Failure
behavior was exercised through actual runtime helpers and synthetic automated
fixtures, not by corrupting development data or scheduling a production failure.
The read-only module's row cap, opening-balance semantics and current-snapshot
limitations in README.md remain. Local SimpleAuth/plaintext password volume is for
trusted local development only. External settlement/fraud is outside reconciliation.

## Final results and runtime state

- Final Airflow/DAG/runtime/reconciliation suite: **42 passed**, warnings treated as
  errors, 20.33 seconds, isolated PostgreSQL 17. Includes proxy-bypass and
  INFO-summary-configuration regressions.
- Banking regression suite: **202 passed**, zero failures/errors/skips,
  BUILD SUCCESS, 1 minute 17 seconds, isolated PostgreSQL 17.
- Existing Airflow test image dependency check passed in Step 54; the runtime uses
  the same pinned Airflow/psycopg versions. V1–V5 SHA-256 values remain unchanged.
- Summary-only controlled repeat succeeded on attempt 2 and its task log contains
  the aggregate `Reconciliation summary` record. Connectivity, reconciliation and
  validation retain their original successful attempt-1 records. This was an
  explicit operator repeat after fixing logging, not an automatic remediation retry.
- Metadata, all component health statuses and the successful run survived container
  recreation. The DAG is paused. The two local runtime services remain available
  for review; stop commands above release memory while retaining all volumes.
- A final resource sample showed Airflow **1.177 GiB / 14.91% CPU**, metadata
  **62.95 MiB / 6.46% CPU**. These are point samples, not load or peak guarantees.
- An in-memory scan of current runtime stdout and persisted task logs found none
  of the configured secrets, actual account numbers, account IDs or transfer IDs.
  Raw logs and those identifiers were not included in the report.
- Existing banking/Prometheus/Grafana/Jaeger containers and the unrelated Airflow
  project were left running. The disposable banking-test container and volume were
  removed. Persistent BankOps Airflow metadata/log/auth volumes were retained.

The UI responded HTTP 200 at http://127.0.0.1:18081/. All financial record comparisons
remained identical. No financial remediation, trigger bypass or banking API changes
were performed.

Step 56 adds a separate agentviewer viewer identity for GET-only agent collection; its generated password stays in ignored local environment configuration. The DAG stays paused. See [agent evidence integration](../agent/AIRFLOW_EVIDENCE.md).
