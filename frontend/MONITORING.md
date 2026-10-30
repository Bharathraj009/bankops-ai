# Live monitoring

The Monitoring workspace reuses the React design system, responsive panels, themes,
accessible status messages and reduced-motion support.
Lightweight SVG charts have keyboard-focusable observation points, hover/focus
value tooltips and an expandable table of the latest 20 observations.

## Run

Start the unchanged FastAPI agent using its Python 3.12 environment, then in frontend/:

```powershell
$env:BANKOPS_MONITORING_API_TARGET='http://127.0.0.1:8000'
npm run dev
```

Open http://127.0.0.1:5173/monitoring. Set the target before starting/restarting Vite.
This is a server-only setting, never a VITE_* browser variable. No credentials or
Prometheus addresses belong in the frontend bundle. The agent's own Prometheus URL
remains an agent-server environment setting.

Only GET /monitoring-api/health and GET /monitoring-api/incidents/detect are exposed
through the same-origin development/preview gateway. They map to existing agent
/health and /incidents/detect. Other paths, methods and query parameters are rejected.
The detection response already includes the five Prometheus evidence metrics plus
banking availability, transfer outcome rate, and traffic-aware rule evaluations.
No agent contract was changed or duplicated. Production static hosting needs an
authenticated same-origin reverse proxy enforcing this same boundary. Existing
read-only evidence endpoints have no authentication layer; no browser bearer keys
or invented login are introduced.

## Meaning and states

API request rates are requests/second; HTTP 4xx/5xx ratios display as percentages;
histogram p95 seconds display as milliseconds. Transfer metrics are HTTP operation
outcomes/second, excluding matching retries and development funding. Failed outcomes
do not imply persisted FAILED transfers or ledger corruption.

Banking availability means Prometheus scrape-target up/down, not readiness or a
transaction guarantee. Agent health means process response only. No Prometheus,
Grafana or Jaeger process health is invented or fetched directly by the browser.

Healthy requires all fresh observations, evidence status ok and healthy backend
rules. Fresh triggered rules are Degraded; fresh banking target-down evidence is
Unavailable. Evidence connection failures or universally failed collection also
show Unavailable, with text separating monitoring availability from banking health.
Missing/stale evidence and low traffic are Insufficient data. Thresholds and traffic
minimums are evaluated by the existing agent, not invented by the frontend.

Observed zero remains zero. Missing, stale and invalid values show an em dash.
Each envelope and sample has a conservative 60-second freshness limit, at most one
second of future clock tolerance. The agent's configured freshness limit is not
exposed, so the frontend never extends its own limit. Freshness is reevaluated every
five seconds. Failed refreshes retain explicitly cached observations, show a warning,
and remove the healthy classification. Agent process health also expires.

The parser validates metric/rule categories, units, finite values, ratios,
timestamps, duplicate names and required fields. It returns only allowlisted data.
HTTP error bodies, raw labels, internal URLs and secrets are never rendered.
Client requests have a 12-second deadline, a 64-KiB response check and unmount
cancellation. Health/evidence failures are handled independently.

## Refresh and charts

Default refresh is 30 seconds, with Off/15/30/60 controls and manual refresh.
Requests do not overlap; polling pauses in hidden tabs. There are no financial
writes or automatic write retries.

The existing API supports only instant snapshots using a fixed five-minute rate
window, not historical range queries. Charts accumulate observations in memory
while this page is mounted: at most 240 samples spanning at most one hour. The
15/30/60-minute local range filters that buffer, sends no unsupported parameters,
and performs no backfill. Missing samples and observed collection failures break
lines. Tooltips show only collected observations. Early charts can have one point
or none. History disappears on navigation/reload and is not stored in localStorage.

## Actual local verification: 2026-10-16 (America/Chicago)

| Check | Actual result |
| --- | --- |
| Component/API tests | 45 passed across three files |
| Desktop/mobile Chromium regression suite | 18 passed |
| Opt-in real local monitoring Chromium test | 1 passed |
| ESLint and strict TypeScript | Passed |
| Prettier check | Passed |
| Production build | Passed; monitoring lazy chunk approximately 5.2 KB gzip |

Desktop/mobile and real-service screenshots were visually inspected. Initial test
locator ambiguity was corrected with an exact accessible control label; assertions
were retained. The final mocked and live browser suites ran sequentially. V1–V5
SHA-256 hashes match their pre-existing values. Banking/agent/Airflow test suites
were not rerun because their code and contracts were not changed; the complete
frontend suite includes the existing banking component and mocked browser tests.

Used the unchanged agent on localhost:18059, temporary Vite on localhost:5175, and
existing Prometheus. LLM and remediation were disabled, no approval DB configured,
and Airflow collection disabled in this temporary agent. Existing services and
production-disabled defaults were not modified.

Actual agent health returned HTTP 200, status ok. Detection returned HTTP 200,
insufficient_data, evidence partial, window 5m. Banking availability was 1; API
request/error rates and transfer success/failure/outcome rates were observed zeros.
p95 latency was missing/null in the idle window. The dashboard preserved the
insufficient-data state and missing latency rather than zero/healthy. No traffic
was generated to fill charts. No banking API/database calls were made.

The opt-in browser check verifies real DTO/card parity, overall state, two actual
observations, agent process health, no browser exceptions, no financial requests,
no internal URLs/secrets in page content, and non-allowlisted proxy rejection.

```powershell
# frontend/ terminal 1; existing agent must be running on localhost:18059
$env:BANKOPS_MONITORING_API_TARGET='http://127.0.0.1:18059'
npx vite --host 127.0.0.1 --port 5175 --strictPort

# frontend/ terminal 2
$env:BANKOPS_LIVE_MONITORING='read-only-local'
npx playwright test --config playwright.monitoring.config.ts
```

The default Chromium suite uses mocked monitoring endpoints and does not contact
live services. Banking live tests remain separate under their original config.
Banking code, agent, Airflow, monitoring services and V1-V5 remain unchanged.
Stop only temporary verification processes afterwards; leave existing services up.

The temporary agent and frontend processes were stopped after verification. Existing
PostgreSQL, Prometheus, Grafana, Jaeger and Airflow services were left running. Normal
frontend use requires an agent running at the configured server-side target; a
stopped/unreachable agent is shown as unavailable rather than demo data.
