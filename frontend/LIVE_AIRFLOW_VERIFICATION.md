# Step 62: live Airflow dashboard verification

Verified on **2026-10-27**, America/Chicago. The real path was:

```text
Chromium / React (localhost:5179)
  -> GET /reconciliation-api/incidents/detect
  -> unchanged FastAPI agent (localhost:18063)
  -> authenticated viewer GETs to actual Airflow 3.3.2 (localhost:18081)
  -> retained Airflow metadata and real reconciliation XCom
```

No banking/API, agent contract, DAG, Compose or financial implementation changed.
The additions are opt-in verification helpers, Chromium checks, and documentation.
No execution duration, stable run ID or other unsupported DTO field was invented.

## Services and one authorized read-only run

Initially the BankOps Airflow containers were stopped. Only BankOps PostgreSQL,
Airflow metadata PostgreSQL, the local Airflow service, a temporary agent and Vite
were started. The unrelated Airflow project and existing isolated banking-test
container were left alone. Spring Boot, Prometheus, Grafana and Jaeger were not
started; they are unnecessary for Airflow reconciliation evidence.

The retained Airflow container referenced a deleted Docker network. Recreating
only that service repaired its attachment while preserving metadata, logs and
authentication volumes. Health reported healthy metadata database, scheduler,
triggerer and DAG processor. The DAG was paused and had two successful runs from
October 16, outside the agent's maximum seven-day evidence window. Old timestamps
were not rewritten and the backend window/schema were not changed.

The user explicitly authorized **one** fresh read-only verification run. Before
execution, the existing `bankops_reconciliation` role was checked: default
transaction read-only enabled; SELECT on all four required tables; no INSERT,
UPDATE, DELETE, TRUNCATE or TRIGGER privilege on those tables. The existing DAG's
read-only reconciliation implementation was used unchanged.

`testing/run_live_readonly_dag.py` invoked Airflow's actual `dags test` command
once, without `--mark-success-pattern`. A persistent exclusive claim under the
Airflow authentication volume prevents accidental re-execution. All four tasks
really executed; none were skipped or artificially marked successful. The DAG
remained paused throughout, avoiding an extra due scheduled run. This was a real
Airflow CLI-executed DagRun, not a new scheduler-dispatched run or an HTTP fixture.
No automatic action retry or financial write was requested.

Airflow run count increased **2 -> 3**, remaining 3 at final inspection. The new
run observation was **2026-10-27T19:05:46.797886Z** (2:05:46 PM CDT):

| Task | Actual state |
| --- | --- |
| validate_read_only_connectivity | success |
| execute_reconciliation | success |
| validate_results | success |
| execution_summary | success |

The actual agent returned HTTP **200**, Airflow status **ok**, `truncated=false`,
one recent run, outcome **pass**, summary **PASS**, and zero violations for all
four checks. The two older runs were correctly outside the collection window.
Other monitoring was unavailable; an Airflow PASS did not establish overall
banking observability health.

## Browser and failure verification

| Case | Actual verification |
| --- | --- |
| Real PASS and details | Real API response and UI showed one successful run, all four task states, all four zero-violation checks and last successful run timestamp |
| Filters | PASS showed the real run; financial violations, task failures, insufficient data and in-progress filters correctly showed no matching runs |
| Refresh | Explicit click fetched a newer collection timestamp and retained the same real run |
| Stale evidence | Waited for the actual 60-second collection TTL, without mocked clock or rewritten evidence; KPI became INSUFFICIENT_DATA / Stale, with historical run retained |
| Recovery from stale | Explicit refresh removed the warning and restored the freshly collected PASS; no background automatic refresh occurred |
| Unavailable Airflow | Real agent was temporarily configured to a verified closed loopback port; HTTP 200 carried Airflow `unavailable`, zero runs, and UI INSUFFICIENT_DATA, never PASS |
| Financial FAIL / run-level INSUFFICIENT_DATA | Existing isolated authenticated Airflow HTTP fixture exercised the real collector and browser; these were synthetic aggregate scenarios, not violations induced in banking data |
| Privacy and read-only browser access | Browser requests stayed on localhost Vite, used GET only and contained no Authorization header; Airflow token never entered the browser |

The closed-port check did not stop or alter actual Airflow. The fixture also
verified task failure despite a recorded PASS summary, in-progress state,
unauthorized upstream 401, blocked proxy paths/methods 404, and zero upstream
writes. No false financial-corruption or incident-resolution claim was made.

Desktop screenshots of the actual real evidence were inspected. Safe projected
evidence and a screenshot are retained under ignored `.cache/step62-live/`.
No viewer token or local password was written there.

## Reproduce read-only collection

Existing ignored `.env` and `airflow/.env.local` must already contain the local
credentials. Do not print their contents or use browser `VITE_*` secret variables.
From repository root, start only the dependencies:

```powershell
docker compose up -d --no-deps postgres
docker compose -f airflow/compose.yaml --env-file airflow/.env.local up -d --no-build airflow-metadata airflow
agent/.venv/Scripts/python.exe frontend/testing/live_airflow_agent.py --inspect
```

From `frontend/`, in separate terminals:

```powershell
../agent/.venv/Scripts/python.exe testing/live_airflow_agent.py --serve

$env:BANKOPS_RECONCILIATION_API_TARGET='http://127.0.0.1:18063'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5179 --strictPort

$env:BANKOPS_REAL_AIRFLOW='available'
npx playwright test --config playwright.reconciliation.config.ts --grep 'real Airflow PASS'
```

The launcher authenticates only as `agentviewer`, holds its short-lived token in
memory, and starts the unchanged app. LLM inference, approval storage and
remediation are explicitly disabled. Real Prometheus reads remain configured to
the local endpoint but tolerate its absence; no Prometheus fixture is used in
this live mode. Do not reuse the separate synthetic launcher for a real claim.

The real PASS test intentionally requires exactly the current one-run sample;
future new runs or expiration beyond seven days will require inspecting actual
conditions rather than weakening assertions. The maximum window and run count
stay within existing Settings limits. A missing recent sample must remain
INSUFFICIENT_DATA; this launcher never triggers a new run automatically.

For unavailable-source verification, stop only the temporary agent first and run
it with `--serve --unavailable-source`. This uses fixed localhost port 18999,
which must be closed. Set `BANKOPS_REAL_AIRFLOW=unavailable` and run the same config
with `--grep 'real agent returns unavailable'`. The real Airflow runtime stays up.
Synthetic cases use the existing commands in [RECONCILIATION.md](RECONCILIATION.md).

## Tests and preservation

| Check | Result |
| --- | --- |
| Complete frontend component/API suite | **96 passed**, six files |
| Complete desktop/mobile Chromium suite | **26 passed** |
| Real Airflow PASS, task details, filters, refresh and natural stale expiry | **1 passed**, approximately 72 seconds |
| Real-agent unavailable-source Chromium check | **1 passed** |
| Isolated authenticated FAIL/INSUFFICIENT_DATA/task-failure fixture | **1 passed** |
| ESLint, TypeScript and Prettier | Passed |
| Production build | Passed, unchanged reconciliation application chunk 4.43 kB gzip |

No financial assertions were weakened, no test timeout was increased in existing
tests, and all existing browser regressions were included. The new real-evidence
test explicitly permits enough time to wait for the actual freshness TTL.
The bank/agent/Airflow implementation suites were not rerun; their code and
contracts were unchanged, and the live checks directly exercised the actual
Airflow tasks, read-only bank role, agent collector and detection endpoint.

After verification, only the temporary agent/fixture/Vite processes and the three
BankOps containers started for this task were stopped, returning those services
to their initial stopped state. Persistent banking, metadata, log and auth volumes
were retained. The unrelated Airflow project and pre-existing banking-test
container were left running. The verified DAG remains paused with exactly three
stored runs; the real run and its successful task records remain inspectable.

A Docker point sample before cleanup showed Airflow 1.183 GiB, metadata PostgreSQL
48.17 MiB, and banking PostgreSQL 20.36 MiB. These are samples, not peak guarantees.

Before/after full-row aggregate fingerprints matched:

| Table | Rows | Ordered row JSON MD5 |
| --- | --- | --- |
| accounts | 3 | 47f5a9b6bccf79419938b3846b5e4011 |
| transfers | 2 | 320157084af0d56192b3b951327b3dc7 |
| ledger_entries | 4 | c75027a827d8eaa1178cb9399fd158f0 |

These comparisons are read-only content checks, not a backup or security audit.
V1–V5 SHA-256 hashes matched before/after. No account, transfer, balance, ledger,
Flyway history, financial trigger or API was modified. Only legitimate Airflow
execution metadata/logs/XCom and ordinary authentication activity were added.

## Remaining limits

No genuine financial FAIL or run-level INSUFFICIENT_DATA was introduced into the
development DAG. Those branches were verified through controlled fixtures, with
the same collector/DTO/UI, rather than corrupting financial data or executing
additional runs. The actual live run was PASS; source unavailability and natural
staleness were separately verified through the real agent/browser path.

The contract still has no execution durations, task timestamps, stable run IDs,
global latest-success guarantee or backend pagination. The dashboard correctly
shows only observation/collection timestamps and the bounded returned sample.
No unsupported duration is inferred. Collection is a multi-request read and does
not establish an atomic Airflow snapshot or full production reliability.
