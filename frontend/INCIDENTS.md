# Incident detection and AI investigation

The incidents and investigation workspaces display deterministic detection,
source status, correlated evidence and optional validated hypotheses from the agent.

## Start

Run the existing agent as documented in agent/README.md. In frontend/:

```powershell
$env:BANKOPS_INVESTIGATION_API_TARGET='http://127.0.0.1:8000'
npm run dev
```

Open /incidents or /investigation. The server-only target defaults to
BANKOPS_MONITORING_API_TARGET, then localhost:8000. It is never a VITE_* variable
or part of the browser bundle. Never put credentials into frontend configuration.
Production static hosting needs an authenticated same-origin gateway; the existing
agent evidence endpoints have no browser authentication layer.

The development/preview boundary permits only:

| Browser route | Method | Existing agent route |
| --- | --- | --- |
| /investigation-api/incidents/detect | GET | /incidents/detect |
| /investigation-api/incidents/investigate | GET | /incidents/investigate |
| /investigation-api/workflows/investigate | POST, empty body | /workflows/investigate |

Other paths/methods and query parameters are rejected before proxying. There is
no approval, remediation or financial route in this boundary. The UI supplies no
provider settings, prompts, source paths or arbitrary URLs. Backend authorization
and disabled defaults remain authoritative.

## Actual contract boundaries

Detection returns a current snapshot of deterministic rule evaluations, not a
historical incident store. The UI lists actual triggered rules and preserves
healthy, insufficient-data and unavailable conditions. Severity is explicitly
**Not provided by API**. No fabricated incident IDs, severity rankings, confidence
percentages, incident timelines or explanations are assigned.

Filtering/search apply locally to the current rule snapshot. Rule detail links
use the existing rule ID as frontend-only selection context. Neither report API
supports incident-ID targeting; evidence collection and workflow execution collect
new global snapshots, not a historical report for that rule. Refresh detection
never runs investigation or an LLM. Collection is manual; no polling or automatic
RCA occurs. Stale detection is marked after a conservative 60-second freshness
limit. No-incidents messaging requires fresh complete healthy evidence; zero
triggered rules with insufficient data does not establish that there are no incidents.

Collect evidence calls the existing GET investigation endpoint. It displays
observed metrics, returned-trace/log counts, source availability, bounded trace
summaries and span categories, sanitized WARN/ERROR events and exact-ID correlation
summaries. No raw messages, stack traces, HTTP paths, attributes, credentials or
prompts are displayed. Exact-ID matches establish identity, never causality.

The timeline uses only backend start/detection/completion/analysis timestamps.
Reports remain immutable UI snapshots with their capture timestamp, clearly
separated from later detection refreshes. A captured report does not claim an
incident has been resolved. Partial/unavailable sources and source truncation are
preserved. Reports are held in memory across in-app navigation, not persisted to
localStorage or a new backend store. Reload discards them.

## Explicit AI action

Run AI RCA opens a native confirmation dialog. Only Confirm AI investigation
issues POST /workflows/investigate, without a body. The existing LangGraph workflow
runs detection, evidence collection, assembly and RCA. Its backend provider remains
disabled unless an operator configures it server-side. The frontend cannot enable
inference. A configured provider may incur an inference request; the dialog explains
this. There are no automatic retries. Duplicate clicks are guarded synchronously;
all collection controls are disabled during an active request.

The response must say root_cause_confirmed=false. Only fixed hypothesis kinds,
reported low/moderate confidence, existing compatible evidence references, bounded
uncertainty categories and recommended investigation steps are accepted. Reference
IDs, source type, support compatibility, observation category and timestamp are
checked against the actual returned rule/span/log records. Unsupported kinds,
references, confidence values or confirmed-root-cause claims are rejected.

Observed facts appear separately from hypotheses. Disabled inference, inadequate
evidence, timeouts, rate limits and provider validation failures retain explicit
undetermined reasons. HTTP/schema failures show an investigation failure, without
reclassifying otherwise valid detection as unavailable. Old reports remain marked
with their original timestamp. An aborted/failed client request may already have
started backend inference; repeating requires another explicit confirmation.
No approvals, remediation or financial writes are initiated.

## Limits and accessibility

DTOs are projected through an allowlist. Metric parsing reuses Monitoring's strict
units/names/value checks. Trace/span names and log categories are fixed enums;
trace/span/correlation identifiers are format-validated. Responses are streamed
with a 2 MiB cap. Detection/evidence deadlines are 40 seconds; workflow deadline
is 70 seconds, covering existing collector/provider timeout limits. Requests are
cancelable on application unmount; no workflow is automatically restarted.

Accepted reports retain existing source maxima: 50 traces, 2,000 total spans,
500 logs and 500 correlation groups. To bound rendering, trace details show the
first 20 traces and 20 spans each, explicitly labeled; correlation summaries show
20 groups. Logs show 50 initially with a functional show-more control up to the
source limit. Source truncation is visible. Missing samples never become zero.

Native confirmation focus trapping, semantic headings/tables, labeled filters,
status/error announcements, keyboard controls, responsive cards and theme tokens
reuse the existing design system. Animations remain lightweight and respect
reduced motion. No new runtime dependencies were added.

## Isolated synthetic integration

The separate helper testing/incident_agent.py imports the unchanged agent app,
real detector, report assembly, LangGraph workflow and RCA validator. Only evidence
collectors are replaced by deterministic synthetic in-memory sources. It binds to
localhost:18060 (or 18061), configures no approval DB, disables remediation/Airflow
and external LLM providers, and never calls banking or monitoring systems.

Default RCA is disabled. --fake-rca explicitly installs an in-memory test provider
which returns bounded JSON; it is not an LLM or HTTP adapter. It cannot make paid
calls. The real RCA validator still grounds and validates that response.

Run from frontend/, in separate terminals:

```powershell
# Terminal 1: existing Python 3.12 agent environment
../agent/.venv/Scripts/python.exe testing/incident_agent.py --port 18060
# Add --fake-rca only for the second, explicitly synthetic provider case.

# Terminal 2
$env:BANKOPS_INVESTIGATION_API_TARGET='http://127.0.0.1:18060'
npx vite --host 127.0.0.1 --port 5176 --strictPort

# Terminal 3
$env:BANKOPS_SYNTHETIC_INCIDENTS='step60-local-only'
npx playwright test --config playwright.incidents.config.ts
# For a backend started with --fake-rca, additionally set:
# $env:BANKOPS_SYNTHETIC_RCA='fixture'
```

The live test checks a synthetic trace/correlation fingerprint before any POST.
Do not aim this test at a real provider. Normal Chromium tests mock APIs and never
contact live services. Existing banking and monitoring opt-in configs stay separate.

## Actual verification: 2026-10-16, America/Chicago

| Check | Actual result |
| --- | --- |
| Component/API-mocking suite | 61 passed across four files |
| Full desktop/mobile Chromium regression suite | 20 passed |
| Real FastAPI/LangGraph, disabled RCA | 1 isolated browser test passed |
| Real FastAPI/LangGraph, in-memory test provider | 1 isolated browser test passed |
| ESLint, strict TypeScript, formatting | Passed |
| Production build | Passed; incident/investigation lazy chunk about 7.7 KB gzip |

The frontend suite includes existing banking and monitoring regressions. Coverage
includes real rule filtering/selection, fresh no-incidents versus insufficient
data, source failures, partial evidence, separate evidence/hypothesis views,
explicit confirmation/cancellation, duplicate-click protection, disabled RCA,
invalid references/confidence/confirmed-cause claims, schema rejection, privacy
allowlisting, request cancellation and safe errors. Desktop, mobile and isolated
workflow screenshots were visually inspected. No external model quality or paid
provider was tested. Banking, agent and Airflow unit suites were not rerun because
their code/contracts were unchanged; the isolated tests execute the real agent
detector, HTTP routes, assembler, graph and RCA validator. V1–V5 SHA-256 hashes
match the pre-existing values.

Both real-HTTP isolated cases passed: disabled provider returned undetermined with
reason disabled; explicit synthetic provider returned a grounded HTTP-error
hypothesis with reported confidence low, rule.high_http_error_rate support and
causality_unconfirmed uncertainty. Both used real LangGraph execution and actual
FastAPI serialization. One workflow POST occurred only after confirmation per
case. GET evidence did not invoke RCA. Proxy attempts to call approval routes,
GET workflows or supply provider query parameters were rejected with 404.

No external LLM, banking API/database, approval, remediation or Airflow calls were
made. These are isolated synthetic integration results, not production incident
or real-model quality validation. Real model/provider behavior remains backend
configuration dependent. No credentials were required or printed.

Temporary localhost verification processes were stopped after the checks. Existing
development services were left running. Normal UI use needs an agent at its
configured server-side target; unreachable services are shown explicitly, never
replaced with demo data. No new persistence or historical incident API was added.
