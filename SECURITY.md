# BankOps AI security

Published baseline: `36a88e8`. [Application CI](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960966)
passed all four jobs. [Hosted image verification](docs/verification/HOSTED_36A88E8.md)
recorded five blocked gates, 44 unique HIGH package findings and zero CRITICAL;
banking and Jaeger passed. Strict gates include unfixed findings. Workflows build,
test and scan without deploying services or publishing container images.

See [publication verification](PUBLICATION_READINESS.md) and the
[deployment limitations](README.md#deployment-scope-and-limitations).

The milestone sections below preserve dated evidence and intermediate behavior.
Their test counts and runtime status apply to the stated milestone. Earlier
pending-publication statements do not describe the current public baseline.

## Step 63 — security audit and hardening (historical)

Verified **2026-10-27** (America/Chicago). This is a repository/local-test audit,
not a penetration-test certification or approval for a public banking deployment.
Pre-existing Step 62 working-tree changes were preserved. No production service,
development banking record, financial service/repository logic or V1–V5 migration
was changed. All financial writes in automated tests targeted disposable,
explicitly selected test databases/schemas, never development banking.

## Findings and fixes

| Severity | Verified finding | Result |
| --- | --- | --- |
| High | Spring had no HTTP authentication boundary and defaulted to all network interfaces | Default bind is now loopback. Production profiles, non-loopback binds, or an explicitly configured key require service Bearer authentication. Missing credentials in an exposed configuration fail closed with 503; invalid/missing requests return 401. Only GET health is public. |
| High | Agent evidence/workflow routes lacked deployment authentication, including the POST capable of invoking configured RCA | Added a hashed service-token boundary for production, non-loopback, or explicitly secured deployments. Unconfigured exposed instances return 503 for private routes. Existing approval endpoints retain independent proposer/reviewer authorization. |
| High | Local workflow POSTs could be initiated by cross-origin browser requests without a body; no host/origin boundary | Spring and the agent now reject unexpected hosts, foreign/null/duplicate Origins, and cross-site Fetch Metadata. Vite rejects cross-origin API traffic before forwarding. No wildcard CORS permissions or cookie authentication were added. |
| High | A broad frontend banking proxy also forwarded development funding and unsupported operations | Proxy now allows only the existing account/transfer UI operations; development funding, arbitrary routes and unsupported methods return 404. Backend dev-profile restrictions remain authoritative. |
| High/critical | Public advisories affected packaged Jackson, agent certifi and cached Airflow dependencies | Applied Jackson 2.21.7 / 3.1.7 BOM patches, certifi 2026.10.23 in agent locks, and a tested Airflow security pin set. Final OSV lookup reports no affected packages in the audited inventory. |
| Defense in depth | Financial/evidence responses lacked explicit anti-caching and browser hardening headers | Added no-store for private responses and nosniff, frame denial and no-referrer headers. Spring error-message, stack-trace and binding-detail exposure is disabled. |
| Defense in depth | Future `.env.*` files were not consistently ignored | Root ignore rules now cover secret dotenv variants, preserving example templates. No live credential was found in the scanned files. |

Spring authentication runs **before routing**, rather than matching a handful of
financial URI prefixes. Tests cover servlet context paths and semicolon path
parameters, avoiding a path-normalization bypass. Valid authentication still
passes through unchanged DTO validation, transaction services and database triggers.

The agent uses constant-time SHA-256 digest comparison, rejects duplicate Bearer
headers, and preserves correlation IDs on denied responses. Its deployment key
must be different from both approval-role keys. A deployment key cannot approve
a proposal; a proposer still gets 403 when attempting approval; the separate
reviewer can decide. Approval, execution and verification stores/audits were not
changed. Disabled remediation and inference defaults remain disabled.

## Configuration and compatibility

### Spring Boot

| Variable | Purpose |
| --- | --- |
| `BANKOPS_BIND_ADDRESS` | Default `127.0.0.1`; non-loopback binding requires an API key |
| `BANKOPS_BANKING_API_TOKEN` | Secret ASCII service key, 32–256 characters; never a URL/query/client-storage value |
| `BANKOPS_ALLOWED_HOSTS` | Explicit comma-separated host names, without ports; defaults localhost, 127.0.0.1 and ::1; wildcard rejected |

`prod` and `production` profiles require a credential for every request except
GET `/actuator/health`. A missing key leaves those private routes unavailable,
not anonymously accessible. In local loopback dev/test with no key configured,
existing workflows continue to work. Enable a key on shared/untrusted machines.
Prometheus needs Bearer configuration when the banking API key is enabled; use
an external secret file, never a committed plaintext monitoring credential.

The existing production/test funding-profile regression now sends a valid
synthetic service key and still proves the route is **404** and funding/bootstrap
beans are absent. Authentication does not silently replace that financial safety
assertion. No bootstrap, transfer or migration logic was altered.

### FastAPI

| Variable | Purpose |
| --- | --- |
| `BANKOPS_AGENT_API_TOKEN_SHA256` | Lowercase SHA-256 digest of a separately generated service token |
| `BANKOPS_AGENT_ALLOWED_HOSTS` | JSON array of explicit host names; wildcard rejected |
| Existing proposer/reviewer hash settings | Remain distinct role credentials with existing required permissions |

Production or a non-loopback host requires the deployment credential for private
evidence/investigation routes. `GET /health` remains public and approval routes
continue to use their existing role tokens. The default allowed hosts support
localhost/loopback and the local ASGI test host; configure your explicit external
hostname when deploying behind a trusted gateway. Do not reuse an LLM credential,
banking key or reviewer key as the agent deployment token.

### React/Vite

Configure **server-side only** `BANKOPS_BANKING_API_TOKEN` and
`BANKOPS_AGENT_API_TOKEN` to match the upstream services when secured. They must
not use a `VITE_*` name. Agent deployment credentials are forwarded only to the
fixed monitoring, investigation and reconciliation proxies. Governance requests
preserve the explicitly supplied proposer/reviewer token; the service key never
substitutes for a reviewer. Existing target settings and localhost binds remain.

An isolated real-Vite integration verified private service-key forwarding,
reviewer-key preservation and Origin/Host consistency. Generated keys were absent
from served HTML/client modules. A production build with synthetic server keys
also contained neither key in its assets. Existing UI tests verify credentials
stay in a private memory ref and are cleared on authorization failure/clear;
no credential storage in localStorage/sessionStorage was added.

Vite is a local development/preview server, not a production identity gateway.
For deployment use TLS and an authenticated same-origin gateway that preserves
the validated external Host/Origin and applies user permissions/rate limits.
Do not expose a service-key-bearing frontend proxy anonymously to the internet.
Do not blindly strip Origin or trust arbitrary forwarded headers to bypass checks.

### Airflow

BankOps Airflow UI remains localhost-only; metadata PostgreSQL has no published
port. The reconciliation role remains SELECT-only and tasks retain explicit
read-only snapshots and rollback. No actual banking connection or live DAG run
was made during this audit.

`airflow/security-requirements.txt` pins the patched Python dependency set in
both runtime and test images. `pip check` is mandatory during both builds. The
unused Google provider / Vertex evaluation / LiteLLM stack is excluded because
its published constraints prevent upgrading to a safe LiteLLM release. BankOps
uses none of those operators; the existing reconciliation DAG is unchanged.
Adding Google/Vertex operators later requires a new dependency/security review.

Separate patched images (`bankops-airflow-step63-security` and
`bankops-airflow-step63-tests`) were built and verified. Existing deployments were
**not replaced**. Rebuild/restart local deployments from the updated Dockerfile
to adopt it; old cached images/containers retain their old dependencies. For
production, deploy only through your authorized release process. Local SimpleAuth,
plaintext local secret files and environment credentials are not production SSO
or secret-management solutions.

## Dependency and secret checks

- `npm audit`: **0** reported advisories, including the locked frontend dev tools.
- Initial [OSV batch API](https://google.github.io/osv.dev/api/) lookup: **536**
  public coordinate queries, **26** affected inventory entries (source-specific,
  not a count of unique CVEs). It covered agent runtime lock, packaged banking
  JAR Maven metadata and installed packages in the cached Airflow runtime image.
- Final lookup: **535** public coordinate queries, **0 affected entries** in the
  patched lock/JAR/image. Dependency names/versions only were transmitted; no
  source code, secrets or financial data was sent.
- Important advisory examples include
  [certifi](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2),
  [Jackson](https://osv.dev/vulnerability/GHSA-7hhh-6rmp-j9qf), and the incompatible
  [LiteLLM branch](https://osv.dev/vulnerability/GHSA-7hp6-4w63-5g45).
- A redacted scan of tracked and nonignored working files found no provider/cloud
  keys or private-key blocks and no tracked `.env`/`.env.local`. Its sole candidate
  was `synthetic-not-a-real-key` in the mocked Groq verifier. No real key was
  printed, committed or rotated. Example dotenv files stay trackable.

The audit helper is `frontend/testing/security_inventory.py`; use `--patched`
after building the tested patched image. Results are under ignored
`frontend/.cache/step63/`. Secret-scan output contains only file/line/category,
never a matched value. Results reflect the advisory database at query time.
This is not an exhaustive historical secret scan, operating-system image scan,
or audit of every Maven build plugin, unused branch or external deployment.

## Actual validation

| Check | Result |
| --- | --- |
| Complete banking suite, including authorization HTTP checks and financial regressions | **206 passed**, no failures/errors/skips; package build passed |
| Complete agent suite, warnings as errors | **487 passed** |
| Patched Airflow DAG/reconciliation suite, warnings as errors | **43 passed** |
| Frontend component/API suite | **96 passed** |
| Desktop/mobile Chromium suite | **30 passed**, including cross-origin/proxy guards |
| Frontend lint, strict TypeScript, formatting, production build | Passed |
| Real-Vite private credential forwarding / client leakage check | Passed, isolated stub upstream only |
| Isolated patched Airflow health and RBAC | Healthy; admin/viewer login succeeds; invalid password rejected; viewer read succeeds and admin configuration returns 403 |
| Isolated patched Airflow DAG state | Paused, **0 runs**, no banking network or financial connection |
| V1–V5 | All five SHA-256 hashes exactly match Git HEAD |

The banking tests used only localhost:55463 and unique synthetic schemas. Airflow
tests created only disposable test databases on that same dedicated PostgreSQL.
The patched runtime used a separate metadata database on a private test network;
it was not joined to the development banking network. No real accounts,
transfers, balances, ledger records, triggers or production grants were changed.
No paid inference, live remediation, actual reserve initialization, or development
DAG run occurred. Temporary test services were stopped; test data/images retained.

Failed intermediate dependency resolutions were treated as failures, not ignored:
the Google evaluation constraint required removal of the unused stack, and the
OpenTelemetry Prometheus exporter was pinned to match its patched SDK. Final
images pass strict dependency checks, DAG tests and real service startup/RBAC.
An ASGI correlation test's fake hostname was adjusted to the allowed test host;
its concurrency/correlation assertions remain unchanged. No assertions or tests
were disabled to obtain passing results.

## Remaining risks / production gates

1. **Service authentication is not customer authorization.** Banking still has no
   customer ownership/tenant model. An authenticated operator can use the existing
   APIs across accounts. Add identity-bound resource permissions, human identity,
   MFA/SSO, credential rotation and access auditing before a multi-user/public
   banking deployment. Reviewer custody is still a separately held shared role
   secret, not proof of physical human presence.
2. Development database owner credentials can have broad privileges. Provision a
   least-privileged application role and separate migration principal through an
   authorized database rollout. No production/development grants were changed by
   this task. Existing API paths use parameterized queries and retain DB integrity
   triggers; that does not protect against a compromised database superuser.
3. Default loopback development intentionally remains usable without service keys.
   Untrusted local processes/users are outside that trust model. Use keys even on
   loopback when sharing a host, and never publish unprotected dev proxies.
4. TLS termination, gateway/user authentication, rate limiting, request/resource
   budgets, full container OS scanning and independent penetration testing remain
   deployment responsibilities. No public production deployment was tested.
5. Existing installed images must be rebuilt to receive dependency fixes. Zero
   advisory matches is time- and inventory-bounded, not a guarantee of no unknown
   vulnerabilities. Continue dependency and secret scanning in CI.

## Step 64 — initial customer authorization design review (superseded)

This subsection records the earlier stop before the user approved the local
identity, ownership and access policies. See the implementation below for current
behavior and actual tests.

Reviewed **2026-10-27**. **Implementation stopped at the security-critical design
boundary**, as required by Step 64's stop condition. Customer authorization is
not implemented or verified. This section records the findings and decisions
needed to implement it safely; it is not an authorization contract or rollout.

### Existing architecture and verified gaps

- Repository migrations V1–V5 contain accounts, transfers, ledger entries and
  idempotency records, but no customer table, identity-provider subject, tenant,
  account owner or ownership relationship. V3 adds the immutable opening balance;
  V4 and V5 enforce lifecycle and idempotency, not customer entitlements.
- `ApiSecurityFilter` authenticates one shared banking **operator/service** key.
  It does not establish a customer principal. The project has no configured OIDC
  issuer, audience, JWKS trust source, customer enrollment or credential issuer.
- `AccountService.get` and `transactions` use an account UUID without a principal.
  Their repository queries filter by account ID only. Account creation accepts
  accountNumber/currency and records no ownership. Account numbers, UUID knowledge
  and possession of an operator key cannot safely establish a customer's rights.
- `TransferService.get` reads by transfer UUID. Creation locks the two accounts
  in UUID order, claims a globally scoped idempotency key, posts balanced entries
  and completes atomically. It has no caller identity or source-ownership check.
  A future customer principal must be checked before any debit or idempotent
  response is returned, including a matching retry.
- Ledger-backed account history exposes the existing six-field transaction DTO;
  there is no separate raw-ledger API to secure or add. Transfer details include
  both participating account IDs, so customer visibility needs an explicit policy.
- Vite currently injects the operator banking key for all supported banking
  routes. Customer traffic must not inherit that privileged identity. Frontend
  filtering or a client-supplied customer/owner header would not fix this gap.
- FastAPI proposer/reviewer credentials are independently validated and distinct
  from the agent deployment key. They are not banking customer identities and
  must not be repurposed as such.

The current application is an operator workspace. Exposing it to customers would
permit cross-account access with the shared operator credential. No customer
access should be enabled until the missing trust and ownership boundaries exist.

### Security-critical decisions required

1. **Identity authority and login boundary.** Select the trusted customer issuer
   and provide its issuer/audience/verification configuration. No existing issuer
   can be inferred from the repository. Decide whether browser authentication
   terminates in a trusted backend-for-frontend or uses provider-issued access
   tokens. The operator proxy must remain separate in either design.
2. **Authoritative ownership enrollment.** Define who can provision customers and
   link verified identities to accounts. Existing accounts have no owner evidence.
   Do not assign them to the first login, infer owners from account numbers, accept
   client ownership claims, or automatically backfill production/development data.
   Define whether the initial model permits only sole ownership or joint accounts.
3. **Transfer participation and operator privileges.** Decide whether customers
   may credit another customer's account, which participants may read transfer
   details, and which counterparty fields may be disclosed. Define explicit
   operator permissions and who may assign ownership; the current shared service
   key must never become a customer or imply ownership-administration rights.

### Options for the next implementation

**Preferred: external OIDC identity provider.** Use Spring Security's resource
server support with an explicitly trusted issuer, audience, signing algorithms
and verification keys. Validate token signature, expiry/not-before and claims;
bind an internal customer UUID to the verified `(issuer, subject)` pair. Never
trust an arbitrary subject header, unverified JWT, token-selected issuer/JWKS
URL or client role claim. A local identity-provider instance with separately
provisioned synthetic users can support secure development without hardcoded
customer passwords. Provider choice, enrollment and trusted role mapping remain
required decisions, not defaults installed by this review.

**Alternative for an explicitly limited local foundation:** externally provisioned
opaque, per-customer tokens with hashed storage, revocation and an audited trusted
provisioner. This requires explicit selection of the token lifecycle, provisioning
authority and ownership mapping. It is not a substitute for a production identity
provider and must not silently introduce self-registration, shared customer keys,
or a homemade password/login protocol.

After those decisions, an additive migration can introduce customer/identity and
ownership metadata without changing V1–V5 or financial rows. Legacy/unassigned
accounts and the system reserve should remain inaccessible to customers until
authoritatively provisioned; they must not be auto-claimed. No V6 was created,
and no ownership backfill or real banking update was performed by this review.

### Required backend enforcement and regression plan

- Establish a typed customer principal independently of operator, proposer and
  reviewer credentials. Fail closed on missing/invalid/expired credentials and
  wrong issuer/audience; no development fallback may impersonate a customer.
- Assign newly created customer accounts from that verified principal, never a
  request owner field. Gate account/balance/history reads in services and scope
  repository queries to authorized ownership, including count/pagination queries.
  Select a consistent non-disclosing not-found policy for foreign resources.
- Check source ownership within the transfer transaction and maintain the existing
  deterministic account lock order. Prevent ownership-change races, cross-customer
  debits and authorization bypass through internal service entry points.
- Authorize transfer reads and incoming/outgoing history according to the agreed
  participation policy. Do not expose unrelated balances, ledger entries or
  counterparty details through transfer IDs learned from history.
- Namespace new customer idempotency claims by the stable internal customer
  identity, with ownership checked on every retry. Preserve existing operator
  scopes and V5 records; never delete, rebind or rewrite historical keys. Token
  rotation must not change customer identity or cause duplicate transfers.
- Retain V3 ledger-driven balances, double entry, atomic rollback, insufficient
  funds rejection and V4 terminal states. Customer authentication must not grant
  reserve funding, bootstrap, operator or agent approval/remediation permissions.
- Replace customer use of the operator proxy with the selected trusted identity
  flow. Keep keys/tokens out of source and browser persistent storage; any cookie
  session design also needs explicit CSRF, SameSite, session and logout controls.

Required isolated tests include two customers and separately authenticated
operators: own/foreign/missing account reads, balance and history pagination
isolation, forged identity/role/owner inputs, wrong token class, expired/invalid
credentials, cross-customer source debits, participant visibility, retries across
customers and token rotation, concurrent authorization/ownership attempts,
operator/proposer/reviewer separation, rollback and all existing financial
integrity regressions. Then run the banking, agent, frontend and Chromium suites
against synthetic users and isolated databases only.

### Actual Step 64 result and limitations

Only this documentation section was added for Step 64. Architecture, migrations,
security configuration, services, repositories, DTOs, proxy behavior and existing
tests were inspected read-only. No runtime service was started, live database
queried, customer credential generated, account linked or migration applied.
Application code, financial logic, V1–V5 and all prior working-tree changes remain
unchanged. The live database schema was not independently queried in this review.

No test suites were executed for this documentation-only stop, and no customer
authorization tests are claimed to pass. The Step 63 counts above are historical,
not Step 64 validation. Implementation and the requested new tests remain pending
the identity authority, ownership enrollment and access-policy decisions above.

## Step 64 — implemented customer identity and ownership

Verified **2026-10-27**, using isolated synthetic users and PostgreSQL only.
The user approved local Spring Security authentication and self-registration.
No development banking connection, ownership backfill, paid API call, production
deployment or real financial update was performed. V1–V5 SHA-256 values match
the pre-implementation values. The new V6 has only been applied in test schemas.

### Authentication configuration

- `BANKOPS_CUSTOMER_ENABLED=true` explicitly enables `/api/v1/customer/**` in
  local development. The default is **false**. `prod` or `production` profiles
  always disable these routes (503), even when the flag is true.
- Spring Security's `DaoAuthenticationProvider` authenticates local aliases.
  BCrypt cost 12 hashes are stored; passwords must be 12–72 characters and at
  most 72 UTF-8 bytes. Aliases are lower-case, 3–64 characters, using letters,
  digits, dots, hyphens and underscores. This verifies possession of a login,
  **not** KYC, legal identity, email ownership or an external customer identity.
- Registration returns a customer ID/alias and requires separate login. Login
  returns a cryptographically random 256-bit opaque bearer token with a 15-minute
  absolute lifetime. Only its SHA-256 digest is stored. Every authenticated
  request checks expiry, revocation and active customer state in PostgreSQL.
  Logout revokes that token; there is no automatic refresh or persistent login.
- The browser holds tokens only in a private client object in memory. Password
  form inputs are cleared immediately after submission. No token is placed in
  URLs, localStorage, sessionStorage, cookies, source, logs or analytics. Browser
  tests handling credentials disable trace/video capture.
- Spring chains are stateless, with form login, HTTP Basic and request caching
  disabled. There is no cookie authentication; clients explicitly send Bearer
  headers with `credentials: omit`. CSRF token middleware is disabled for these
  header-only APIs, while existing Host/Origin/Fetch Metadata guards remain.
  Introducing cookies or Basic authentication would require a new CSRF review.
- Login/registration share a process-local 30-attempt/minute limiter per actual
  remote address, bounded to 1,024 active buckets. Forwarded addresses are not
  trusted. The limit resets on restart and is not a distributed abuse defense.
  Shared-proxy users can share a limit. Malformed requests are rejected before
  BCrypt; this is not a complete denial-of-service defense.

The local BCrypt/short-lived credential design follows Spring's
[password storage guidance](https://docs.spring.io/spring-security/reference/7.0/features/authentication/password-storage.html).
The [CSRF guidance](https://docs.spring.io/spring-security/reference/7.0/servlet/exploits/csrf.html)
also explains why statelessness alone would not make cookie/Basic auth safe.

### Ownership and financial authorization

V6 adds `customers`, `customer_sessions` and `customer_account_ownership`.
Ownership has foreign keys, one owner per account and triggers rejecting update,
delete and truncate. The migration does not update existing accounts, balances,
transfers, ledger entries or idempotency records. Existing ownerless accounts,
including the system reserve, remain inaccessible to customers. There is no
claim, reassignment, ownership import or customer-role administration endpoint.

New customer accounts receive server-generated account IDs/numbers, USD currency,
zero balance and ownership from the typed authenticated principal, atomically.
Client-supplied owner, account number and balance fields are rejected. Service
method authorization and ownership-scoped queries protect account reads, account
lists, counts, balance and ledger-derived transaction history. Foreign and
unknown resources both return safe 404 responses. Pagination is bounded.

Customer transfers can debit only the authenticated customer's source account.
The destination must also be customer-owned, but can belong to another customer.
Ownership is checked inside the transaction after the existing ordered account
locks and before idempotency/postings. Customer idempotency scopes use stable
customer identity, independent of session rotation and other customers; existing
operator scopes are unchanged. Ledger-driven balances, the original debit/credit
postings, insufficient-funds checks, rollback and terminal-state rules remain.

Transfer details are **sender-only**. The customer transfer DTO omits destination
ID and all recipient private information. Both parties can see their own
incoming/outgoing ledger-derived history, containing only transfer ID, timestamp,
direction, amount, currency and status. Recipients cannot use a history transfer
ID to fetch the sender's transfer details. There is no raw ledger browsing API.

### Operator, proposer and reviewer boundaries

Legacy `/api/v1/accounts`, `/api/v1/transfers` and dev funding routes are now
explicit operator APIs: an authenticated `ROLE_OPERATOR` is required, including
on loopback. `BANKOPS_BANKING_API_TOKEN` is a 32–256 character ASCII secret,
distinct from customer tokens (`cus_` prefixes are reserved), agent and governance
credentials. GET `/api/v1/operator/me` validates operator access. Account and
transfer services enforce roles independently of React. A customer cannot access
operator routes and an operator key cannot impersonate a customer.

**Vite never injects a banking operator key.** Its customer proxy preserves the
customer bearer header; its banking proxy forwards only an explicitly supplied
operator credential. The operator UI requires an unlock form, holds the key only
in private memory and clears it on lock, authorization failure or workspace exit.
The existing agent deployment key is limited to its aggregate evidence proxies.
Proposer/reviewer credentials, approval state transitions and remediation APIs
are unchanged. Entering customer banking unmounts and clears the governance UI's
cached role credential; no customer login grants approval/remediation authority.

See [customer setup and API contract](frontend/CUSTOMER_BANKING.md). Keep services
on localhost with distinct random keys. Use TLS and a separately reviewed gateway
before any nonlocal deployment. Do not expose the local Vite proxy publicly.

### Actual verification results

| Check | Result |
| --- | --- |
| Banking Maven package/full isolated PostgreSQL suite | **213 passed**, zero failures/errors/skips |
| Agent full pytest suite, warnings as errors | **487 passed** |
| Frontend component/API-mocking tests | **104 passed** |
| Desktop/mobile Chromium regression suite | **32 passed** |
| Real isolated customer Chromium workflow | **1 passed** |
| ESLint, TypeScript, Prettier and production build | Passed |
| Real Vite privilege-boundary regression | Passed: anonymous banking not elevated; explicit operator, customer and reviewer credentials preserved; no keys in served client sources |
| Public OSV inventory lookup | 535 package coordinates, zero affected packages at verification time, including packaged Spring Security and cached patched Airflow runtime |
| Tracked-file secret-pattern scan | One reviewed synthetic mocked Groq placeholder; no real credential found; no tracked dotenv credentials |

New backend assertions cover authentication failure, UTF-8 password limits,
revoked/expired sessions, role/owner forgery, disabled production profiles,
foreign/ownerless account isolation, history counts/privacy, sender-only transfer
reads, cross-customer debit rejection, service-level guards, immutable ownership,
customer-scoped conflicting/matching retries and concurrent duplicates. A V5→V6
migration test proves an existing unowned account row remains unchanged. Existing
financial tests retain their assertions and now supply explicit synthetic
operator authority where required; no test was disabled to accommodate auth.

The real browser used a dedicated PostgreSQL container on localhost:55464 and a
unique `customer_ui_*` schema. Customer A's account was funded with synthetic
reserve funds through the existing dev funding API, then transferred $250 to
customer B: final customer balances were **$750/$250**. Matching retry returned
200 with the original transfer; foreign account access, foreign source debits
and recipient transfer-detail access returned 404. Anonymous and customer-token
access to the operator route returned 401. Logout revoked the session.

Early browser attempts stopped at Chromium response-body capture (the client
consumes a bounded streaming body); verification now asserts the original HTTP
status and validates the object through authenticated read-back/idempotent retry.
No financial write was automatically retried. Test data from those attempts was
preserved: the fixture contains six customer accounts plus the reserve, four
completed transfers and eight postings. Final READ ONLY checks, rolled back,
showed **0 account-balance mismatches**, **0 invalid completed-transfer postings**
and **$10,000 total balance = $10,000 total opening balance**. Two synthetic
sender/recipient pairs ended at $750/$250; the reserve held $8,000 and two other
test accounts held zero. No development records were read or modified.

The isolated Spring/Vite fixture was stopped, its generated credential manifest
removed by its own cleanup, and only the dedicated Step 64 PostgreSQL container
was stopped. Test database contents were preserved; existing services were not
stopped or reconfigured.

### Remaining limitations

This is a local portfolio identity implementation, not production retail banking
authentication. There is no MFA, password reset, breached-password screening,
external identity/KYC verification, session-management screen, joint ownership or
trusted legacy-account enrollment tool. Registration is open only when explicitly
enabled. TLS, external rate limiting, stronger enrollment and operational identity
controls require a separate rollout review; production customer auth stays off.

Operator auth remains a powerful shared service credential, not individual human
RBAC. Existing proposer/reviewer keys prove credential possession, not physical
human presence. Database owners remain privileged: HTTP ownership checks cannot
protect against a compromised superuser. V6 has no row-level security; use a
separate migration principal and least-privileged application role when deploying.

Browser reload/navigation loses customer session and pending retry state. Unknown
financial outcomes retain their original request/key only while that workspace
is alive; users must check history before creating another request after losing
it. There are no automatic financial retries. Memory-only bearer tokens reduce
persistent exposure but do not protect against a compromised browser/XSS.
Session metadata is retained; expiry/revocation is enforced but scheduled cleanup
is not implemented. Dependency lookup is time/inventory bounded and the secret
scan covers tracked files; neither is proof against unknown vulnerabilities.

No migration was applied to the development database. A future authorized rollout
must back up/verify that database before enabling Flyway V6 and provision customer
ownership through a separately reviewed process; never infer historical owners.

## Step 65 — database security and least-privilege access

Implemented/verified **2026-10-27** (America/Chicago). This section supersedes
earlier database connection/provisioning guidance. Existing working-tree changes,
customer ownership, financial services and Flyway V1–V6 were preserved. **No V7
was necessary:** credentials, role provisioning and ACLs are environment policy.
No existing development banking rows, grants, passwords, object ownership or
migration history were changed. No production or paid API calls were performed.

### Read-only audit of existing services

Only PostgreSQL containers were temporarily started for metadata-only inspection,
then restored to their original stopped state. No banking row queries were used.

- The development banking cluster has a `bankops` superuser with CREATEDB,
  CREATEROLE, inheritance, replication and BYPASSRLS. It owns the V1–V5 banking
  tables and Flyway history. No customer V6 tables have been deployed there.
- `bankops_reconciliation` has no elevated attributes/memberships and SELECT on
  accounts, transfers, ledger entries and history. The existing schema denies
  public CREATE, but PostgreSQL's default public CONNECT/TEMP and function
  EXECUTE permissions needed explicit hardening in the new policy.
- The existing Airflow metadata database has a separate `airflow` superuser,
  also owning its metadata database. This is independent of the banking cluster.
- Banking currently uses SCRAM for external Docker connections, SSL is off, and
  the old initialized HBA contains trust rules for sockets/container loopback.
  Docker publishes banking PostgreSQL only on host `127.0.0.1:5433`.
- The FastAPI agent has no banking PostgreSQL driver, DSN or credentials. It
  collects HTTP evidence and keeps approval/remediation persistence in separate
  SQLite. Prometheus, Grafana and Jaeger also have no banking DB credentials.

The live legacy roles remain as audited: these are **pending rollout risks**,
not claims that existing volumes were silently upgraded. New banking startup
refuses the superuser runtime; fresh Airflow metadata receives a restricted role.

### Permission matrix and implementation

| Principal | CONNECT / schema | Table/function capabilities | Denied |
| --- | --- | --- | --- |
| Infrastructure `bankops` administrator | Cluster administration, backup and explicit provisioning | Trusted administrative access | Must never be supplied to the application/browser/agent |
| `bankops_migrator` | Banking DB CONNECT, public USAGE/CREATE | Owns tables/functions/history it creates; migration-only process | Superuser, CREATEDB, CREATEROLE, inheritance, replication, BYPASSRLS, role membership |
| `bankops_runtime` | Banking DB CONNECT, public USAGE | SELECT on seven app tables; bounded INSERT/UPDATE columns; EXECUTE only V5 keyed-transfer function | Schema CREATE, TEMP, owner rights, DELETE/TRUNCATE/TRIGGER/REFERENCES, history access, other app functions, membership/escalation |
| `bankops_reconciliation` | Banking DB CONNECT, public USAGE; default read-only | SELECT accounts, transfers, ledger entries, Flyway history only | All financial writes, customer/session/ownership/idempotency access, schema/TEMP creation and write-function execution |
| `bankops_agent` | NOLOGIN, no DB/schema access | None; HTTP evidence and separate SQLite only | All banking reads/writes/functions |
| `bankops_monitoring` | NOLOGIN, no DB/schema access | None; HTTP monitoring only | All banking reads/writes/functions |
| Airflow metadata `airflow` (fresh volumes) | Own metadata DB/schema only, separate cluster | Metadata DDL/DML needed by standalone Airflow migrations | Superuser, CREATEDB, CREATEROLE, inheritance, replication, BYPASSRLS; no banking write credential |
| Airflow metadata `airflow_admin` | Separate infrastructure administrator | Metadata initialization/maintenance | Never passed into the Airflow runtime |

`database/roles.sql` provisions bounded principals and revokes public database
CONNECT/TEMP and schema permissions. Roles have no membership paths to a privileged
role. Migrator default privileges remove global public function EXECUTE; future
objects receive no automatic runtime/reader grants. `permissions.sql` resets both
table **and column** ACLs before granting the exact allowlist. No SECURITY DEFINER
wrapper was added; existing trigger functions remain SECURITY INVOKER.

Runtime UPDATE columns are only account `balance` (needed by the ledger trigger),
transfer `status`, idempotency `request_hash`/`transfer_id` (needed by V5 conflict
claims/binding) and session `revoked_at`. INSERT covers the existing creation and
posting columns, including account genesis balance for the dev reserve. The
runtime cannot change ownership, customer identity fields, transfer amounts or
account identities, or modify/delete posted ledger entries. V3 enforces balances
even though its invoker trigger requires runtime UPDATE(balance); direct mismatched
balance changes still fail at commit. V4/V5/V6 protections and service ownership
checks continue to apply. Customer APIs still create only zero-balance accounts.

`database/provision.py` is explicitly opt-in and local-target-only. It requires
an administrator environment DSN matching the selected database, rejects unsafe
roles/memberships/runtime-owned objects, and applies changes transactionally.
Three service passwords must be distinct printable ASCII secrets of 32–256
characters. It sends salted SCRAM verifiers instead of plaintext password SQL,
suppresses statement/error-statement logging and never prints SQL/DSNs/errors.
Repeat prepare verifies existing verifiers without implicit rotation; a mismatch
aborts. Grant requires successful V1–V6 history and is repeatable. Credentials,
existing SQL ownership and financial rows are never automatically reassigned.

### Runtime/migration separation and connection policy

- Normal Spring configuration now disables embedded Flyway by default and enables
  a privilege verifier before the HTTP server accepts requests. The runtime must authenticate as `bankops_runtime`,
  including its session identity, with no elevated flags, memberships, ownership,
  schema/TEMP creation, dangerous table grants, unsafe application function access
  or Flyway history access. Unsafe connections fail closed. `db-secure` makes the
  runtime username default explicit and keeps Flyway disabled.
- `DatabaseMigration` is a separate packaged non-HTTP launcher using only
  `BANKOPS_MIGRATION_DB_URL`, `_USER`, `_PASSWORD` and explicit
  `BANKOPS_MIGRATION_APPLY=local-only`. It requires the dedicated non-superuser
  principal, local JDBC target, validates checksums, disables Flyway clean and
  suppresses sensitive diagnostics. The runtime needs no migration/admin secret.
- Compose separates `BANKOPS_POSTGRES_ADMIN_PASSWORD` from runtime
  `BANKOPS_DB_PASSWORD`. A mounted HBA uses SCRAM on sockets/IPv4/IPv6, allows the
  three login roles only into `bankops`, permits the infrastructure administrator
  separately and rejects other connections. The administrator remains trusted.
- Banking PostgreSQL keeps its localhost port and existing data volume. Monitoring
  services move to their own Compose network; Prometheus↔Grafana DNS and existing
  host-scrape/OTLP mappings remain. Monitoring receives no database credentials.
- Fresh Airflow metadata uses an environment-configured administrator plus an
  explicitly created non-superuser runtime. No metadata admin secret is forwarded
  to Airflow. Its DB has no host port; the existing SELECT-only reconciliation
  connection is separate. The legacy provisioning helper also suppresses SQL
  statement/error-statement logging before credential SQL.
- No database password enters React, frontend proxy configuration or a `VITE_*`
  setting. Governance proposer/reviewer keys and contracts are unchanged.

See [database setup and existing-volume rollout](database/README.md) and the
placeholder-only environment template there. In a separate runtime shell, use
`dev,db-secure` after provisioning. Existing superuser-based development startup
now intentionally fails closed until that setup is completed. Automated invariant
fixtures explicitly use test-only administrator exceptions; the dedicated HTTP
permission suite uses the guarded, real runtime role.

### Actual verification results

| Check | Actual result |
| --- | --- |
| Banking full Maven package / isolated PostgreSQL 17 | **219 passed**, zero failures/errors/skips; includes six real-role HTTP/ACL tests |
| Agent full pytest, warnings as errors | **487 passed** |
| Airflow full pytest/DAG import, warnings as errors | **44 passed**, including real V6 reconciliation with a SELECT-only login |
| Database provisioning/credential tests | **14 passed**, including PostgreSQL authentication of generated SCRAM and wrong-password rejection |
| Frontend component/API tests | **104 passed** |
| Desktop/mobile Chromium | **32 passed** |
| Lint, TypeScript, Prettier, production build | Passed |
| Packaged migration launcher | Default disabled; actual non-superuser V1–V6 migration/validation passed; repeat no-op; wrong password safely rejected; no HTTP server started |
| Actual provisioning CLI | Prepare/grant repeat execution passed; a mismatched credential was rejected and rolled back without rotation; original credentials still verified |
| Fresh PostgreSQL 16 Airflow metadata initializer | Runtime not superuser; metadata DDL/DML allowed; cluster role creation denied; verification transaction rolled back; generated credentials absent from container logs |
| Exact PostgreSQL 16 banking HBA policy | SCRAM login passed; wrong password and other-database connection denied; no trust/invalid rules; generated credentials absent from logs |
| Compose configuration / secret scan | Both configurations validate without printing resolved secrets; one reviewed synthetic Groq placeholder, no real credentials or tracked dotenv credentials found |

Permission probes explicitly switch Airflow transactions to READ WRITE, proving
that ACLs—not merely the default read-only setting—reject INSERT/UPDATE/DELETE.
They deny customer/session/ownership reads, write-function calls and role changes.
Agent/monitoring roles cannot log in, have no CONNECT or table grants and fail
actual financial UPDATE attempts. Runtime DDL, trigger disabling, history access,
unneeded column writes, ownership changes and SET ROLE are rejected. Migration
ownership and future private table/function defaults are verified in rolled-back
transactions. HTTP tests exercise customer account creation/login/logout, owned
transfers, cross-customer debit denial, insufficient funds, concurrent matching
idempotency, conflicting reuse, balanced ledger results and financial rollback.

The first broader run exposed test infrastructure assumptions: standalone profile
fixtures relied on automatic Flyway, and another pooled application context hit
PostgreSQL's connection limit. Fixtures now explicitly opt into isolated admin
migration and bound pools to two connections. Assertions were not weakened and
no test was skipped. The subsequent complete 219-test run passed.

V1–V6 files were not edited. V6 SHA-256 remains
`9B9A684C719E8471AE9274349D1517A1AD74C2FC5E36C07BAD2755CE4C2BAC02`;
V1–V5 match the previously recorded values. No development privilege rollout,
financial transaction, ownership assignment, migration or scheduled DAG run was
performed. Read-only audits were rolled back. New write/denial tests and migration
history changes were restricted to dedicated disposable containers/databases.

All three Step 65 PostgreSQL verification containers were stopped after testing,
with their data preserved. Existing service states were restored; no monitoring,
banking application or full Airflow stack was started or reconfigured in place.

### Remaining limitations and rollout requirements

1. **Existing volumes are not upgraded.** Banking's legacy `bankops` and Airflow
   metadata's legacy `airflow` superusers remain as audited. Back up/verify restore
   and review object ownership, history access and a credential/ACL handoff before
   enabling the new configuration there. The tooling deliberately does not
   `REASSIGN OWNED`, auto-demote owners, grant superuser membership or recreate
   volumes. Fresh init scripts do not alter existing PostgreSQL passwords/roles.
   The new migration role cannot take over legacy-owned objects automatically.
2. Superusers/owners can bypass ACLs; protect administrator and migration credentials
   and keep them outside runtime environments. The application role is still
   trusted across customers: HTTP service ownership checks are authoritative; no
   row-level security was added. Runtime SQL INSERT(balance) remains necessary for
   the existing reserve genesis and can create opening balances; restricting that
   separately would require a reviewed bootstrap/financial design change.
3. Local Compose uses SCRAM, localhost publication and Docker network boundaries,
   **not TLS**. Nonlocal deployment requires managed certificates, verify-full
   clients, separately reviewed HBA/network policy, credential rotation and backup
   procedures. These local provisioning/migration commands intentionally reject
   remote targets. Docker administrators can inspect container environment secrets.
4. Airflow standalone retains DDL only in its own metadata DB, because it performs
   its own metadata migrations. A production migration/runtime split for Airflow,
   secret-file/manager delivery and full scheduler rollout remain separate work.
   No full Airflow runtime was restarted for this step; DAG imports/functions,
   real reconciliation and metadata role initialization were tested independently.
5. Startup privilege verification is defense in depth, not continuous drift
   monitoring or a complete privilege-policy engine. Future migrations, manual
   grants and function additions require explicit ACL review/reapplication. Tests
   cover PostgreSQL 17 banking and PostgreSQL 16 auth/metadata; no production
   network, operating-system or privileged-host compromise testing was performed.

## Step 66 — end-to-end security regression verification

Verified **2026-10-27, America/Chicago**. The integrated fixture passes, with
V1–V6 unchanged and no existing development database, role or financial record
updates. Full commands, scope, actual evidence, findings and Docker prerequisites
are in [security/README.md](security/README.md).

The repeatable opt-in harness creates a PostgreSQL 17 regression cluster and a
fresh PostgreSQL 16 banking cluster using the exact SCRAM HBA. Central prepare/
grant provisioning and the packaged migration-only launcher apply/validate V1–V6
with the dedicated non-superuser migrator. Banking then starts with only the
restricted runtime credential; administrator-credential startup fails. The actual
agent uses an isolated SQLite approval store and separate role hashes, without
banking credentials, paid inference or remediation. React/Vite and Chromium use
the existing APIs without changing their authentication or response contracts.

| Verification | Result |
| --- | --- |
| Banking / agent / Airflow / database suites | **219 / 487 / 44 / 14 passed** |
| Harness safety / frontend unit / standard Chromium / real-service Chromium | **7 / 104 / 32 / 2 passed** |
| Total automated cases | **909 passed** |
| ESLint, Ruff, Prettier, Python formatting, TypeScript | Passed |
| Maven package, Vite production build, agent Docker image | Passed |
| SQL permission probes | 22 expected denials, including runtime DDL/trigger bypass and reader DML after switching READ WRITE on |
| Financial reconciliation | PASS on generated ledger; four controlled in-memory violations detected; financial snapshot unchanged |
| Browser/service privacy | No persistent browser credentials; no tested role/session keys, customer aliases, account numbers/IDs, transfer IDs, idempotency keys or financial fields in structured logs |
| npm / expanded OSV audits | 0 npm vulnerabilities; 0 affected package coordinates among 646 audited entries |
| Patched agent image | Non-root UID 10001, health 200, private APIs fail closed 503, approvals disabled 503, no banking DB credentials |

Live checks covered owned account creation, private history, IDOR/foreign transfer
denial, cross-customer source debit rejection, operator/customer separation,
invalid/malformed/revoked/expired sessions, safe confirmation and matching retries.
Actual concurrent duplicates produced one 201 and one 200 for one transfer;
conflicting reuse returned 409 and insufficient funds 422. Customer balances after
the browser's synthetic $1,000 funding/$250 transfer were $750/$250. Reconciliation
and rollback probes preserved the financial snapshot. Corruption scenarios changed
only in-memory copies, never balances, triggers or committed ledger records.

Real approval APIs rejected proposer approval and reviewer proposal creation
(403), unrelated credentials (401), and conflicting repeated decisions (409).
The reviewer UI required explicit confirmation and preserved server-assigned audit
actors. Customer navigation cleared the cached governance credential. Approval
executed no action; remediation and LLM inference stayed disabled throughout.

The first combined run passed the application suites but caught a readiness bug
in the new harness: it tried to parse Vite HTML as JSON. That is fixed with new
regression coverage; fresh integrated reruns passed. The image probe was corrected
to use a supported proposal-detail route rather than an unsupported GET list.
No financial/security assertions were weakened, and no tests were disabled.

The expanded audit found vulnerable **development packaging tools** omitted from
the earlier lock-only inventory: local pip 23.2.1/setuptools 84.0.0 and image pip
25.0.1. Local tools are pinned to pip 26.2.2/setuptools 84.2.1, the image installs
patched pip, and builds require setuptools >=84.1.0. Published
[pip](https://github.com/advisories/GHSA-4xh5-x5gv-qwph) and
[setuptools](https://github.com/advisories/GHSA-xmj3-9gf7-h52w) advisories support
these corrections. The rebuilt image, expanded audit and `pip check` pass.
No banking financial code or API contract changed. Docker contexts now exclude
dotenv variants and SQLite/dump data. The secret scan found only the known
synthetic mocked Groq key, not a live credential or tracked dotenv file.

Final integrated evidence is in ignored
`frontend/.cache/step66/ee48c11ca4a2/report.json`; completed application regression
logs are retained under run `bbc2e2bdf03d`. Test fixtures were stopped and preserved.
No development services were restarted, no development roles upgraded and no
production deployment or paid external API call occurred.

**Docker readiness is conditional:** role/migration/runtime sequencing and the
agent image are verified, but banking/frontend container packaging, internal DNS
allowlists for the deliberately local-only migration tools, Linux harness paths,
TLS, exact ingress hosts and production secret delivery still need implementation
or deployment review. No full Airflow scheduler/UI or live monitoring stack was
started in this step. Existing development superusers/ownership remain a pending
reviewed rollout, not silently fixed. All earlier limits—shared operator/reviewer
credentials, no production customer identity, no RLS, trusted runtime genesis
INSERT, privileged-host/superuser exposure—remain. Audits cover package metadata,
not container OS/native CVEs or penetration testing. This is evidence for the
next isolated Docker integration step, not production security certification.
