# End-to-end security regression — Step 66

## Step 67 follow-up: unified local Docker

The [local runbook](../local/README.md) supersedes this document's historical
"Docker readiness" section for local integration. The complete isolated stack
was built and started on 2026-10-28. All nine runtime containers passed health
checks; authenticated frontend proxy routes, actual Prometheus scraping,
Grafana datasource health, Jaeger banking traces and SELECT-only reconciliation
passed. Customer APIs, inference and remediation stay disabled. The agent has no
financial network or banking credentials; migration/admin credentials are absent
from application containers. No existing development data, roles or volumes were
changed and no destructive cleanup was executed.

Step 67 regressions: 219 banking, 487 agent, 104 frontend, 57 Airflow/database and
7 harness tests passed (874 total), plus frontend lint/typechecking and Compose
validation. See the local runbook for actual scope, corrected startup issues and
remaining limits. These results do not rerun or extend Step 66's dependency audit.

Verified **2026-10-27, America/Chicago**. The isolated integrated run passed.
Development databases, roles, services and financial records were not changed.
Flyway V1–V6 hashes are unchanged. No paid inference or production deployment
was performed. Existing working-tree changes from earlier steps were preserved.

## What runs together

`run_step66.py --isolated --regressions` creates two unique test containers:

1. PostgreSQL 17 on localhost:55467 for the existing banking/Airflow/database
   regression fixtures. Its generated administrator credential never selects a
   development database. Legacy invariant tests can create deliberately invalid
   fixtures only in this disposable environment.
2. PostgreSQL 16 on localhost:55466, using the exact banking SCRAM HBA policy and
   central `database/provision.py` prepare/grant commands. Dedicated migration
   credentials run the packaged Flyway launcher, then are discarded from runtime
   environments. Repeating migration validates checksums and does no new work.

The packaged banking service starts on localhost:18066 with only its restricted
runtime credential, the `dev,db-secure` profiles, and an explicitly enabled
synthetic reserve. An administrator-credential startup is tested separately and
must fail. The actual FastAPI agent starts on localhost:18067 with an isolated
SQLite approval store, different deployment/proposer/reviewer credential hashes,
inference disabled and remediation disabled. It receives **no banking DB secret**.
Vite runs on localhost:5196 against these services; Chromium exercises real APIs,
customer ownership and reviewer actions through the existing proxies.

The real reconciliation module runs with the actual SELECT-only login against
the generated ledger. Its output is PASS. Balance, missing/duplicate posting and
lifecycle inconsistencies are then introduced **only in copies of an in-memory
snapshot**, not through financial writes or disabled triggers. Every inconsistency
is detected; the database snapshot stays identical across the verification probes.

## Run locally

The host launcher currently targets Windows + Docker Desktop, Java 21+ (verified
using JDK 25), the repository Maven wrapper distribution, Python 3.12 agent venv,
Node/npm dependencies and cached Chromium. Test images `postgres:16`, `postgres:17`
and `bankops-airflow-step63-tests` must be available. Build the patched Airflow
test/runtime images using the existing Airflow instructions if absent. Do not
substitute an older unpatched image silently.

From the project root, install tooling into the **project** virtual environment:

```powershell
agent/.venv/Scripts/python.exe -m pip install -r security/requirements-dev.txt
agent/.venv/Scripts/python.exe security/run_step66.py --isolated --regressions
```

Use `--isolated` without `--regressions` to repeat only the integrated checks with
an already built banking JAR. This still creates a new database/container and
never reuses development banking or previous financial fixtures. Ports 55466,
55467, 18066, 18067, 18068 and 5196 must be free; startup fails rather than taking
over a listener. No arbitrary target URL or existing database option is accepted.

Build/audit the verification-only agent image separately:

```powershell
docker build -t bankops-agent:step66-security agent
agent/.venv/Scripts/python.exe security/verify_image.py
agent/.venv/Scripts/python.exe security/audit.py
cd frontend
npm audit --registry=https://registry.npmjs.org
```

The audit sends only public package names/versions to OSV; npm sends dependency
metadata to its public registry. Neither submits source, logs, prompts or banking
data. `audit.py` requires both the patched Airflow runtime image and built agent
image, and fails if inventory/lookup is missing. Run it explicitly as a CI gate;
the offline harness does not imply that the online audit was performed.

Python checks: `python -m ruff check --config security/ruff.toml security`,
`python -m ruff format --check --config security/ruff.toml security`, and
`python -m pytest security/tests -q -W error`, using the agent venv. Existing
Python modules keep their established formatting; no unrelated reformat occurred.
The full harness runs frontend ESLint, TypeScript, Prettier, unit tests, production
build and desktop/mobile Chromium, plus Maven package and complete Python suites.

## Privacy and cleanup

All service credentials are random per run, held in memory/child environments.
The harness strips inherited banking, database, migration, provider and tracing
configuration. Successful runtime services never receive administrator/migration
secrets; the separate negative startup test deliberately supplies an isolated
administrator credential and must fail before serving requests.
Chromium gets synthetic role keys through its test-process environment, not a
secret manifest. Traces, videos and screenshots are disabled for real credential
tests. Tests verify no credentials in browser persistent storage or service logs;
banking logs also exclude customer aliases, account numbers/IDs, transfer IDs,
idempotency keys and financial fields. HTTP verification refuses redirects and
does not trust proxy environment variables for localhost requests.

Reports and redacted logs live under ignored `frontend/.cache/step66/<run-id>/`.
They contain safe statuses/counts and a snapshot digest, not raw financial rows.
The SQLite file contains synthetic proposal/audit data only. Processes created
by the harness are terminated in `finally`; only its unique containers are
stopped. Database/container data is preserved, never deleted/truncated. Unrelated
services are not started, stopped or reconfigured. Cleanup failures or changed
migration hashes fail the run.

## Actual results

| Check | Result |
| --- | --- |
| Banking isolated PostgreSQL suite / packaged JAR | **219 passed**, zero failures/errors/skips |
| Agent suite, including a repeat after tooling patches | **487 passed** |
| Airflow/DAG/reconciliation suite | **44 passed** |
| Database provisioning/SCRAM suite | **14 passed** |
| Harness safety regression tests | **7 passed** |
| Frontend component/API tests | **104 passed** |
| Desktop/mobile Chromium regressions | **32 passed** |
| Actual restricted-role customer/reviewer Chromium tests | **2 passed** |
| Lint, formatting, TypeScript | Passed |
| Maven package, Vite production build, agent image build | Passed |
| Runtime SQL permission probes | **22 denied** as expected |
| Reconciliation | Actual fixture PASS; four in-memory mismatch cases detected; no financial snapshot change |
| Agent image | UID 10001; health 200; private API 503 without credentials; approvals 503 by default; no banking credentials |
| Final npm audit | **0 vulnerabilities** |
| Final OSV audit | **0 affected package coordinates out of 646** |
| Secret-pattern scan | One reviewed pre-existing synthetic Groq placeholder; no live credential or tracked dotenv file found |

These are **909 automated test cases**, plus explicit HTTP/SQL/image checks.
The completed regression stage is retained in run `bbc2e2bdf03d`; final integrated
and log-privacy verification is run `ee48c11ca4a2`. A previous integrated run
`742f63ef2a59` also passed before adding the explicit service-log assertions.
Final audit metadata is `frontend/.cache/step66/dependency-audit.json` and npm's
report is `frontend/.cache/step66/npm-audit.json` (ignored local artifacts).

The browser/API flow verified zero-balance owned account creation, synthetic
reserve funding and a $250 transfer producing $750/$250 customer balances.
Matching retries returned 200 with the original transfer. Concurrent duplicates
returned one 201 and one 200; conflicting reuse returned 409; insufficient funds
422; foreign account/history/transfer reads and foreign source debits 404.
Anonymous/customer access to operator routes returned 401. Invalid/malformed,
revoked and deliberately expired test sessions were rejected. Customer/proposer/
operator/deployment credentials could not become reviewer authority: proposer
approval and reviewer creation returned 403, and conflicting repeat decisions
409. Server-assigned audit actors remained `proposal_service` / `human_reviewer`.

The first combined run completed all application suites but stopped at an HTML
readiness parsing bug in the new harness. A dedicated regression now covers it;
fresh integrated reruns passed. The image smoke check also initially selected an
unsupported GET collection route (405); it now checks the supported proposal
detail route for disabled-by-default behavior. No banking/security assertions
were weakened or disabled to obtain a pass.

## Findings corrected during verification

The expanded audit included installed development tools, beyond the old runtime
lock-file inventory. It found local pip 23.2.1 and setuptools 84.0.0, and the first
agent image inherited pip 25.0.1. Local tooling is now pinned to pip 26.2.2 and
setuptools 84.2.1; the agent image explicitly installs patched pip and requires
setuptools >=84.1.0 for builds. See the
[pip advisory](https://github.com/advisories/GHSA-4xh5-x5gv-qwph) and
[setuptools advisory](https://github.com/advisories/GHSA-xmj3-9gf7-h52w).
The rebuilt image and installed environment pass the final expanded audit and
`pip check`. Runtime API dependencies/contracts and banking behavior did not change.
Docker context exclusions now also cover dotenv variants, SQLite data and dumps.

## Docker readiness and remaining limits

**Ready for a subsequent isolated Docker integration step, conditionally—not a
production approval.** PostgreSQL HBA, role provisioning, dedicated migration,
restricted runtime, Vite forwarding and the agent image have been verified.
Banking and frontend currently have no production Dockerfiles/services; the live
cross-service test intentionally uses host processes with disposable Docker DBs.
The full Airflow scheduler/UI stack and live Prometheus/Jaeger/Grafana were not
started. Airflow's actual reconciliation code, DAG imports and read-only role were
tested; collector failure states remain honest when evidence sources are absent.

Before a combined Compose stack:

- Keep migration/admin credentials out of long-running containers; sequence
  prepare → dedicated migrate/validate → grant → runtime. Keep DB networks separate
  from monitoring and expose only intended localhost ports.
- The local provisioning/migration tools deliberately reject arbitrary remote or
  service-DNS targets. Review an explicit internal service allowlist/network model
  before introducing container-side migration jobs. Linux CI also needs host-path
  adaptation and `host.docker.internal` routing; this Windows harness is not yet a
  portable production launcher.
- Containerized HTTP services need explicit bind addresses, exact allowed hosts
  and separate API-role secrets. Preserve Host/Origin checks, memory-only browser
  credentials, no automatic write retries and fail-closed defaults.
- Keep production customer authentication, approvals, inference and remediation
  disabled unless separately authorized/configured. Existing production customer
  profile restrictions remain; no real identity/KYC, MFA or per-person reviewer
  identity was added. Shared role credentials prove possession, not human presence.
- Existing development volumes/roles remain untouched and require verified backup
  restoration and a reviewed ownership/credential handoff. Do not reuse these
  disposable fixture secrets or automatically claim legacy customer accounts.
- TLS/verify-full database connections, secret manager delivery/rotation, pinned
  base-image digests, OS image
  and native-library scanning, penetration testing and full deployment hardening
  remain required for production. OSV/npm results are time/inventory bounded;
  container OS CVEs and unknown vulnerabilities are outside this audit's scope.
