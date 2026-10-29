# Customer Banking — Step 64

The `/customer` workspace uses separate Spring Security customer authentication.
`/banking` remains the operator workspace, requiring explicit operator unlock.
No customer, operator or governance token is stored in localStorage/sessionStorage.

## Local setup

Use an explicitly selected development/test PostgreSQL database and the normal
Spring Boot dev launch procedure. Review and back up an existing database before
allowing Flyway V6 to run; this task did not migrate the development database.
V6 adds identity, session and ownership metadata without assigning old accounts.

```powershell
# In the backend launch shell; retain the documented database configuration.
$env:BANKOPS_CUSTOMER_ENABLED='true'
# Step 65 requires a provisioned bankops_runtime connection; migrate separately.
# BANKOPS_BANKING_API_TOKEN must be a separately generated secret from your
# environment/secret manager if operator access is required. Never use cus_*.
./mvnw.cmd spring-boot:run '-Dspring-boot.run.profiles=dev,db-secure'
```

In `frontend/`, with dependencies installed:

```powershell
$env:BANKOPS_BANKING_API_TARGET='http://127.0.0.1:8080'
npm run dev
```

Follow the [database security setup](../database/README.md) before first launch.
Normal application startup no longer runs Flyway with runtime credentials.

Open `http://127.0.0.1:5173/customer`. Register a lower-case local alias and a
12–72 character password (at most 72 UTF-8 bytes), then sign in separately.
Open a USD account: account ID, account number and ownership are server-assigned,
with zero opening balance. Registration verifies login possession, not legal
identity/KYC. Existing ownerless accounts cannot be claimed or accessed here.

Sessions expire after 15 minutes and are not refreshed. Sign out explicitly to
revoke a session. Reloading or leaving the workspace forgets its in-memory token;
the server-side session remains valid until expiry unless explicitly revoked.
`prod`/`production` always disable customer routes, even with the flag enabled.

## API contract

The browser uses `/customer-api`, which Vite rewrites to `/api/v1/customer`.
It forwards the caller's customer bearer header without injecting operator keys.
The static build needs an equivalent trusted same-origin reverse proxy; Vite
proxy behavior is not bundled into production assets.

| Method/path under `/api/v1/customer` | Request/result |
| --- | --- |
| POST `/register` | `{username,password}` → 201 `{id,username}`; no automatic login |
| POST `/login` | `{username,password}` → 200 `{token,expiresAt}` |
| GET `/me` | Customer Bearer → `{id,username}` |
| POST `/logout` | Customer Bearer → 204, revokes current token |
| GET `/accounts?page=0&size=20` | Only owned accounts, with pagination metadata |
| POST `/accounts` | `{}` or `{currency:"USD"}` → 201 owned zero-balance account |
| GET `/accounts/{id}` | Owned account only; foreign/missing → 404 |
| GET `/accounts/{id}/transactions?page=0&size=20` | Owned ledger-derived completed incoming/outgoing postings |
| POST `/transfers` | `{sourceAccountId,destinationAccountId,amount}` plus `Idempotency-Key`; 201 new / 200 matching retry |
| GET `/transfers/{id}` | Sender-owned transfer only; foreign/recipient/missing → 404 |

Customer accounts return the existing account DTO: ID, account number, currency,
balance and creation timestamp. Sizes are 1–100; page must be nonnegative. Transfer
DTOs contain ID, **owned source** account ID, amount, currency, status and timestamp;
recipient private details/destination ID are not returned. History returns transfer
ID, timestamp, direction, amount, currency and status, plus pagination metadata.

A source must belong to the authenticated customer; a destination must have a
customer owner. Sending to another customer is allowed, without looking up their
private details. Ownerless/system-reserve destinations are not eligible. Customer
operations cannot access dev funding/bootstrap, operator or approval endpoints.
Authentication failures return safe 401; disabled routes 503; malformed inputs
400; conflicts 409; financial rejection 422. No database error bodies are rendered.

## Write safety and UI behavior

The UI confirms each transfer and freezes the exact body/idempotency key. A
synchronous guard prevents double submission. No financial write is automatically
retried. An explicit retry reuses the original request/key, including after an
uncertain outcome, while the same customer's in-memory attempt exists. Check
history before creating another transfer if that state was lost on reload/exit.
Backend service ownership checks and all financial triggers remain authoritative.

Operator access uses a separate password-style unlock form and GET
`/api/v1/operator/me`. The entered operator key stays in private memory and is
cleared on lock, authorization failure or workspace exit. Customer login never
grants operator access. Entering customer banking also clears cached governance
credentials; proposer/reviewer authority is still enforced by the agent.

## Actual verification — 2026-10-27

- Banking: **213 tests passed** on isolated PostgreSQL; agent: **487 passed**.
- Frontend: **104 component/API tests**, **32 desktop/mobile Chromium tests**;
  lint, typecheck, formatting and production build passed.
- One real isolated Chromium workflow passed against the packaged backend with
  V6 and a unique schema on PostgreSQL port 55464. Synthetic reserve funding and
  a $250 transfer produced **$750/$250** customer balances. Matching retries,
  foreign-account/source denials, recipient history privacy, logout revocation
  and explicit operator unlock were verified.
- Read-only aggregate checks reconciled all preserved test attempts: $10,000
  total balances/opening balances, zero balance mismatches and zero invalid
  completed postings. Development banking data and V1–V5 were unchanged.

Tests: `npm test`, `npm run test:e2e`, `npm run lint`, `npm run typecheck`,
`npm run format:check`, `npm run build`. `playwright.customer.config.ts` is a
separate opt-in real test; it requires the test-only fixture launcher, explicit
`BANKOPS_ISOLATED_CUSTOMER=step64-local-only`, packaged JAR and dedicated PostgreSQL
on 55464. It must never target development banking. Its generated test credential
manifest/logs stay under ignored `.cache/step64`; no credential trace/video is
recorded. The launcher accepts `.cache/step64/stop-request` to stop only its own
children and remove its own synthetic manifest, without deleting test DB data.

See [SECURITY.md](../SECURITY.md) for the full architecture, limitations and
production-disabled defaults. No existing account-ownership assignment mechanism,
MFA, password recovery, KYC, production customer rollout or paid identity service
was introduced.
