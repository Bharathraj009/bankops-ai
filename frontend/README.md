# BankOps AI operations workspace

React, TypeScript and Vite dashboard for banking, customer identity, read-only
monitoring, incident investigation, reconciliation and human approval workflows.
The `/banking` workspace requires an explicit operator credential; customer
operations use the separate authenticated [Customer Banking workspace](CUSTOMER_BANKING.md).
See [security boundaries](../SECURITY.md) and the [complete local platform](../local/README.md).

Milestone verification sections below preserve dated implementation evidence.

## Run

Use Node 22 LTS and npm. From frontend/:

```powershell
npm ci
$env:BANKOPS_BANKING_API_TARGET='http://127.0.0.1:8080'
npm run dev
```

Open http://127.0.0.1:5173/banking. Vite proxies only /api/v1 to the configured
backend. Set the target before starting/restarting Vite; it is server configuration,
not a VITE_* browser variable. No database credentials or API keys belong in this
frontend. Preview uses the same proxy setting on localhost:4173. Production static
hosting requires an appropriate same-origin /api/v1 reverse proxy and index.html
history fallback; the Vite proxy is not part of the static build.

## Banking behavior

- Load an account by UUID or create a USD account using accountNumber (max 64).
  The server generates IDs and opening balances are always zero. No balance field
  is accepted or sent by the form.
- The account directory contains accounts loaded or created in this browser
  session, not the entire bank. Account search is local to that directory.
  The existing backend has no list-accounts or global transaction-search API.
- Cards show real, last-fetched balances and account details. Refresh requests
  fresh account data and history; failed reads do not fabricate zero balances.
- History comes from the existing ledger-derived completed-transfer endpoint.
  Ten entries per server page, newest first. Direction and transfer-ID filters
  apply only to the current page. Raw ledger postings are not exposed by the API.
- Find a transfer by ID, or open details from history. Only documented public
  DTO fields are rendered; idempotency keys/internal database fields are excluded.
- Transfers require distinct UUIDs and positive USD decimal amounts with at most
  two fractional digits and 17 integer digits. Decimal values are preserved as
  strings, validated without floating point, and sent as exact numeric JSON tokens.
  Backend authorization, funds checks and atomic financial protections remain
  authoritative.
- Review the source, destination and amount in a native confirmation dialog,
  then explicitly confirm. A synchronous submission guard prevents double clicks.
  A cryptographically generated key is bound to the exact request. Unknown outcomes
  retain the original key and lock edits; explicit retries reuse the same body/key.
  There are no automatic write retries. Definitive 400/404/422 failures allow edits.
  Conflicts and unknown outcomes retain the original attempt for investigation.
- Close an unsubmitted review to edit/cancel. Pending dialogs cannot be dismissed.
  Account creation is disabled while a transfer attempt is unresolved. Navigation
  is guarded during unresolved transfers; leaving Banking now clears operator
  authority and loaded records. Refresh/closing the tab prompts before discarding
  an unresolved attempt. Verify history after losing an uncertain request key.

## Privacy, accessibility and limitations

Account data and retry keys remain in memory, not localStorage, URLs or console
logs. Only theme/sidebar preferences persist. **A forced reload or closed tab loses
an unresolved retry key. Do not recreate an uncertain transfer; check backend
records with an authorized operator first.** Cross-tab duplicate intent protection
and durable transfer drafts require a future authenticated server workflow.

The banking backend now authenticates operators and customers separately. Unlock
`/banking` with the configured operator key; use `/customer` for customer login,
owned accounts and private history. Keys/tokens are held only in memory. Vite
does not automatically supply operator credentials. Error bodies are never echoed,
and redirects are rejected by the client. Production identity remains out of scope.

Native dialogs, keyboard navigation, labeled forms, responsive tables, live status
messages, route/account loading states, dark/light themes and reduced-motion
support are retained. Reliability workspaces connect independently through the existing agent APIs.
No fake metrics, balances or activity are generated in the application.

## Monitoring

Set BANKOPS_MONITORING_API_TARGET in the Vite server environment to the existing
FastAPI agent (default http://127.0.0.1:8000), restart Vite, and open /monitoring.
The browser uses only two allowlisted read-only same-origin endpoints. Refresh is
Off/15/30/60 seconds. Charts show locally observed snapshots, not historical range
queries; the underlying metric window remains five minutes. Missing data never
becomes zero or healthy. See [MONITORING.md](MONITORING.md) for setup, contracts,
actual verification and limitations. Incidents and AI Investigation are also integrated.

## Incidents and AI investigation

Set BANKOPS_INVESTIGATION_API_TARGET in the Vite server environment to the existing
agent (defaults to the monitoring target, then localhost:8000). Open /incidents or
/investigation. Detection refresh and evidence collection are read-only. Run AI
RCA requires confirmation and may invoke a provider only if configured server-side;
the frontend cannot enable inference. No automatic approval/remediation occurs.
Severity and historical incident records are not supplied by the current API.
See [INCIDENTS.md](INCIDENTS.md) for contracts, privacy, isolated synthetic
verification, setup and limitations.

## Human approvals and remediation

Set BANKOPS_GOVERNANCE_API_TARGET in the Vite server environment to an independently
configured agent, then open /approvals or /remediation. Load a real proposal by UUID.
Enter a single role credential into the password form; it stays in memory only.
The backend authorizes each action. Approve/reject, allowlisted read-only execution,
and recorded-result verification require separate explicit confirmations. No backend
features are enabled by the UI and no mutation is automatically retried.

The API provides no global proposal list or personal actor identities. Proposals
come from the existing trusted proposer integration; this UI does not create them.
See [GOVERNANCE.md](GOVERNANCE.md) for contracts, credential handling, isolated
SQLite/browser verification, actual results and limitations. Clear the credential
and records when finished. Reconciliation now reads sanitized Airflow evidence; see RECONCILIATION.md.

## Checks

```powershell
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run format:check
npm run build
```

Chromium tests use the local Playwright browser cache and mock all banking API
calls. They never write to the development database. For a fresh machine install
Chromium with npx playwright install chromium, using PLAYWRIGHT_BROWSERS_PATH set
to frontend/.cache/ms-playwright. See BANKING_VERIFICATION.md for actual isolated
API verification and its separately opt-in browser test.

## Reconciliation

Step 62 connects `/reconciliation` to sanitized Airflow evidence through a GET-only
agent proxy. It includes run/task states, check summaries, filters, details,
refresh and freshness warnings. Set BANKOPS_RECONCILIATION_API_TARGET server-side
before starting Vite if a separate agent is used. No DAG triggers or Airflow
credentials are available in the browser. See [RECONCILIATION.md](RECONCILIATION.md)
for setup, isolated verification, results and API limitations (execution durations
are not available in the existing contract).

Actual Airflow-to-agent-to-browser verification, the single authorized read-only
run, natural stale expiry, and remaining limitations are documented in
[LIVE_AIRFLOW_VERIFICATION.md](LIVE_AIRFLOW_VERIFICATION.md).
# Unified local Docker (Step 67)

See [the complete platform runbook](../local/README.md). The container builds the
React assets and runs the existing local Vite preview/proxy as the non-root `node`
user at http://127.0.0.1:15173. Its only writable application directory is Vite's
temporary config directory. Banking requests preserve the caller's operator or
customer credential; approved reliability routes use a separate server-side
agent token. Customer APIs remain disabled in this stack. Authenticated banking
and reliability proxy checks, cross-origin denial, 104 component tests, lint and
TypeScript passed. This remains a local preview server, not a production gateway.
