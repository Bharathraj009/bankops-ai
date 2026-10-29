# Step 72: GitHub-hosted CI readiness

Verified October 29, 2026 (America/Chicago). **Local preflight completed; hosted
verification is blocked pending repository identification, publication review
and explicit approval. No GitHub run has occurred.**

## Local preflight results

| Check | Actual result |
| --- | --- |
| Initial Git state | `main`, HEAD `2600779`; Step 70/71/71B work remains uncommitted; nothing staged |
| Workflow YAML and expressions | Both workflows pass cached actionlint 1.7.7; optional shellcheck disabled |
| CI safety contracts | 12 passed on Windows; 12 passed inside the existing final Linux Airflow test image |
| Workflow permissions | Both declare only `contents: read`; no job overrides, persisted checkout credentials, registry publishing, OIDC, SARIF or repository secrets |
| Test commands and image paths | Four test jobs and all seven image/context/Dockerfile combinations match existing source and lockfiles |
| Linux compatibility | Ubuntu 24.04, Bash, Java 21, Python 3.12, Node 22; wrapper invoked with `bash` rather than requiring executable mode; tracked shell scripts have LF endings; no case-colliding candidate paths |
| Credentials | No live credential pattern or long local-secret value matched candidate source or reachable named historical blobs; two literal candidates reviewed as synthetic test values |
| Banking records | Publication blocker: two tracked development workflow artifacts also exist in history; see below |
| Generated scan reports | `local/results/`, frontend `.cache/`, audit JSON, logs and private dotenv files are ignored and absent from the index |
| Large files | Nothing staged; no tracked/unignored candidate over 1 MiB; largest is the approximately 174 KiB frontend lockfile |
| Flyway V1-V6 and Step 70 workflow | Recorded SHA-256 hashes unchanged |
| Existing security fixes | Preserved; strict HIGH/CRITICAL policy unchanged |

The Linux verification used an automatically removed container, no network and a
read-only repository mount. It connected to no database. Full application suites
and image builds were not repeated locally; their prior results remain recorded
in [Step 71B](STEP71B_CLOSEOUT.md). Linux contract checks do not establish that
all hosted installs, builds or application suites pass.

The local audit inspected current tracked/unignored files and all 626 reachable
Git objects (scanning named blobs), using credential patterns and matching long
values from local secret settings without printing those values. The only
credential-literal candidates in source/history are mocked provider configuration
in `agent/src/bankops_agent/verify_groq.py` and the synthetic test credential in
`local/tests/test_platform.py`. This is a scoped scan, not proof of absence of
every possible credential or private record. Raw settings and matched values are
not included in this report.

## Publication blocker: historical banking response artifacts

These tracked files contain account/transfer identifiers, balances, idempotency
keys, timestamps and actual development API response bodies:

- `backups/workflow-<private-run>.json`
- `backups/workflow-<private-run>-report.md`

The report documents a development test with generated account names, rather than
evidence of production customer data. Nevertheless, publication of those actual
development responses has not been authorized. Both artifacts are reachable from
commit `ac4cff5`. Do not publish the current history until this is resolved.

Added ignore patterns for future generated workflow response JSON/reports. Ignore
rules neither untrack existing files nor remove historical copies. Existing files
and history were preserved. A normal deletion commit would still publish their
earlier contents. Recommended publication approach: an explicitly approved clean
initial snapshot in a separate checkout, excluding these two artifacts and all
ignored local data, while preserving this workspace/history as the local archive.
Alternatively, explicitly authorize publication of the reviewed development
artifacts or separately approve history sanitization. No history rewrite, data
deletion or new repository was performed.

## GitHub access and intended target

No Git remote or upstream for `main` is configured. No intended owner/repository
can therefore be established from Git configuration. Do not infer a target from
the project name or credential account.

GitHub CLI is not installed and no `GH_TOKEN`/`GITHUB_TOKEN` environment variable
is present. Git Credential Manager is configured and lists the GitHub account
`<local-account-redacted>`; tokens were not retrieved or displayed. That confirms a stored
account, not a successful authenticated GitHub API request, current token validity
or authorization to a particular repository. A repository URL and explicit
publication approval are still required. No login, remote edit, repository
creation, commit, push, PR creation or workflow dispatch was performed.

## Safe commit and execution plan

1. Supply the exact existing GitHub owner/repository URL, intended visibility and
   target/default branch. Review repository access, Actions policies and available
   runner/artifact/cache allowance without changing settings.
2. Choose and authorize the historical-artifact handling above. Prefer a separate
   clean initial snapshot when preserving the local archive is desired. Review
   the complete snapshot, not only the current uncommitted diff, before first
   publication.
3. Keep all Step 70, 71 and 71B source dependencies together in the publication:
   `.github/` workflows/helpers/contracts, patched Dockerfiles and dependency
   constraints, frontend proxy/preview/runtime files and runtime verifier,
   Airflow runtime lock/tool-removal helper and regression, plus README/security/CI
   documentation and ignore rules. Step 72 adds this report and future generated
   backup ignore rules. The local `commit-plan.json` lists the candidate changed
   paths. Stage explicit reviewed paths; never use `git add -A`, `git add .` or
   force-add ignored artifacts. No migrations belong in the commit.
4. Proposed commit subject: `Prepare BankOps AI hosted CI and preserve strict image gates`.
   This is a plan only; nothing is staged or committed. Recheck the staged diff,
   credentials, data exclusions, file sizes and V1-V6 hashes after preparation.
5. Obtain explicit approval for the exact commit/snapshot, destination/ref and
   push. If a remote must be added, approve that separately. Do not force-push or
   overwrite an existing branch. A push to `main` triggers both workflows; a
   non-main review branch needs an approved PR targeting `main` to trigger them.
   Do not push to a branch and assume the current push filter will run there.
6. Manual dispatch is available only after the workflow exists on the default
   branch. Request dispatch approval if not already included in execution
   authorization. Avoid duplicate push/dispatch runs. Confirm zero paid usage is
   possible under the repository owner's billing controls before starting runs.

The [GitHub workflow reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
documents permissions and the default-branch prerequisite for manual dispatch.
The [Actions billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
explains included usage, artifact/cache allowances and budget controls. These
repository/account settings cannot be established without an identified target.
Do not assume private hosted execution and artifact retention are free.

## Expected hosted behavior and evidence

| Workflow/job | Hosted verification required |
| --- | --- |
| CI / backend | Temurin Java 21, disposable PostgreSQL 17, Maven wrapper tests including runtime identity/ACL and Flyway compatibility |
| CI / agent | Python 3.12, locked dependencies, `pip check`, mocked-inference pytest suite |
| CI / airflow-database | Build existing Airflow test Dockerfile; run reconciliation, provisioning and SCRAM tests against its fresh PostgreSQL service |
| CI / frontend | Node 22; npm install, lint, format, types, components, build; locked Chromium desktop/mobile; launcher/security/CI contracts |
| Image security / seven matrix entries | Build Linux amd64 Docker archives without pushing; scan OS/application packages; generate CycloneDX SBOM; enforce HIGH/CRITICAL gate; upload narrow evidence |

Test jobs are expected to pass based on prior local verification; only actual
hosted execution can confirm this. For images, the preserved Step 71B snapshot
expects banking to pass and **agent (44 HIGH), frontend (43), Airflow (44),
Airflow-test (44), database tooling (44), and Jaeger (5) to fail**. The shared
total is 49 unique findings, not the sum of per-image counts. The 44 OS findings
had no vendor fixed version; five Jaeger findings require a patched binary.
Fresh hosted advisory databases and supported package upgrades may change counts,
including banking's result. Do not force expected counts or waive new findings.

`fail-fast: false` lets every image finish despite another gate failure. The JSON
scan uses exit zero to preserve evidence, followed by a separate strict conversion
gate with exit one for HIGH/CRITICAL, including unfixed issues. No ignore file or
`continue-on-error` bypass is allowed. SBOM generation occurs before the gate.
Evidence upload runs after failure for successfully built images. It uploads only
`build.json`, `scan.json`, `vulnerabilities.txt`, `sbom.cdx.json`, with a unique
image/attempt name and 14-day retention. Infrastructure failures may leave partial
evidence; they must not be reported as a completed clean scan.

Artifact/cache service credentials are supplied by the Actions runtime; the
workflows do not need repository write, package write, OIDC or SARIF permissions.
Repository policy, quota and fork approvals still need hosted confirmation.
The [artifact action documentation](https://github.com/actions/upload-artifact)
describes artifact naming, retention and missing-file behavior. Existing action
major references are unchanged; resolving/pinning their exact implementations is
separate work, not a dependency migration in Step 72.

After authorized execution, record the repository/ref/commit SHA, both run URLs,
run IDs/attempts and every job conclusion. Confirm all seven image builds and
scans actually finished; parse downloaded JSON/SBOM artifacts and compare their
counts to each gate outcome. Verify artifact identities, retention and uploads
from the six expected failed jobs, not just a green build step. Reconcile new
advisories with the inventory and report missing/partial artifacts explicitly.

For failures, inspect the first failing named step and its exit code. Backend
diagnostics summarize counts without uploading raw Surefire XML. Pytest and
Chromium failures remain in step logs. Image jobs provide severity summaries and
the narrow artifacts even after a gate fails. Do not enable shell tracing, dump
environment/container configurations, or upload raw browser traces, credentials,
banking responses or the whole workspace. A red image workflow due to known HIGH
findings is expected policy enforcement; it is not an all-green CI result.

## Stop point

No production deployment, paid service, development database access, Docker volume
operation, migration edit or dependency migration occurred. No full image rebuild
or full application suite was necessary locally. Local evidence is retained in
ignored `local/results/step72/` (publication audit, candidate commit plan and
validation summary); Step 71B reports remain intact.

**Needed next:** identify the existing repository and approve the exact safe
publication/history approach, destination/ref, any remote addition and workflow
execution after checking the no-paid-usage condition. Hosted results remain
unverified. Step 72 stops at this approval boundary.
