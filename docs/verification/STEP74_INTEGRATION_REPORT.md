# Step 74: end-to-end integration verification

Date: 2026-10-29. Result: **verified connected synthetic investigation slices;
full running-stack integration remains incomplete**. No real cloud inference,
paid service, external banking-data transmission, Ollama, push or deployment.

## Architecture and scope

React uses a same-origin Vite proxy with route/method and origin restrictions.
Its investigation proxy supplies the server-held agent credential to FastAPI.
The workflow joins parallel detection and evidence_collection at report_assembly,
then runs rca and ends. Prometheus drives banking incident rules; Jaeger and
local structured logs provide supporting evidence. Optional Airflow GETs add
bounded reconciliation summaries to incident detection. RCA retrieves local
BM25 chunks and optionally invokes a provider, independently validating current
observation and document citations. Human proposals/reviews use separate roles
and a private approval store. Model output does not execute remediation.

Inspected workflow/app/config, evidence and RCA/RAG modules, frontend proxy and
incident page, existing agent process/HTTP tests, Airflow DAG/reconciliation tests,
Step 73/73B reports and running container feature flags. Existing dirty workspace
changes were retained. No application implementation or security policy was
changed during Step 74; additions are verification harnesses/tests and this report.

## Actual connected execution

`agent/tests/test_step74_integration.py` starts an isolated real Uvicorn FastAPI
server and real Vite frontend, then drives actual headless Chromium against them.
No frontend API response routes are mocked. Both profiles run at desktop
1440x1000 and mobile-sized 390x844 viewports (not a physical mobile device).

| Profile | Connected path actually executed | Results |
| --- | --- | --- |
| HTTP observability / disabled inference | Chromium UI -> Vite proxy -> authenticated FastAPI -> production collectors over real loopback HTTP to synthetic Prometheus/Jaeger-format endpoints and a synthetic WARN log file -> detection -> real four-node LangGraph -> local RAG -> report -> React render | Two viewport runs; 60 HTTP evidence requests across fixture; zero provider calls; incident and matched retrieval; disabled inference displayed |
| Synthetic / mocked cloud | Chromium UI -> Vite proxy -> FastAPI -> server-owned synthetic demo collectors -> detection -> real LangGraph -> RAG -> production cloud adapter with httpx2.MockTransport -> independent citation validation -> React hypothesis render | Two viewport runs; exactly two mocked provider calls; zero HTTP observability fixture requests; supported hypotheses displayed; no confirmed root cause |

Each browser flow collects evidence without a POST, then explicitly confirms
the AI workflow and sends exactly one workflow POST. Reports include successful
trace/log collection and retrieved chunks from service-outage and
investigation-guide. The cloud output cites retrieved IDs present in that same
report. No browser JavaScript errors occurred. Both profiles use synthetic
content only. The HTTP observability servers emulate upstream APIs; this is not
a claim that actual Prometheus/Jaeger processes participated in these slices.

The same isolated HTTP agent also verifies anonymous workflow access returns
401, caller-supplied evidence returns 400, reviewer proposal creation and
proposer self-approval return 403, a valid proposer/reviewer sequence succeeds,
and execution remains disabled (503). The browser-facing proxy rejects approval
creation through the investigation route (404) and cross-origin workflow POSTs
(403). Approvals are exercised against the same agent separately from the UI;
there is no claim of a browser-driven complete approval lifecycle here.

Private synthetic execution artifacts, ignored by Git:

- `local/results/step74/http-browser.json`: actual workflow reports, viewport
  results, HTTP evidence request count and zero provider calls.
- `local/results/step74/cloud-browser.json`: reports/citations, viewport results
  and two mocked provider calls, explicitly real_inference=false.
- `local/results/step74/airflow-regressions.log`: disposable database test output.

## Airflow, reconciliation and independent regression evidence

`local/run_step74_airflow.py` creates a new internal Docker network and a new
PostgreSQL 17 container with tmpfs storage, runs the existing Airflow test image
against the current repository mounted read-only, then stops/removes only its
own resources. No existing database, migration or volume is changed/deleted.
The tests cover DAG topology/callables, reconciliation on real migrations in
disposable databases, synthetic financial inconsistencies, snapshot consistency,
read-only sessions and V6 SELECT-only login restrictions.

These tests verify Airflow workflow logic plus real PostgreSQL behavior. They
do **not** execute a real Airflow scheduler/DAG run in Step 74. Agent Airflow
collector/detection tests use mocked Airflow API documents; UI reconciliation
tests are component tests. These independently passing components must not be
interpreted as a connected scheduler -> reconciliation -> agent -> dashboard run.

A new `test_reconciliation_rag_boundary.py` runs a real graph with mocked Airflow
FAIL evidence: the reconciliation incident and summary remain in the report,
retrieval returns no_match, RCA returns no_retrieval_match, and the supplied
provider receives zero calls. No unsupported financial diagnosis is invented.

## Exact verification results

| Verification | Result |
| --- | --- |
| Opt-in Chromium/agent/RAG integration, two profiles | **2 passed in 50.06s**, four viewport executions |
| Selected existing agent suites: Airflow, workflow, investigation, RAG, cloud RAG, security, approval/remediation/reliability process integrations | **132 passed in 66.84s** |
| New reconciliation/RAG boundary regression | **1 passed in 3.64s** |
| Airflow DAG/runtime/reconciliation suite, isolated PostgreSQL | **45 passed in 16.80s** |
| React incident/governance/reconciliation suites | **55 passed**, three test files |
| Frontend TypeScript check | **Passed** |

Total executed pytest/Vitest cases: **235 passed, zero final test failures**.
The full 535-test agent baseline from Step 73B was not repeated; relevant suites
and the new connected tests were run. The new browser test is explicitly opt-in
and skips in ordinary runs without `BANKOPS_STEP74_BROWSER=1`.

Initial infrastructure attempt failed before tests because Docker's automatic
network address pool was exhausted by existing networks. The harness now
inspects occupied subnets and allocates a non-overlapping internal subnet;
the subsequent complete run passed. Existing networks were left untouched.
Vite emitted its existing future native-config-loader warning, without test
or typecheck failure.

Reproduce from `agent`:

```powershell
$env:BANKOPS_STEP74_BROWSER='1'
.\.venv\Scripts\python.exe -m pytest tests/test_step74_integration.py -v -W error -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_reconciliation_rag_boundary.py -q -W error -p no:cacheprovider
```

The browser harness requires existing frontend dependencies and installed
Chromium. From repository root, run
`agent/.venv/Scripts/python.exe local/run_step74_airflow.py` for the isolated
Airflow/database suite; it requires the existing test and PostgreSQL images.

## Running development stack checks

All nine bankops-step67-4c201966c1cb development containers remained healthy.
Read-only HTTP probes returned 200 for Prometheus readiness (19097), Grafana
health (13007), Jaeger services API (16687), Airflow health (18087), and frontend
monitoring health (15173). Prometheus reported one active target, up.
These are liveness/connectivity checks, not newly generated banking incidents
or proof of complete trace propagation. No development banking operation ran.

Inspection of the installed development agent returned:

```json
{"rag_settings_available": false, "provider": "disabled", "log_source_configured": false, "airflow_enabled": false, "remediation_enabled": false}
```

Thus the running image is older than the verified Step 73B workspace. It was
not rebuilt/restarted here. Final Docker inventory showed no Step 74 containers
or networks remaining, with all nine original services still healthy.

## Missing integrations and security limitations

1. **Runtime drift:** the development image does not yet contain workspace RAG.
   Source-based connected tests cannot establish that the installed stack has it.
2. **Native log connection:** the runtime agent has no configured log source.
   SafeEventLogger emits INFO events while the collector accepts WARN/ERROR.
   Synthetic WARN evidence verifies the collector path, not a native banking
   log bridge. This report does not treat that bridge as working.
3. **Airflow connection:** installed agent Airflow collection is disabled.
   A connected real scheduler-to-dashboard execution was not performed.
4. **Reconciliation AI grounding:** current RCA rule mappings/corpus cover banking
   HTTP errors, latency, transfers, availability and database-call degradation;
   they do not map reconciliation rule IDs to RAG hypotheses. The added test
   verifies the safe no-match outcome rather than obscuring this limitation.
5. **Document presentation:** backend reports expose retrieved chunk IDs/source
   references, but the dashboard does not render a retrieved-document viewer.
   Rendering hypotheses alone is not full document citation UX verification.
6. **Inference boundary:** real cloud inference remains unverified and disabled
   by default. Explicit opt-in, synthetic-only mode and checksum-approved corpus
   content are required. Operational banking evidence cannot be exported.
   Mocked inference is not real model execution or proof of causal correctness.
7. **Approvals:** human separation and disabled execution pass. There is no
   verified automatic report-to-proposal handoff; approval checks here are a
   separately initiated lifecycle on the same isolated agent.
8. **Security gates:** no HIGH/CRITICAL gate or suppression configuration changed;
   existing documented image vulnerabilities remain outside this verification.
   No new image scan or security clearance is claimed.

## Recommended next development step

Close the local integration gaps in a disposable compose environment: build the
current agent source, wire a sanitized native log source with a deliberate level
policy, enable read-only Airflow evidence, and add one actual scheduler -> agent
-> dashboard regression. Then implement the RAG citation viewer and approved
reconciliation evidence/corpus mapping. Keep operational cloud export blocked,
strict vulnerability gates and human authorization unchanged. Do not enable
autonomous banking remediation to fill these gaps.

Step 74 verification/reporting is complete, with the full-stack limitations
above explicitly unresolved. No holistic end-to-end claim is made for components
that were only exercised independently.
