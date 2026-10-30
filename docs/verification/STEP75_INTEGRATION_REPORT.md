# Step 75: real Airflow-to-dashboard integration

Verification date: 2026-10-29. **PASS: an actual scheduler-created reconciliation
run reached the React dashboard through the real Airflow API, FastAPI,
LangGraph and local RAG.** No cloud inference was used.

## Features implemented

- Rebuilt `bankops-step75/agent:local` from the current workspace, including the
  real four-node LangGraph, RAG, optional cloud adapter and new reconciliation
  evidence mappings. Rebuilt `bankops-step75/frontend:local` with the citation UI.
- Added RAG kinds for validated reconciliation integrity failures, evidence gaps
  and workflow failures. They derive only from triggered Airflow incident rules.
  Reconciliation analysis requires RAG; legacy RAG-disabled behavior is preserved.
- Added a reviewed fictional reconciliation runbook with stable SHA-256 source
  IDs. INSUFFICIENT_DATA is explicitly distinguished from financial corruption.
- Added `LOG_INCLUDE_INFO=false` by default. Explicit opt-in accepts native
  SafeEventLogger INFO outcomes through the existing bounded JSONL projection.
  INFO events never become warning evidence or causal hypothesis support.
- Connected native banking stdout, already filtered by SafeLogFilter, through a
  fixture-only tee/shared volume mounted read-only by the agent. No fabricated
  native events or customer operations are used by the Compose scenario.
- Connected the existing authenticated GET-only Airflow collector using a viewer
  token and a fixture TLS front door. `AIRFLOW_CA_FILE` explicitly trusts a local
  read-only PEM; certificate and hostname verification remain enabled. HTTPS
  requirements for non-loopback endpoints were not relaxed. The TLS front door
  forwards fixed-resource GETs only and has a TLS-validating health endpoint.
- Added an expandable React citation viewer. It validates bounded source IDs,
  document hashes/reference formats, duplicates, hypothesis support and cited
  IDs; renders reviewed content as escaped text; offers no outbound document
  links; and hides titles/body of unreviewed local documents. Review flags are
  computed server-side from the reviewed corpus hash allowlist, not model output.

## Disposable execution design

`local/run_step75.py` uses the existing isolated Compose generator. It creates a
fresh project, credentials, networks and volumes; never restarts development
services; binds interfaces only to localhost; and removes its own containers and
networks afterward without deleting any volumes. Only required services are
started; Grafana is not part of this scenario.

The fixture copies the existing DAG and changes only that copy's cron to every
minute and retry count to zero. All four actual project task functions execute
under the actual Airflow scheduler/LocalExecutor. The production daily cron,
retry policy and existing migrations are untouched. The harness unpauses the
fixture DAG, makes no manual dagRuns POST, and requires a run_type=scheduled
terminal run before proceeding.

The controlled incident temporarily removes the reconciliation reader's SELECT
permission on schema-history metadata in the disposable database. Connectivity
and SELECT 1 still succeed, but reconciliation cannot validate its source. The
real reconciliation function therefore returns INSUFFICIENT_DATA; validators
fail as designed. The original permission is restored before the final snapshot.
The cluster's hardened database authentication policy is unchanged. No
banking table or record is altered to manufacture a financial violation. The
fixture's migrated banking database has zero accounts, transfers and ledger
entries, with a before/after snapshot and migration hash comparison.

The agent uses its production Airflow API parser to obtain bounded task states
and XCom aggregates, generates a reconciliation incident, executes the real
LangGraph, retrieves reviewed documentation and returns a deterministic report.
The browser explicitly requests investigation through the real frontend proxy.
This is pull-based evidence ingestion on an authorized investigation request,
not a new background incident watcher, webhook or automatic remediation system.

## Regression and build results

- Final complete agent suite: **544 passed, 2 skipped in 123.15s**. The skips are
  the explicit opt-in Step 74 standalone browser tests; Step 75 has its own real
  Compose/browser verification. No failing agent tests remain.
- Focused Airflow/config/RAG/cloud-mock/CA checks: **108 passed in 6.75s**;
  these overlap the complete suite and are not additional unique tests.
- React incident/citation/governance/reconciliation suites: **62 passed**, four
  files. TypeScript, ESLint (zero warnings) and selected Prettier checks passed.
- Java 21 StructuredLoggingIntegrationTests, LoggingFailureIntegrationTests and
  ApiSecurityFilterTests: **7 passed**, no failures/errors/skips. A separate fresh
  tmpfs PostgreSQL test container was stopped afterward. Any account/transfer
  fixtures in these existing regression tests belong only to that disposable DB.
- Agent and frontend Docker builds passed. No unrelated image rebuilds occurred.

An existing test initially caught reconciliation inference becoming reachable
without RAG. The code now requires the reviewed RAG path; that test passes
unchanged. A new UI test initially clicked while detection was loading; it now
waits for detection readiness without changing application controls.

## Actual scheduler, LangGraph and browser evidence

Successful project: `bankops-step68-1e618f80e798` (the existing generator retains
its Step 68 naming prefix). Fixture directory:
`local/results/step68-c5bb3ea2c60a`. Machine-readable evidence is in ignored
`local/results/step75/report.json` and the generated fixture's redacted logs.

Actual scheduler evidence:

| Field | Observed value |
| --- | --- |
| DAG | bankops_daily_reconciliation |
| Run ID | scheduled__2026-10-29T21:24:00+00:00 |
| Run type | scheduled |
| Started | 2026-10-29T21:24:10.992369Z |
| Ended | 2026-10-29T21:24:23.694209Z |
| validate_read_only_connectivity | success |
| execute_reconciliation | success |
| validate_results | failed, expected for unavailable evidence |
| execution_summary | failed, expected for unavailable evidence |
| Overall DAG state | failed, expected controlled incident |
| Manual DAG trigger POSTs | zero |

The failed DAG is the intended incident stimulus, not a failed integration test.
The API collector returned status=ok, outcome=insufficient_data and validated
summary_status=INSUFFICIENT_DATA. Detection triggered
`reconciliation_insufficient_data`; it did not infer a financial violation.

The actual frontend workflow POST executed the real four-node LangGraph in the
rebuilt agent. Its report returned matched local retrieval, successful Jaeger
and native log sources, and RCA reason=disabled with no confirmed cause. The
initial captured report had ten traces and ten INFO log events; later browser
reports contained twelve native INFO events, with zero WARN/ERROR events.
The overall evidence status remains **partial** rather than being promoted to
complete: banking availability is observed, while six idle banking traffic/rate
metrics are missing. Trace/log samples are not truncated. This is displayed
honestly; no transactions or observations were invented to fill missing metrics.

Actual Chromium checks passed at desktop 1440x1000 and mobile-sized 390x844:
both observed the real scheduler summary and incident, expanded the citation
viewer, and displayed source `doc.reconciliation.4c433b2cbde0.c000` with
`corpus://synthetic/reconciliation`. Both returned matched retrieval, twelve
native INFO events and zero JavaScript errors. No frontend API interception
or fake Airflow/LLM response was used in this Compose/browser flow. Chromium
blocked non-loopback browser requests. Physical mobile hardware was not tested.

Before and after the incident, banking accounts/transfers/ledger counts were
all zero and snapshot digests matched. V1-V6 hashes matched. The temporary read
permission was restored before the final snapshot.

Final cleanup completed successfully: no containers or networks remain for the
successful fixture; its seven newly created volumes were preserved. All nine
original development services remain healthy and were not restarted/upgraded.
The existing development stack therefore remains distinct from this tested
disposable deployment. Earlier attempt volumes were also preserved.

Verified image IDs:

- Agent: `sha256:89e0afac782f8b2a52a7e18f866f091e1fbdee2dd1e6df5c2fcf05b9126c006e`
- Frontend: `sha256:1ebd671e2d0cf85aac85b2f5a5560d85aa195d655b5d5fd0df6b3ca4568c7620`

Earlier fixture attempts exposed real setup boundaries: Windows cannot reach
published APIs on wholly internal bridges; HTTPS is required outside loopback;
the proxy inherited an unrelated agent health probe; and hardened pg_hba rejects
the initially proposed extra source database. These attempts were not reported
as successful. Their ignored diagnostic reports are preserved under
`local/results/step75`. The final setup resolves them without changing the
production DAG, relaxing TLS or altering database authentication rules.

## Safety and limits

All scenario evidence is synthetic. Cloud provider and external opt-in are
disabled; no real inference or paid API call is made. Human approval and
remediation controls remain unchanged. The agent has no financial network or
database credentials; native files are read-only. The Airflow viewer cannot
read configuration. Schema-incompatible evidence never establishes a financial
violation or confirmed root cause.

The TLS front door is fixture infrastructure: the agent-to-proxy hop verifies
TLS; proxy-to-Airflow HTTP is confined to the disposable API network. It is not
a claim that the Airflow server itself has production TLS configured. Viewer
JWT provisioning is explicit and short-lived; automatic rotation is not added.
The fixture tee is not a production rotating log pipeline; collector read sizes,
time windows and event counts remain bounded. Localhost-published API/web bridges
are retained for Windows access; finance, metadata and telemetry stay internal.

HIGH/CRITICAL workflow gates and authentication/authorization policies are not
weakened or bypassed. These application integration tests do not clear existing
documented image vulnerabilities. No new vulnerability-scan clearance is claimed.
No GitHub push, deployment, volume deletion or real customer-data access occurs.

## Files changed in Step 75

- `agent/src/bankops_agent/config.py`, `evidence/logs.py`, `evidence/airflow.py`:
  explicit native INFO opt-in and verified custom CA support.
- `agent/src/bankops_agent/rag/models.py`, `rag/retrieval.py`,
  `rag/corpus/reconciliation.json`, `rca/analysis.py`: reviewed retrieval metadata,
  reconciliation mapping and grounding while preserving disabled-RAG behavior.
- `agent/tests/test_step75_evidence.py`, `test_reconciliation_rag_boundary.py`:
  INFO privacy/classification, reconciliation grounding/citation checks and CA
  verification tests; update the former no-mapping regression to the new behavior.
- `agent/.env.example`, `agent/RAG.md`: safe defaults/configuration and current UI.
- `frontend/src/incidents.ts`, `pages/Incidents.tsx`, `test/RagCitations.test.tsx`:
  strict citation parsing/viewer and security regressions.
- `local/run_step75.py`, `local/airflow_tls_proxy.py`, `local/step75_browser.mjs`,
  `local/run_step75_backend.py`: reproducible disposable integration/regression
  harnesses. `STEP75_INTEGRATION_REPORT.md`: this report.

Unrelated pre-existing workspace changes were preserved.

## Final status and remaining work

Step 75 is complete for the controlled scheduled evidence-gap scenario, including
real native evidence and desktop/mobile-sized browser rendering. It does not
establish a real financial-corruption incident, automatic background ingestion,
real LLM inference, production readiness or cleared vulnerability gates.
Remaining operational work includes rotating native log capture, durable
read-only Airflow token provisioning/refresh, direct production TLS configuration,
and adequate real traffic evidence for complete banking metrics. These are not
enabled on the retained development stack by this verification task.
