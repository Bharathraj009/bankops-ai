# Reconciliation workspace

Real local Airflow verification completed on 2026-10-27 is documented in
[LIVE_AIRFLOW_VERIFICATION.md](LIVE_AIRFLOW_VERIFICATION.md), separately from the
original synthetic contract verification below.

Open `/reconciliation`. It reads the existing agent's `GET /incidents/detect`
and projects the sanitized `airflow` field.
There are no direct Airflow calls, DAG triggers, workflows or financial writes.

## Configuration

Before starting Vite, optionally set the **server-only** target:

```powershell
$env:BANKOPS_RECONCILIATION_API_TARGET='http://127.0.0.1:8000'
npm run dev
```

This falls back to `BANKOPS_MONITORING_API_TARGET`. The browser requests only
`GET /reconciliation-api/incidents/detect`, with credentials omitted. Both Vite
and preview reject other paths, methods and query strings. Production static
hosting needs an equivalent same-origin reverse proxy and appropriate access
policy; Vite's proxy is not part of the static build.

Independently configure the existing agent's Airflow collector and viewer token
server-side. Never put Airflow credentials or URLs in `VITE_*` variables, source,
or browser storage. This step does not enable disabled backend features.

## Result semantics and limits

- Newest observation first; filters apply only to the bounded returned sample.
  Details show all four expected tasks and allowlisted rule counts. Violation
  counts may overlap and do not count unique affected accounts.
- Financial violations are checker-reported findings. Task failures are execution
  problems, never proof of financial corruption. A failed downstream task can
  coexist with a recorded PASS summary, and is displayed as a task failure.
- Sample PASS requires fresh, complete, non-truncated `ok` collection, at least
  one run, and every returned run having a validated PASS outcome. Running,
  missing, disabled, partial, invalid and stale evidence cannot establish PASS.
- Collection freshness expires after 60 seconds, checked every five seconds.
  Daily runs can be older: they remain historical records, with stale warnings
  when collection expires. Failed refreshes retain records and indicate current
  evidence unavailable. No current balance guarantee or incident resolution is
  inferred from a historical PASS.
- Airflow read access describes collection reachability, not scheduler health.
  Last successful run is limited to the returned sample, not all Airflow history.
- The API supplies observation (`run_after`) and collection timestamps. It does
  **not** supply run IDs, start/end times, task timestamps, execution durations,
  or the configured collection window. The UI explicitly marks durations as
  unavailable, uses snapshot details rather than invented stable IDs, and offers
  no unsupported server pagination/date-range controls.
- Manual refresh has a 15-second deadline and no automatic retries. Responses
  are bounded to 512 KiB before JSON parsing; at most ten runs, four tasks and
  four checks per run. Unknown fields/raw messages are excluded; invalid enums,
  inconsistent PASS, duplicate tasks/checks and invalid timestamps fail safely.

## Isolated HTTP integration

From `frontend/`, use separate terminals:

```powershell
../agent/.venv/Scripts/python.exe testing/reconciliation_agent.py

$env:BANKOPS_RECONCILIATION_API_TARGET='http://127.0.0.1:18063'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5179 --strictPort

$env:BANKOPS_SYNTHETIC_RECONCILIATION='step62-local-only'
npx playwright test --config playwright.reconciliation.config.ts
```

The existing Python 3.12 agent environment runs a real unchanged collector and
detection API on 18063 against a synthetic Airflow v2 HTTP fixture on 18064. A
viewer token is generated only in server memory. Unauthenticated reads and all
writes are rejected. Aggregate test counters contain no credentials or records.
Five runs cover PASS, financial FAIL, task failure with recorded PASS,
INSUFFICIENT_DATA, and running execution. Prometheus evidence is synthetic.
No banking database, live scheduler or LLM is contacted. This validates the
authenticated HTTP contract, not a newly deployed full Airflow scheduler.

## UI refinement

Shared tables have consistent heading typography, tabular figures and quiet
hover states; cards share subtle depth and form controls inherit typography.
Semantic statuses support both themes. Monitoring chart labels are larger,
with contained scrolling on narrow screens. Reconciliation has responsive cards,
keyboard controls, native modal focus handling and reduced-motion-aware loading.
Its lazy chunk is approximately 4.43 kB gzip; no new package was added.

## Verification results

Verified locally on 2026-10-16:

- ESLint, TypeScript checks and Prettier: passed.
- Complete Vitest suite: **96 passed**, six files. One earlier run alongside
  Chromium hit the existing banking cancellation test's five-second timeout;
  the complete standalone rerun passed with assertions and timeouts unchanged.
- Complete Chromium suite: **26 passed**, desktop and mobile. Visual screenshots
  reviewed; no page-level horizontal overflow in the reconciliation workspace.
- Isolated Airflow HTTP → real agent → Vite → Chromium: **1 passed**. Explicit
  refresh produced ten authenticated GETs (one listing, five task lists, four
  completed execution summaries). Unauthenticated upstream access returned 401;
  proxy write/arbitrary-route attempts returned 404; upstream writes remained zero.
- Production build: passed; reconciliation chunk 4.43 kB gzip. No new dependency.
- Read-only before/after fingerprints matched for all development banking rows:
  accounts **3**, transfers **2**, ledger entries **4**. V1–V5 SHA-256 hashes
  matched the pre-existing values. No banking, agent, Airflow, Compose or
  monitoring implementation was changed.

Temporary isolated services were stopped after verification. Existing services
were left running. Live scheduler behavior, scheduler health and execution
durations are outside what this contract-fixture verification establishes.
