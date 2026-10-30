# Banking reconciliation and Airflow scheduling

The reconciliation module checks account balances, double-entry postings, ledger
consistency and transfer lifecycle invariants in one read-only PostgreSQL snapshot.
A daily Airflow DAG runs the connectivity, reconciliation and validation tasks;
the agent and dashboard consume bounded task/check summaries.

Use the [local platform](../local/README.md) for the integrated scheduler runtime
and [Airflow runtime guide](LOCAL_RUNTIME.md) for component setup. The CLI below
runs reconciliation independently. [Scheduled integration evidence](../docs/verification/STEP75_INTEGRATION_REPORT.md)
records an actual scheduler-created run reaching the dashboard.

## Configuration and execution

Use Python 3.12. From airflow/:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Supply BANKOPS_RECONCILIATION_DSN through the environment/secret manager.
.\.venv\Scripts\python.exe -m reconciliation
```

The DSN is a PostgreSQL URI/conninfo string. Provision a dedicated SELECT-only
role for public.flyway_schema_history, accounts, transfers and ledger_entries.
Use TLS for remote access. Do not use an application owner or superuser in
production. No role/grant or banking data changes are made by the module.

The Python interface is reconcile(dsn=None, max_rows=100000), returning a frozen
Result with to_dict(). The CLI prints JSON and exits 0 (PASS), 1 (FAIL), or
2 (INSUFFICIENT_DATA). Reports include UTC start/end timestamps, status, a bounded
reason and per-rule statuses/violation counts. No logs, credentials, SQL details,
account/transfer IDs, account numbers, balances or amounts are emitted.

## Deterministic rules

| Rule | Invariant |
| --- | --- |
| completed_double_entry | COMPLETED has exactly one source DEBIT and destination CREDIT, both equal to the positive USD transfer amount |
| account_balances | Balance equals immutable opening_balance + all credits - all debits; finite nonnegative cent-precision USD values |
| ledger_consistency | No missing/duplicate sides, duplicate ledger IDs, orphan references, invalid types, wrong amounts/accounts/currencies or nonpositive values; transfer accounts exist and differ |
| lifecycle_ledger | Only PENDING/COMPLETED/FAILED; COMPLETED needs its valid pair, FAILED has no entries |

V2 permits PENDING with either no entries or a valid full pair. Partial or malformed
pending postings fail ledger_consistency. Balance reconciliation includes all
postings, matching V3's immediate balance trigger. Current rows cannot establish
whether historical lifecycle transitions were legal.

V3's opening_balance is the immutable genesis baseline. This includes legitimate
reserve initialization described in DEV_FUNDING.md; no invented ledger entries
are required. Historical nonzero openings are accepted for all accounts, without
account-number heuristics or exceptions. The API's zero-opening rule does not
invalidate historical V3 baselines. Reconciliation does not validate the economic
legitimacy of an opening balance.

PostgreSQL NUMERIC decodes to Decimal. Financial arithmetic uses Decimal with
precision 80, sufficient for the bounded NUMERIC(19,2) snapshot; no float money
conversions occur. Counts may overlap across rules and do not represent distinct
affected entities.

## Read-only snapshots and limits

A connection enforces default_transaction_read_only and an explicit REPEATABLE READ
READ ONLY transaction. All reads use one committed snapshot; rollback is unconditional,
including success. No FOR UPDATE, procedure calls, financial writes, trigger bypass,
remediation or external commands occur. SELECT-only grants provide defense in depth.
Connection timeout is 5 seconds, each statement timeout 5 seconds, lock timeout 2 seconds.

Successful Flyway versions 1–5 and compatible public columns are required. This
checks compatibility, not checksums or actual trigger installation. Later versions
are tolerated if compatible but require semantic review before production use.

Each table is bounded to at most 100,000 rows (caller may lower the cap). Reading
one additional row detects truncation. Exceeding the cap, missing/incompatible
schema, source/query failures or timeout returns INSUFFICIENT_DATA, with no partial
findings. A compatible empty snapshot passes vacuously. A complete snapshot with
any violation is FAIL; otherwise PASS. No unavailable or incomplete scan is healthy.

The implementation reads bounded snapshots in memory. Larger datasets would need
streaming or SQL aggregation while preserving snapshot and completeness semantics.
PASS only describes these current-snapshot invariants; it is not proof of external
settlement, historical lifecycle correctness, fraud absence or source authenticity.

## Isolated tests

From airflow/:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
# Set BANKOPS_RECONCILIATION_TEST_DSN to disposable PostgreSQL with CREATEDB.
.\.venv\Scripts\python.exe -m pytest -q -W error
```

Each integration case creates a unique test database and removes only that database.
The genuine schema test applies unchanged V1–V5 and uses genesis inserts and balanced
postings. Deliberately malformed cases use separate synthetic tables without
constraints; no production integrity trigger is disabled. Tests verify unchanged
row JSON before/after scanning, read-only write rejection, Decimal precision,
invalid and missing postings, failed/pending lifecycle relationships, schema/cap
failures, safe unavailable responses and snapshots during concurrent commits.

Actual suite results follow below.

## Actual verification results

Historical standalone-module verification (Step 53), before DAG scheduling was added:

- Reconciliation suite: **20 passed**, warnings treated as errors, 12.42 seconds.
- Banking suite: **202 passed**, zero failures/errors/skips, BUILD SUCCESS,
  1 minute 48 seconds against disposable PostgreSQL 17.
- Driver/dependency check: no broken requirements.
- V1–V5 SHA-256 hashes match the prior baseline; no migration was changed or added.
- Disposable test databases, PostgreSQL container and test volume were removed.
- No development database connection or banking write was performed by this step.
  Banking code and monitoring configuration are unchanged.

The initial NaN preservation assertion failed because Decimal NaN does not equal
itself. The test now compares PostgreSQL row JSON before/after scanning, preserving
the invalid-value FAIL assertion. All final tests pass. No Airflow scheduling or
financial remediation was introduced.

## Step 54: daily Airflow DAG

`dags/bankops_reconciliation.py` targets Apache Airflow **3.3.2**, Python 3.12,
using the public `airflow.sdk` decorators. It defines (but does not start)
`bankops_daily_reconciliation`, scheduled at **00:00 UTC daily**. `catchup=False`,
`max_active_runs=1`; all tasks configure `retries=2`, `retry_delay=5 minutes`.
No scheduler, web/API server, worker, metadata migration or full Airflow stack
was started for this step.

Task topology:

```text
validate_read_only_connectivity -> execute_reconciliation -> validate_results
                                                        -> execution_summary
```

Connectivity uses an explicitly read-only transaction and SELECT 1, checks
transaction_read_only, and rolls back. The check task reuses `reconcile()` and its
independent repeatable-read snapshot. Database configuration remains solely
BANKOPS_RECONCILIATION_DSN from the worker environment, provisioned via secrets;
no credentials or banking DSN are read at DAG parse time or embedded in DAG code.
Keep the dedicated SELECT-only role described above. The test credentials only
refer to disposable synthetic databases.

Only execute_reconciliation pushes XCom: a strict aggregate payload under 2 KB in
unit fixtures, with at most four rule summaries and timestamps. No ledger rows,
identifiers, balances, connection details or raw exceptions enter XCom. All
operators disable return-value logging. Summary output is strict allowlisted JSON;
unknown fields, malformed timestamps or inconsistent states are rejected before
logging. A missing result produces a fixed unavailable summary and fails.

PASS validates successfully. FAIL raises AirflowFailException: deterministic
integrity violations fail without wasteful retries, despite the configured retry
count. INSUFFICIENT_DATA raises a distinct AirflowException eligible for task
retries and never becomes PASS or skipped. Validation retries evaluate the same
immutable XCom snapshot; they do not recollect data. A new DAG run is required
for a new snapshot. Connectivity retries establish a new read-only connection.
No task retries write or repair banking data.

Summary uses ALL_DONE and pulls only the aggregate result; it runs even when
upstream work fails. Both validation and summary are terminal tasks, ensuring
summary success cannot mask validation failure in Airflow's leaf-based DAG outcome.
Summary also fails on violations/insufficient/missing evidence. This deliberately
creates two parallel terminal tasks rather than an ALL_DONE success-only leaf.

## DAG deployment and tests (no stack startup)

Install Airflow 3.3.2 in a supported Linux Python 3.12 environment using its matching official constraints first. Then install requirements-airflow.txt with the Airflow version pinned and run pip check, as verified in Dockerfile.test. The reconciliation driver pin is installed after the base Airflow constraints.
Deploy the DAG folder and make this directory available on PYTHONPATH to both the
DAG processor and task workers; the shared reconciliation package is required.
Use your existing Airflow secret/environment provisioning. Review privileges and
row caps before deployment; this step does not deploy or unpause a DAG.

Windows execution uses the official Linux Airflow test image. From repository root:

```powershell
docker build -f airflow/Dockerfile.test -t bankops-airflow-step54-tests airflow
```

Run that image with the repository mounted read-only at /workspace, working
folder /workspace/airflow and PYTHONPATH=/workspace/airflow. Supply
BANKOPS_RECONCILIATION_TEST_DSN for a disposable PostgreSQL instance with CREATEDB
privilege, then execute `python -m pytest -q -W error -p no:cacheprovider`.
Do not point integration-test setup at development or production databases.
The test image runs pytest, not an Airflow service; no stack is started.
For native core-only testing without Apache Airflow installed, use
`python -m pytest tests/test_reconciliation.py -q -W error` instead.

Tests inspect an actual DagBag with zero import errors, schedule, task topology,
retry configuration, no parse-time connectivity, XCom scope and log safety. Task
unit tests cover PASS, FAIL, INSUFFICIENT_DATA, absent configuration/results,
connection failures, rollback and strict payload rejection. Existing isolated
PostgreSQL tests still cover the financial invariants. Actual final results follow.

Reference: [Airflow DAG and trigger-rule behavior](https://airflow.apache.org/docs/apache-airflow/3.3.2/concepts/dags.html).



### Step 54 actual verification results

- **37 tests passed** (17 DAG/task tests plus 20 reconciliation tests), warnings
  treated as errors, 30.68 seconds in Apache Airflow 3.3.2 / Python 3.12 Linux.
- Actual DagBag import: zero import errors; all four real task callables exercised,
  daily UTC schedule, catchup/overlap/retry settings and failure-safe topology checked.
- **202 banking tests passed**, zero failures/errors/skips, BUILD SUCCESS,
  1 minute 49 seconds against disposable PostgreSQL 17.
- Airflow test-image pip check: no broken requirements.
- V1–V5 checksums unchanged. Banking code and monitoring unchanged.
- No development database was accessed. No full Airflow stack was started.
- Ephemeral test containers and PostgreSQL test volume were removed after testing.

The import tests caught deprecated exception/DagBag imports and older DagBag/
timetable test APIs; these were updated to the installed Airflow 3.3.2 APIs rather
than suppressing warnings. Final imports and tests pass without warnings.

Limitations: this verifies parsing, task functions, topology and PostgreSQL reads,
not a scheduler-driven production DAG run, worker deployment or Airflow metadata/XCom
persistence across a full stack. No deployment or scheduling activation was performed.
The Step 53 row cap and reconciliation coverage limitations continue to apply.

Step 55 local Compose runtime, commands, measured resources and actual verification: [LOCAL_RUNTIME.md](LOCAL_RUNTIME.md).

Step 65 adds separate metadata administrator/runtime credentials for **fresh**
volumes and a central [banking database permission policy](../database/README.md).
Existing metadata volumes are not automatically demoted or reinitialized. Supply
`BANKOPS_AIRFLOW_METADATA_ADMIN_PASSWORD` separately; the Airflow service receives
only its non-superuser metadata password. The banking reconciliation login remains
SELECT-only, with no customer authentication-table access. See [SECURITY.md](../SECURITY.md)
for the actual audit, isolated tests and pending existing-volume rollout.
# Unified local Docker (Step 67)

The [unified local runbook](../local/README.md) starts this patched Airflow image
with its own fresh metadata, auth and log volumes. It reuses this Compose service
through `extends`, with exact internal `postgres` service DNS for reconciliation
and localhost UI port 18087. The standalone configuration remains available.
Only `postgres` and the existing standalone banking container hostname are allowed
by the runtime hostname selector. No administrator or migration secret enters
Airflow. The full scheduler/API/DAG processor health check and real SELECT-only
reconciliation passed in the Step 67 isolated stack. DAGs remain paused by default.
