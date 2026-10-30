# Testing the sanitized snapshot

Use Python 3.12, Node 22 and Java 21. Dependency lockfiles are authoritative.
Never use a real banking database, cloud model key or paid provider for tests.

## Agent

Create/activate a Python 3.12 virtual environment, then from repository root:

```bash
python -m pip install pip==26.2.2 setuptools==84.2.1
python -m pip install -r agent/requirements-test.lock
python -m pip install --no-deps --no-build-isolation -e agent
python -m pip check
cd agent
python -m pytest -q -W error -p no:cacheprovider
```

The default suite uses synthetic evidence and mocked providers. The Step 74
browser test is opt-in through BANKOPS_STEP74_BROWSER=1 and is skipped otherwise.
It starts only loopback fixture servers. Step 75's Compose/browser harness is
separate and uses real scheduler execution with cloud inference disabled.

## Frontend

From `frontend`: `npm ci`, then `npm run lint`, `npm run format:check`,
`npm run typecheck`, `npm test`, `npm run build`. For browser tests, install
Chromium with `npx playwright install chromium`, then run `npm run test:e2e`.
These ordinary UI tests use test fixtures; they do not establish live-stack
integration. Live/Compose harnesses are separate and explicitly isolated.

## Java, Airflow and database tests

Banking Maven tests require BANKOPS_TEST_DB_URL, BANKOPS_TEST_DB_USER and
BANKOPS_TEST_DB_PASSWORD for a **fresh disposable PostgreSQL**. Java tests create
isolated schemas and synthetic fixtures. Do not provide a development/admin DSN
for a retained banking database. Run `bash mvnw --batch-mode test` from
`backend/banking-service` on Linux, or `mvnw.cmd --batch-mode test` on Windows.

Airflow/reconciliation/security tests require disposable database DSNs. The CI
workflow creates these services and runs the patched test image, then cleans up
runner-owned resources. See `.github/workflows/ci.yml` for the exact contract.
The source scripts `local/run_step74_airflow.py` and `local/run_step75_backend.py`
are historical local verification helpers, with platform/tool/image prerequisites.

## Reproducing the Step 75 integration

`local/run_step75.py` requires the documented local fixture image set and existing
Docker project generator, Chromium, Node, Python 3.12 and OpenSSL. It is a Windows
verification harness, not the generic quick-start command. It starts a fresh
Compose project, accelerates only the copied DAG's schedule/retries, creates a
read-permission fault, observes a scheduled run, drives the real dashboard and
preserves volumes on teardown. It never points at retained banking data.
The fixture uses a TLS front door with an explicit CA and a read-only viewer token.
Real LLM inference remains disabled. See [the scheduled integration report](verification/STEP75_INTEGRATION_REPORT.md) for the
actual observed result and limitations, including partial idle banking metrics.

## Security gates and evidence

The image workflow builds seven image targets, uploads SBOMs and scan artifacts,
and fails on any HIGH/CRITICAL finding, including unfixed advisories. Gates are
not suppressed or weakened to obtain green CI. [Hosted baseline scans](verification/HOSTED_BASELINE.md) are dated;
a future push must run the current scanners again. No images are
published and no deployment is performed by these workflows.

Raw logs, local secrets, database files, screenshots containing banking records
and generated scan/test reports are excluded from publication. Authored Markdown
reports contain aggregate results and explicit scope limits. Dated preparation and hosted results are in
[publication status](../PUBLICATION_READINESS.md).
