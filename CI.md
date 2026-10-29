# Step 70: GitHub Actions testing

**Step 72:** [GitHub-hosted readiness and publication blockers](security/STEP72_READINESS.md).
Local preflight is complete; hosted execution awaits an identified repository,
reviewed data/history handling and explicit publication approval.

Step 71B final artifact, container, Git and workflow verification is recorded in
[the closeout report](security/STEP71B_CLOSEOUT.md). Its October 29 container
status supersedes the historical October 28 container status below.

The workflow is [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
It runs on pushes to `main`, pull requests targeting `main`, and manual
`workflow_dispatch`. Four independent Ubuntu 24.04 jobs run each suite once;
new runs cancel older runs for the same workflow/ref. No deployment, repository
creation, publishing, paid cloud services or live inference is configured.
GitHub runner usage is subject to the repository's Actions allowance.

| Job | Toolchain | Coverage |
| --- | --- | --- |
| Backend | Temurin Java 21, Maven wrapper, PostgreSQL 17 | Full banking regressions, Flyway compatibility, customer authorization and database ACLs |
| Agent | Python 3.12, locked dependencies | FastAPI, evidence, mocked inference, approvals, remediation and security |
| Airflow/database | Existing patched Airflow 3.3.2 / Python 3.12 test Dockerfile, PostgreSQL 17 | DAG import/topology, read-only reconciliation, provisioning and real SCRAM authentication |
| Frontend | Node 22, Python 3.12, lockfile-selected Chromium | Lint, formatting, types, components, production build, desktop/mobile browser tests, launcher/security harness and CI safety tests |

Java 21 matches `pom.xml`; Python 3.12 matches the agent constraint and Airflow
Dockerfiles; Node 22 matches the frontend Dockerfile/runbook. PostgreSQL 17 matches
the existing isolated regression cluster. Maven, pip and npm download caches use
project dependency files. Chromium comes from the locked Playwright package;
the patched Airflow test image is built each run. Neither is separately cached.

## Database isolation and least privilege

Each database job has a separate fresh PostgreSQL service, `bankops_test` database,
and dynamically allocated host port. `.github/scripts/database_env.py` requires
the GitHub Actions CI context, validates numeric run/port identifiers, and exports
only fixed loopback test targets. It never reads dotenv files, platform state,
development credentials, repository secrets, or production settings. No existing
Compose platform is started. The Airflow test container uses Linux host networking
to reach its job's service port; its repository bind mount is read-only. Keep these
jobs on GitHub-hosted runners, never a self-hosted development machine or database.

The service administrator is needed for fixtures that create disposable databases
and schemas and deliberately test corruption/DDL. It is not the application
runtime identity. The existing `DatabasePermissionsIntegrationTests` suite:

1. Creates a uniquely named disposable database and applies `database/roles.sql`.
2. Runs Flyway migrate/validate for V1–V6 as **`bankops_migrator`**, a non-superuser
   with no role/database creation rights, which owns the migrated objects.
3. Applies `database/permissions.sql` before starting Spring with the separate
   **`bankops_runtime`** identity.
4. Tests real HTTP operations, runtime DDL/ownership denials, and SELECT-only
   reconciliation access to four evidence tables. Agent/monitoring cannot log in
   or access banking tables; future objects remain private.

Legacy invariant and additive migration tests retain their isolated administrator
fixtures; CI does not weaken those tests or represent them as restricted runtime
tests. Airflow creates fresh test databases and exercises synthetic corruption
and real SELECT-only roles. The SCRAM integration verifies a generated verifier
with PostgreSQL. GitHub disposes of service containers at job completion. No
development records, V1–V6 migration files, or existing Docker volumes are touched.

## Commands and diagnostics

```bash
# backend/banking-service; explicit disposable BANKOPS_TEST_DB_* variables required
bash mvnw --batch-mode --no-transfer-progress test

# repository root, in a clean Python 3.12 environment
python -m pip install pip==26.2.2 setuptools==84.2.1
python -m pip install -r agent/requirements-test.lock
python -m pip install --no-deps --no-build-isolation -e agent
python -m pip check
# agent/
python -m pytest -q -W error

# repository root; see workflow for read-only mount and service DSN environment
docker build --file airflow/Dockerfile.test --tag bankops-ci-airflow airflow
# Inside that image with PYTHONPATH=/workspace/airflow:
python -m pytest -q -W error -p no:cacheprovider \
  airflow/tests database/tests database/integration

# frontend/
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npx --no-install playwright install --with-deps chromium
npm run test:e2e -- --config playwright.config.ts --reporter=line

# repository root, with frontend node_modules installed
python -m pip install pytest==8.4.2 PyYAML==6.0.3
python -m pytest -q -W error local/tests security/tests .github/tests
```

The default Playwright config starts a fresh Vite server in CI and runs desktop
and mobile Chromium with one worker. These are synthetic route and proxy boundary
tests. Separate live browser configs, full Docker recovery, real monitoring UI
and scheduler lifecycle checks remain opt-in local verification. No production
service, development account seeding or inference provider is required.

Named steps and job timeouts make failures attributable. Test exit codes propagate;
there is no `continue-on-error`, disabled failing suite, or success-on-retry rule.
The backend failure summary prints only test counts from Surefire reports, not
report properties, exception bodies or SQL. Pytest/Playwright show failing test
names in their step logs. No raw logs, environments, traces, test reports or build
directories are uploaded as artifacts.

Only `contents: read` is granted to `GITHUB_TOKEN`; checkout does not persist its
credential. There is no `pull_request_target`, PR-text shell interpolation, or
repository/environment secret dependency. The service bootstrap credential is a
disposable CI-only value derived from the run ID/attempt, never used by another
system. Its password and full DSNs are masked before running tests. Application
role/session credentials are generated by existing test fixtures. Do not add
`set -x`, dotenv dumps, raw `docker inspect`, or raw report uploads.

## Validation

```bash
actionlint .github/workflows/ci.yml
python -m pytest -q -W error .github/tests
```

The CI safety tests check that development target overrides cannot change the
exported database target, invalid contexts/ports cannot inject environment values,
and workflow triggers, permissions, checkout settings and referenced paths exist.
The actions' maintained major versions and cache configuration follow their
official documentation: [checkout](https://github.com/actions/checkout),
[setup-java](https://github.com/actions/setup-java),
[setup-python](https://github.com/actions/setup-python), and
[setup-node](https://github.com/actions/setup-node).

No workflow was pushed or remotely executed during Step 70.

### Actual local verification — October 28, 2026

| Check | Result |
| --- | --- |
| Java 21 banking, including migration/runtime ACL integration | 219 passed, zero failures/errors/skips; Maven BUILD SUCCESS |
| Airflow, database provisioning and PostgreSQL SCRAM | 58 passed |
| Python reliability agent (completed before resume) | 487 passed |
| Launcher, security harness and CI safety contracts | 68 passed; CI-only subset also passed 8/8 |
| Frontend lint, formatting, type checks and production build | All passed |
| Frontend component tests (completed before resume) | 104 passed |
| Chromium desktop/mobile | 32 passed; runner exited zero |
| Workflow YAML and expression validation | actionlint 1.7.7 passed |
| Git whitespace check and unchanged V1–V6 migrations | Passed |

Completed results were reused after the interrupted session. The temporary
`bankops-step70-ci-verification` PostgreSQL 17 container had a random credential,
only port 55470 published on loopback, and `/var/lib/postgresql/data` on tmpfs.
It attached no development volume. Backend verification used the Maven wrapper
and Java 21 in a disposable container; Airflow/database verification used the
already-built patched `bankops-airflow-step63-tests` image with a read-only source
mount. Browser verification used the normal desktop/mobile config with `CI=true`.
After verification, the temporary PostgreSQL container was cleanly stopped with
exit code 0. Temporary Maven containers exited/removed themselves; the browser
test server exited normally. All nine existing local platform runtime containers
remained running and healthy. No Docker volume was deleted.

Two local infrastructure attempts did not produce completed test results: copying
the entire Windows Maven cache was stopped before Maven started, and a subsequent
wrapper launch failed because Docker's default tmpfs mount was non-executable.
The completed backend attempt instead downloaded dependencies into an executable
temporary cache. The first sandboxed Chromium process stalled at teardown; it
was stopped, and an unsandboxed rerun with a three-minute global timeout passed
all 32 tests and exited normally. No test assertions were relaxed or skipped.

The first real GitHub run must still verify action downloads, cold dependency
installation (including the fresh Airflow image build), cache restore/save,
Linux Chromium dependency installation and GitHub service port mapping. Local
Airflow tests reused an existing image, and local Docker Desktop reached its
isolated database via `host.docker.internal`; the hosted Linux job uses loopback
with host networking. Full local-platform recovery, production deployment,
live cloud inference and exhaustive dependency/OS vulnerability audits are
outside this CI workflow. No repository secrets or remote configuration changes
are needed to run it.

# Step 71: Docker images and security scanning

[`images.yml`](.github/workflows/images.yml) is a separate workflow with the same
push-to-main, PR-to-main and manual triggers. The Step 70 `ci.yml` and its four
test jobs are unchanged. Both workflows should be required checks before merging.
No image is pushed, deployed, signed into a registry, or uploaded as an artifact.

| Matrix image | Dockerfile | Build context |
| --- | --- | --- |
| banking (also used for migrations) | `backend/banking-service/Dockerfile` | `backend/banking-service` |
| agent | `agent/Dockerfile` | `agent` |
| frontend | `frontend/Dockerfile` | `frontend` |
| airflow | `airflow/Dockerfile` | `airflow` |
| airflow-test | `airflow/Dockerfile.test` | `airflow` |
| database (shared prepare/grant tool) | `local/Dockerfile.database` | repository root |
| jaeger (custom health probe) | `local/Dockerfile.jaeger` | `local` |

These are all seven maintained Dockerfiles, using the existing Compose contexts.
Unmodified third-party PostgreSQL, Grafana and Prometheus service images are not
custom build targets. The Jaeger copy stage includes the pinned Prometheus probe
binary; final image scanning includes its installed contents. Builder-only layers
are not represented as part of the final runtime image's vulnerability report.

## Build identity, isolation and caching

Every Dockerfile `FROM` now retains its existing version tag and adds the resolved
immutable multi-platform manifest digest. CI builds `linux/amd64`, tags each
output with the source commit SHA, and records the source SHA, Dockerfile/context,
BuildKit image digest, base references and scanner reference in `build.json`.
Existing lockfiles and Dockerfile commands remain in use. Users, entrypoints,
health checks, network/database permissions and disabled application capabilities
are unchanged. Base updates require an explicit digest review; a stale digest
must be refreshed when a security fix is needed.

This controls base-image drift and dependency/build inputs; it is not a claim of
bit-for-bit reproducibility. Existing apt repositories, Python build isolation,
package timestamps and external dependency metadata can still change a cold build.
The recorded image digest and SBOM identify the actual scanned output.

Versioned Docker Buildx/build actions export a local Docker archive with
`push: false`. There is no login action, registry password, build argument,
BuildKit secret, SSH mount or runtime dotenv. Existing `.dockerignore` files keep
credentials, logs and local state out of contexts. The scanner reads the archive
without receiving the Docker socket, checkout, host environment or database
volumes. It is never given a running banking container to inspect.

The matrix uses `fail-fast: false`, at most two concurrent builds, and 35-minute
job limits. BuildKit GHA layer caches have separate scopes per image. Public Trivy
databases share one versioned cache across the matrix; only the banking job saves
it after successful analysis, even if findings later block the gate. This avoids
seven copies of the large Java index and repeated cold downloads after a failed
security gate. Image analysis caches are not shared. Trivy still checks for database updates;
there is no offline/stale-cache bypass. Step 70's functional Airflow image build
remains independent, so security failures cannot silently suppress its tests.

## Scanner and failure policy

The scanner is **Trivy 0.71.0**, pinned to container digest
`sha256:016eae51fdcf989332a5404af7e8f625cd5d95d7c0907a221d080a996f556500`.
It is invoked directly, rather than through a mutable scanner action. See the
[official immutable release](https://github.com/aquasecurity/trivy/releases/tag/v0.71.0)
and [image CLI documentation](https://trivy.dev/docs/latest/references/configuration/cli/trivy_image/).

Each image is analyzed once for OS and application package vulnerabilities.
The scan retains the full package inventory, filters findings to HIGH/CRITICAL,
and explicitly includes unfixed vulnerabilities. There are no ignore lists,
VEX suppressions, severity exceptions or `continue-on-error` settings. Advisory
database download failures, analysis failures, build failures, report-generation
failures, and any HIGH/CRITICAL finding fail the job.

The initial JSON scan uses exit code zero for findings so that evidence can be
generated. **This is not the security gate.** `trivy convert --exit-code 1`
evaluates the resulting HIGH/CRITICAL findings and fails the job after the SBOM
has been written. No scanner/database work is repeated during conversion.

For each successfully built image, the workflow attempts to retain these files
for 14 days even if the gate fails:

- `build.json`: exact build/scanner identity and pinned base references.
- `scan.json`: machine-readable HIGH/CRITICAL findings and complete package list.
- `vulnerabilities.txt`: package, vulnerability, severity, installed/fixed versions
  and remediation links from Trivy's detailed table.
- `sbom.cdx.json`: CycloneDX inventory converted from that same scan.

The job summary gives severity totals; the artifact is named
`image-security-<matrix-image>-<run-attempt>`. Download it from the failed job's
Artifacts section and update the implicated base or dependency in a reviewed
change. An unavailable fix remains a blocking finding, not an automatic waiver.
If analysis fails early, only the available evidence (such as build identity)
will be uploaded; consult the scanner step's error for the infrastructure cause.
There is no SARIF upload requiring `security-events: write`, and no broad workspace,
image archive, raw build log or Buildx build record is uploaded.

Permissions remain `contents: read`, checkout does not persist credentials, and
all jobs use GitHub-hosted Ubuntu. Only public package/advisory downloads and
standard Actions cache/artifact storage are used; no paid scanner, registry
account or repository secret is required. Actions usage remains subject to the
repository allowance. This is vulnerability inventory matching, not runtime
penetration testing, secret scanning, or a production deployment approval.

## Local reproduction and verification

Use new verification tags, never retained local-platform image tags:

```bash
docker build --pull --platform linux/amd64 -f agent/Dockerfile -t bankops-step71/agent:local agent
docker image save --output image.tar bankops-step71/agent:local
# Use the archive-only mounts and scanner digest from images.yml:
# trivy image --input /image.tar --scanners vuln --severity HIGH,CRITICAL \
#   --ignore-unfixed=false --ignorefile /dev/null --list-all-pkgs \
#   --format json --output /reports/scan.json --exit-code 0
# trivy convert --format cyclonedx --output /reports/sbom.cdx.json /reports/scan.json
# trivy convert --severity HIGH,CRITICAL --ignorefile /dev/null \
#   --format table --output /reports/vulnerabilities.txt --exit-code 1 /reports/scan.json
actionlint .github/workflows/ci.yml .github/workflows/images.yml
python -m pytest -q -W error .github/tests
```

Local archives, scanner caches and reports are kept under ignored
`local/results/step71/`. No Docker cleanup or volume operation is required.

### Step 71 local results

Verification date: **October 28, 2026**. All seven digest-pinned Dockerfiles built
successfully under separate `bankops-step71/*:local` tags using the existing warm
BuildKit cache. Both workflows passed actionlint 1.7.7. The combined launcher,
security harness and CI contract suite passed **72 tests**; the finalized CI-only
subset passed **12 tests**. Synthetic Trivy report conversion returned exit 1 for
a CRITICAL finding and exit 0 for a clean report.

The local scanner uses the same archive mounts, version/digest, severity policy,
JSON-to-SBOM conversion and blocking report conversion as CI. The cold advisory
download included approximately 130 MiB for the vulnerability database and
945 MiB for the Java index. Scan findings below are package/advisory occurrences,
not counts of distinct exploitable vulnerabilities. Package scope and reachability
require triage; the gate does not automatically waive vendor-unfixed findings.

The original Windows-mounted Airflow archive analysis was stopped for local I/O
performance before producing a completed report. Its partial log was preserved.
The three completed scans were reused; the remaining local runs copied their
read-only archive into the disposable scanner container's Linux filesystem before
analysis. This uses no named/anonymous data volume and does not change CI's
Linux-hosted archive scan or security policy.

All seven analyses and SBOM conversions completed successfully. All seven
security gates returned **exit code 1** because of findings:

| Image | HIGH | CRITICAL | Inventoried packages | Gate |
| --- | ---: | ---: | ---: | --- |
| banking | 0 | 4 | 259 | Blocked |
| agent | 49 | 0 | 154 | Blocked |
| frontend | 67 | 1 | 564 | Blocked |
| airflow | 161 | 19 | 2,839 | Blocked |
| airflow-test | 161 | 19 | 2,841 | Blocked |
| database | 44 | 0 | 91 | Blocked |
| jaeger | 5 | 0 | 347 | Blocked |

Examples requiring a separate reviewed remediation change:

- Banking: four CRITICAL Tomcat findings in `tomcat-embed-core` 11.0.24;
  Trivy lists 11.0.25 as a fixed version.
- Agent: 44 Debian HIGH occurrences plus five Python occurrences in `msgpack`,
  `urllib3` and bundled `setuptools`. Reports include both available fixes and
  vendor-unfixed findings.
- Frontend: Debian and Node package findings, including Trivy's CRITICAL
  `CVE-2023-45853` report against `zlib1g`. Vendor/package scope needs triage.
- Airflow: OS packages and bundled tooling contribute findings beyond the
  installed application-dependency inventory used by earlier audits. Examples
  include Perl/SQLite/libxml2 and Python tooling copies of `certifi` and `uv`.

These are actual scanner reports, not a clean security certification. No
dependency changes, suppressions or severity downgrades were made to turn the
gate green. The main vulnerability database used in this run reports
`UpdatedAt=2026-10-28T13:01:10.618103814Z`.

Local evidence is in `local/results/step71/build-results.json`,
`scan-results.json`, and each image's `scan.json`, `vulnerabilities.txt` and
`sbom.cdx.json`. The representative agent Buildx export also passed using
`--provenance=false --output type=docker,dest=...`, matching the workflow's
archive mode. Archives, logs and advisory caches remain ignored and local.

The workflow implementation is ready for its first hosted execution, but its
security gates will block the currently scanned image contents. Remaining work
is vulnerability triage/remediation and actual GitHub verification of action
execution, GHA layer/advisory cache restore/save, cold dependency resolution and
artifact uploads. Linux/amd64 is the only CI image platform. Full Step 70
functional suites were not rerun for this packaging-only change; its workflow
and existing contract tests remain valid. No push, deployment, application
restart, banking record change, Flyway V1–V6 edit, volume operation or destructive
Docker cleanup was performed.

Final verification parsed all seven CycloneDX files and checked that every gate
exit matched its HIGH/CRITICAL findings. Report/log text had no matches to local
credential values. All temporary scanner containers exited and were automatically
removed; the nine existing development runtime containers remained healthy.
Changes remain local and uncommitted, including the preserved Step 70 files.

# Step 71B remediation results

**Verified October 28, 2026 (America/Chicago).** The interrupted changes and
completed checks were preserved. Final reports reduce the baseline **245 unique
package/advisory/version findings (23 CRITICAL, 222 HIGH)** to **49 HIGH and
zero CRITICAL**. The strict policy remains unchanged: HIGH findings still fail
the corresponding jobs. This is a completed, verified remediation pass, not an
all-green security clearance.

| Image | Before HIGH / CRITICAL | After HIGH / CRITICAL | Final gate |
| --- | ---: | ---: | --- |
| banking | 0 / 4 | 0 / 0 | Pass |
| agent | 49 / 0 | 44 / 0 | Blocked: HIGH |
| frontend | 67 / 1 | 43 / 0 | Blocked: HIGH |
| airflow | 161 / 19 | 44 / 0 | Blocked: HIGH |
| airflow-test | 161 / 19 | 44 / 0 | Blocked: HIGH |
| database | 44 / 0 | 44 / 0 | Blocked: HIGH |
| jaeger | 5 / 0 | 5 / 0 | Blocked: HIGH |

The [complete deduplicated inventory](security/CONTAINER_FINDINGS.md) identifies
every original advisory ID, package, installed/fixed version, OS/application
classification, affected images and final disposition. It also lists all remaining
findings and exact blockers. There are 159 baseline rows no longer reported in
their original affected images; the other 86 baseline rows consolidate into 49
current version-specific findings after base-image convergence. The 245-to-49
change must not be read as 196 distinct CVEs fixed. All 23 baseline CRITICAL rows
are resolved/removed from final reports.

## Compatible fixes applied

- **Banking:** pinned Tomcat **11.0.27**, a maintained patch on the same Tomcat 11
  line, while keeping Spring Boot and Java 21 unchanged. This clears the four
  reported Tomcat CRITICAL findings. The full banking suite and the packaged
  application passed with dedicated migration/runtime identities. See
  [Apache's release information](https://tomcat.apache.org/index.html) and
  [Tomcat 11 security history](https://tomcat.apache.org/security-11.html).
- **Agent:** install the already-patched application lockfile into a dedicated
  build-stage virtual environment and copy only that environment into the runtime.
  Remove installers and their vulnerable vendored copies from the final image.
  The reported `msgpack`, `urllib3` and `setuptools` copies belonged to packaging
  tooling; unaffected application dependencies were not blindly upgraded.
  Non-root execution, health, API fail-closed behavior and disabled inference/
  remediation/Airflow capabilities were verified.
- **Frontend:** split build and runtime stages. The Node 22/Trixie runtime has a
  separate locked Vite 8.3.4 dependency closure, including the compatible fixed
  `picomatch` patch, and excludes React build plugins, TypeScript, Vitest, ESLint,
  Playwright, npm, Yarn and Corepack. `proxy.ts` holds the single shared security
  policy; the minimal preview config reuses it. Production-image checks verified
  operator/customer/reviewer credential preservation, agent-token separation,
  request bodies/idempotency keys, SPA routes and cross-origin/method denials.
- **Airflow:** keep **Airflow 3.3.2, task SDK 1.3.2, Python 3.12 and standard
  provider 1.19.0**. First evaluated the same-version upstream slim image, then
  verified a project-maintained runtime on the pinned Python 3.12/Trixie base.
  Exact Python constraints are in `airflow/requirements-runtime.lock`; unused
  cloud providers, JAR collections and isolated development-tool environments
  are not installed. Both synchronous and asynchronous PostgreSQL drivers are
  explicit in `requirements-airflow.txt`. A clean virtual environment is copied
  between identical base images, without foreign-distro library replacement.
  Non-root UID 50000/GID 0, local authentication, default-paused DAGs, and the
  existing start script are retained; Tini forwards signals to the process group.
  Build installers are removed after dependency validation.
- **OS packages:** use signed stable-distribution package upgrades within each
  selected base, retaining Java 21, Python 3.12 and Node 22. The Trixie base
  supplies maintained fixes for the Bookworm SQLite/zlib findings; no unsafe
  cross-distro `.so` substitution or package-metadata editing was used.
  [Debian SQLite status](https://security-tracker.debian.org/tracker/CVE-2025-7458)
  and [zlib status/vendor context](https://security-tracker.debian.org/tracker/CVE-2023-45853)
  support the base decision. Debian notes that the older zlib finding involves
  source-bundled MiniZip not built in those Bookworm binaries; it was still kept
  in the strict baseline gate rather than suppressed.
- **Database tool:** remove installation tooling after installing/checking the
  required psycopg runtime. The packaged tool's prepare/grant operations passed
  against a new fixture; no application runtime received administrator secrets.

Airflow's new base is a **project-maintained Python image**, not an assertion that
upstream publishes Airflow 3.3.2 on Trixie. Reproducible dependency constraints and
startup/DAG tests are required maintenance obligations. Optional cloud, XML/SAML,
development and arbitrary runtime-installation capabilities are intentionally not
included; adding a new operator/provider requires an explicit build and review.
This packaging continues to support the repository's four reconciliation tasks.

## Actual verification and intermediate failures

| Check | Final actual result |
| --- | --- |
| Java 21 full banking regressions | **219 passed**, zero failures/errors/skips |
| Packaged banking image | Dedicated Flyway migrate/validate, runtime ACL initialization, health and authenticated HTTP passed; financial tables remained empty |
| Reliability agent regressions | **487 passed** |
| Packaged agent runtime | Non-root imports, real installed entrypoint, HTTP health 200, unconfigured exposed API 503, no pip; inference/remediation/Airflow disabled |
| Airflow/database/SCRAM regressions | **59 passed**, including a new async metadata-driver initialization regression |
| Final Airflow runtime | API, scheduler and DAG processor healthy against disposable PostgreSQL; real read-only reconciliation DAG succeeded; DAG paused again; financial tables remained empty |
| Frontend lint, formatting, TypeScript, production build | All passed |
| Frontend component tests | **104 passed** on the serial verification run |
| Chromium desktop/mobile | **32 passed** |
| Built frontend runtime/proxies | Passed against synthetic HTTP stubs; no financial service was targeted |
| Launcher/security/CI contract tests | **72 passed** |
| Workflow YAML/expressions | Both Step 70 and image workflows passed actionlint 1.7.7 |
| Images, SBOMs and strict gates | All seven final analyses and CycloneDX generations completed; gates match the table above |

The first concurrent frontend unit attempt had 102 passes and two failures: a
five-second timeout followed by an account-history assertion failure. The complete
suite passed with one worker, without changing assertions or timeouts. CI's Step
70 test commands remain unchanged; resource-sensitive behavior under heavy local
Docker contention remains a limitation to monitor.

The first slim Airflow full-startup check caught missing `asyncpg`, which simple
imports and synchronous reconciliation tests had not exercised. Restored
`asyncpg==0.31.0`, the version in the previously working image, and added a test
that instantiates the PostgreSQL async engine without opening a connection. Full
startup then passed. A later verification CLI initially used Docker exec's
default metadata settings instead of the DSN assembled by the main start script;
the probe was corrected to call the normal configuration function. The final
real DAG verification passed against the intended disposable metadata database.

Final production/test Airflow rebuilds match the tested candidates' exact runtime
filesystem layers and runtime configurations. OCI index IDs can differ because
build attestations name the Dockerfile path; runtime equivalence was checked
directly, and the actual final tags were scanned again.

## Remaining findings and recommended actions

There are **44 distinct OS package/advisory/version findings** with no fixed
version in the current vendor feed, shared across the Trixie-based images. The
base packages were upgraded using the supported stable repositories. Some are
essential distribution packages or linked runtime libraries; removing them merely
to reduce scanner counts would compromise the supported base. Monitor Debian
stable security updates and refresh the pinned base/validated package set when
fixes are available. All affected images remain blocked by HIGH gates.

The other **five HIGH findings** are linked into the upstream Jaeger binary:

| Advisory | Package / installed | Fixed version indicated by scanner |
| --- | --- | --- |
| CVE-2026-78669 | `golang.org/x/net` v0.58.0 | 0.60.0 |
| CVE-2026-111943 | Go stdlib v1.27.1 | 1.27.3 on the current toolchain line |
| CVE-2026-78667 | Go stdlib v1.27.1 | 1.27.2 or later |
| CVE-2026-78669 | Go stdlib v1.27.1 | 1.27.2 or later |
| CVE-2026-97031 | Go stdlib v1.27.1 | 1.27.2 or later |

The queried Jaeger 2.22.1 and 2.23.0 image tags were unavailable. Updating apt or a
loose library cannot repair a statically linked Go executable. Next action is a
validated upstream rebuild with a patched Go toolchain and x/net, or a separately
maintained source build with upstream Jaeger integration coverage. No unverified
replacement binary or major Jaeger upgrade was applied.

No scanner, severity, ignore-list, ignore-unfixed, failure threshold or scan scope
was relaxed. The same pinned Trivy engine/policy was used for before/after
comparison. Scanner-engine upgrades should be reviewed separately and rescanned.
Hosted Actions/cache/artifact execution, multi-architecture images, production
TLS/deployment, and the complete unified-stack fault/recovery suite were not
verified in Step 71B. No images were pushed and no deployment occurred.

Evidence is retained under ignored `local/results/step71-remediation/`, including
the final scan manifest, image-specific JSON/table/SBOM files, comparison summary,
runtime checks and regression logs. The public inventory contains no credentials.
Step 70's workflow and Flyway V1–V6 hashes are unchanged. Only disposable test
clusters/roles were created; existing development roles, records, containers and
volumes were not modified. All verification services are stopped after checks;
verification images and logs remain available for review.
