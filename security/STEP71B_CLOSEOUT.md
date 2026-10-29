# Step 71B closeout

Verified October 29, 2026 (America/Chicago). Step 71B is complete with unresolved
HIGH findings. This is not a passing release security assessment.

## Final security result

The preserved baseline and final reports confirm **245 -> 49 unique findings**
and **23 -> 0 CRITICAL** findings. Counts deduplicate advisory, package,
installed/fixed version and ecosystem across images; they are not unique CVE counts.

| Final image | HIGH | CRITICAL | Strict gate |
| --- | ---: | ---: | --- |
| Banking | 0 | 0 | Pass |
| Agent | 44 | 0 | Fail |
| Frontend | 43 | 0 | Fail |
| Airflow | 44 | 0 | Fail |
| Airflow test | 44 | 0 | Fail |
| Database tooling | 44 | 0 | Fail |
| Jaeger | 5 | 0 | Fail |

The [complete inventory](CONTAINER_FINDINGS.md) records every remaining finding,
affected image, installed/fixed version and next action. The 44 shared OS findings
have no fixed version in the preserved vendor feed. The five Jaeger findings
require a binary rebuilt with patched Go/x/net dependencies. These are snapshot
results, not a fresh advisory-feed check. Exploitability has not been established
or ruled out. Track vendor fixes and validate a maintained upstream Jaeger build
in separate work; no further major dependency migration belongs to this step.

All strict HIGH/CRITICAL gates remain enabled, including unfixed findings.
No severity threshold, ignore list, scanner scope or failure behavior was relaxed.
Six image jobs remain expected to fail. Existing security fixes are preserved.

## Preserved evidence

All seven baseline and seven final image report sets remain on disk, each with
Trivy JSON, CycloneDX SBOM and vulnerability table. Banking's final table is empty
because it has no findings. Final scans, severity counts and gate statuses were
read directly and checked against `scan-results-final.json` without rescanning.

Evidence remains under ignored `local/results/step71/` and
`local/results/step71-remediation/`. Use the final manifest's `report_dir` mapping:
Airflow's final directories are `airflow-trixie-final` and
`airflow-test-trixie-final`; older intermediate directories are historical.
`closeout-evidence.json` records SHA-256 hashes for all 42 baseline/final report
files. `comparison-summary.json`, regression logs and runtime results remain
preserved. These local artifacts are not committed or remotely backed up by this
step. Do not delete the results directories; runtime fixture files may contain
private settings and should not be published wholesale.

The completed banking, agent, frontend, Chromium and Airflow suites were not
repeated. Their actual results and limitations are in
[CI.md](../CI.md#actual-verification-and-intermediate-failures).

## Container and Git verification

Removed **139 stopped temporary BankOps containers** from earlier verification
runs, retaining their volumes, images and report files. No force removal, volume
deletion or global Docker prune was used. No temporary BankOps verification
containers remain. Existing development provisioning jobs remain stopped after
their earlier successful completion; they are not temporary test services.
Unrelated projects and older standalone development containers were retained.

The existing `bankops-step67-4c201966c1cb` development stack was found stopped.
Restarted its existing containers without builds, recreation or provisioning jobs.
All nine long-running services report Docker health **healthy**: PostgreSQL,
Airflow metadata PostgreSQL, banking, agent, frontend, Airflow, Jaeger, Prometheus
and Grafana. The captured inventory is `closeout-container-inventory.txt`; the
removed-container list is `closeout-removed-containers.txt`.

The retained development stack runs its existing images, not the newly verified
remediation images. Its health does not establish that the running images have
the final vulnerability counts. Applying the remediation images to that stack
would be a separate rollout and was not performed here.

Reviewed the tracked diff and untracked source list. `git diff --check` passes.
The protected Step 70 CI workflow and Flyway V1-V6 match their recorded SHA-256
hashes. Both workflows pass the existing actionlint 1.7.7 validator (YAML and
GitHub expressions; optional shellcheck disabled). Validation used a read-only
repository mount, no network and an automatically removed validator container.
Results are in `closeout-workflow-validation.json`. Hosted Actions execution
remains unverified; this local check does not claim a hosted CI pass.

Changes remain uncommitted for review. No images were rebuilt, no completed suites
were rerun, and nothing was pushed or deployed during closeout. No banking SQL,
financial data operations, volume changes, migration edits or explicit migration
commands were performed. Normal service startup and health checks ran.

Step 71B stops here. Remaining HIGH findings, the retained development-image gap,
local-only evidence retention and unverified hosted CI remain explicit risks.
