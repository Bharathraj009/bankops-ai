# Airflow reconciliation incident evidence

The reliability agent optionally collects reconciliation status from authenticated
Airflow 3.3 REST API v2 GET endpoints. It reuses the existing incident detection
and shared investigation path; both GET /incidents/investigate and the LangGraph
POST /workflows/investigate include the evidence. GET /incidents/detect uses the
same combined deterministic detection. Existing approval/decision/execution and
verification APIs and storage are unchanged. No remediation is dispatched.

## Configuration and least privilege

All values use the agent's existing environment configuration:

| Environment variable | Default / constraint |
| --- | --- |
| BANKOPS_AGENT_AIRFLOW_ENABLED | false, including production |
| BANKOPS_AGENT_AIRFLOW_URL | http://localhost:18081; no credentials, query or fragment |
| BANKOPS_AGENT_AIRFLOW_API_TOKEN | Required only when enabled; externally supplied read-only/viewer bearer token |
| BANKOPS_AGENT_AIRFLOW_TIMEOUT_SECONDS | 5; >0 and <=30, total collection deadline |
| BANKOPS_AGENT_AIRFLOW_WINDOW_SECONDS | 172800 (2 days); 1 hour through 7 days |
| BANKOPS_AGENT_AIRFLOW_MAX_RUNS | 5; 1 through 10 |

HTTPS is required when enabled outside localhost development. Tokens are SecretStr,
excluded from settings repr, never returned/logged. Use a least-privilege Airflow
viewer/DAG-read role permitted to read this DAG's runs, task instances and aggregate
XCom. The collector never uses an admin password, authenticates by GET bearer
headers only, does not follow redirects or use environment proxies, and never
logs upstream payloads or exception messages. Standard agent startup suppresses
third-party HTTP diagnostics; retain this logging configuration when embedding.

Obtain/refresh the bearer token outside the collector using your Airflow identity
provider/secret manager. No automatic login or refresh occurs. Expired/revoked
credentials produce unavailable evidence (401/403), never PASS. Do not paste a key
into commands or tracked files. Restart/reconfigure the agent after external token
rotation as appropriate. Inference, approvals and remediation remain disabled unless
separately configured; enabling Airflow does not enable any of them.

Local development Airflow now pre-seeds a separate `agentviewer:viewer` principal,
with its own generated BANKOPS_AIRFLOW_VIEWER_PASSWORD in ignored airflow/.env.local.
The admin identity remains separate. Provisioning is repeatable using the existing
local script; only role/grant metadata changes, never financial rows. Local startup
pre-seeds both credentials without printing them. This is development-only SimpleAuth,
not a production identity system. See ../airflow/LOCAL_RUNTIME.md for local startup.
A one-time auth-token exchange may use POST /auth/token outside the collector; all
collector requests remain GET-only. No token is persisted by collection.

## Bounded collection and privacy

Only bankops_daily_reconciliation is collected. Requests are:

1. GET its dagRuns with run_after_gte, newest run_after first and configured limit.
2. GET up to five task instances for each returned recent run; exactly the four
   expected task names/states must be present.
3. GET execute_reconciliation's return_value XCom only after that task succeeded.

At most 1 + 2 * max_runs requests occur (11 default, 21 hard maximum). Each response
is capped at 256 KiB and the whole operation has one deadline. No pagination past
the limit, retries, logs, DAG code, conf, rendered fields, arbitrary resource paths
or XCom deserialization requests are used. Truncation remains explicit partial data.
Run IDs are validated and used internally for lookup but never returned; malformed
or traversal-like IDs are rejected. The output contains only a fixed DAG name,
fixed task names, allowlisted states, event timestamps, outcome categories and four
bounded rule violation counts. It contains no account/transfer IDs, account numbers,
amounts, balances, hosts, notes, request bodies or raw error strings.

Reconciliation XCom is strictly allowlisted and validated for all four distinct
known rules, count bounds, PASS/FAIL consistency and timestamps within the successful
execute_reconciliation task's interval. Unknown fields and duplicate JSON keys are
rejected. Binding to task timestamps matters: clearing only a downstream summary
can reset DAG-run start time without changing the original reconciliation XCom.
Evidence from a different execution attempt is rejected. No historical financial
values or identifiers enter investigation responses or LLM prompts.

## Report contract and deterministic incidents

DetectionResult has one additive optional `airflow` field (null while disabled).
Its existing Prometheus evidence and rules remain. InvestigationReport includes
this through `detection.airflow`; no existing fields/endpoints are removed. LangGraph
continues using the same typed shared detection result and assembly nodes, preserving
exact-ID trace/log correlation. Airflow is not correlated to banking IDs.

AirflowEvidence contains source, fixed dag, collected_at, status, truncated and a
bounded runs array. Each run exposes observed_at (Airflow run_after event time),
state, outcome, summary_status, aggregate checks and safe tasks. collected_at is
the local collection time. No run IDs or arbitrary upstream labels are exposed.

| Observed evidence | Outcome / triggered rule |
| --- | --- |
| Failed DAG, successful reconciliation task, valid FAIL summary | financial_violations / reconciliation_financial_violations |
| Failed DAG, valid INSUFFICIENT_DATA summary | insufficient_data / reconciliation_insufficient_data |
| Failed DAG without a valid financial finding, including PASS summary or missing details | task_failure / reconciliation_task_failure |
| Successful DAG, all tasks success, valid PASS summary | pass; reconciliation rules healthy if complete window sample |
| Queued/running, missing or inconsistent evidence | insufficient-data decision, never PASS |

A `financial_violations` observation means the checker reported violations; it is
not an independently confirmed corruption/root cause. A task/workflow failure never
implies financial corruption. Known failed-run observations remain incidents even
if task/XCom retrieval fails; source status preserves partial/unavailable/timeout.
Unavailable Airflow alone is insufficient data, not an invented financial incident.
Prometheus incidents are never masked by missing Airflow.

Any failed run within the collected window triggers an incident, even if a later
run passed. This is recent-failure reporting, not an assertion of ongoing corruption
or automatic incident resolution. A complete bounded sample of successful PASS runs
is required for Airflow health. Missing, stale, malformed, truncated, in-progress,
unavailable or timed-out data cannot establish health. Existing confirmed incidents
win over insufficient evidence; overall healthy requires both Prometheus and enabled
Airflow to be healthy. Support-source completeness includes enabled Airflow.

Observed Airflow evidence stays separate from AI hypotheses. The strict RCA kind
allowlist is unchanged: new Airflow rules are not mapped to unsupported causal
hypotheses. Airflow-only incidents produce undetermined RCA, even with a configured
provider, without calling it when no supported causal evidence exists. Existing
metric/trace hypotheses remain subject to their original evidence checks. Root
cause is never confirmed. No proposal, approval, action execution or financial write
is automatic; the approval workflow remains unchanged.

## Verification and limits

Tests use mocked HTTP and an independently served loopback Airflow fixture with a
synthetic viewer bearer token. The complete HTTP -> shared detection -> LangGraph
report path is exercised for financial violations, task failures, insufficient data,
source failures and healthy cases. Legacy approval/remediation tests remain intact.
Live verification used a separate viewer principal, not the admin, with all secrets
held in memory. GET of admin configuration returned 403. Real read-only collection
returned status ok, two PASS runs, four safe tasks per run and zero violations for
all rules. The paused DAG was not triggered or cleared by this step.

The actual LangGraph investigation included status-ok Airflow evidence and three
healthy reconciliation rules. Overall detection was insufficient_data because the
other evidence/traffic did not establish overall health; RCA was undetermined,
root_cause_confirmed false and remediation disabled. A passing reconciliation did
not turn missing/insufficient observability data into a healthy report.

Live verification exposed the DAG-start-reset issue above; the collector now uses
execution task times and a regression rejects cross-attempt XCom. No financial
constraint or assertion was weakened.

REST endpoints do not provide an atomic multi-request snapshot. Inconsistent
metadata is treated conservatively. Sampling is bounded and cannot prove absence
of older failures or financial corruption outside the scanned reconciliation
coverage. Token rotation remains an operator responsibility. The module does not
verify the Airflow server's internal financial checker implementation or access
banking PostgreSQL directly. Synthetic failures were not introduced into development
financial records. Final test counts and unchanged-data checks follow below.

### Final automated results and data-preservation checks

- Agent complete suite: **474 passed**, warnings treated as errors, 83.77 seconds.
  Includes 35 Airflow evidence/integration regression cases and the full existing
  approval, execution, verification, RCA and process-restart coverage.
- Airflow/runtime/reconciliation suite: **43 passed**, warnings treated as errors,
  21.79 seconds, with isolated PostgreSQL integration fixtures.
- Banking complete suite: **202 passed**, zero failures/errors/skips, BUILD SUCCESS,
  1 minute 35 seconds against disposable PostgreSQL 17.
- Dependency check: no broken requirements. No new Python dependency was needed.
- V1–V5 SHA-256 hashes match the prior baseline. Banking code, root monitoring
  Compose configuration, APIs and financial protections were not changed.
- The disposable PostgreSQL test container and volume were removed. Local Airflow
  remains healthy with the existing DAG paused; no DAG runs or task clears were
  performed during Step 56. Approval and remediation defaults remain disabled.

Read-only development snapshots before and after the work matched exactly:

| Table | Rows before / after | Row-content MD5 before / after |
| --- | --- | --- |
| accounts | 3 / 3 | df772bdf0304dc65296d25700ea38d41 |
| transfers | 2 / 2 | 73959676babf273b756172c65dfde71d |
| ledger_entries | 4 / 4 | c1904307e418d06e80aa85a3a4f9817e |

No account, transfer or ledger records were created, modified or deleted. These
fingerprints are content-comparison evidence, not a backup or cryptographic audit.
The only local Airflow runtime change was adding the separate viewer principal;
existing banking read-role provisioning retained the same secret and SELECT-only
grants. Collector defaults remain disabled; real verification used in-memory
short-lived viewer tokens and did not store a token in tracked configuration.
