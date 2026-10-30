> Historical local assessment, 2026-10-29. The changes were subsequently published
> in `8dff277`; see [hosted verification](../docs/verification/HOSTED_BASELINE.md).
> Pending-publication wording below records the original local review state.

# Step 72C: remaining security findings

Verified October 29, 2026 (America/Chicago). **49 -> 44 unique HIGH findings;
zero CRITICAL. Five application findings resolved locally; 44 vendor-unfixed
Trixie package findings remain blocking. No push or deployment was performed.**

## Evidence and counting

Started from all seven downloaded [hosted image-security artifacts](https://github.com/Bharathraj009/bankops-ai/actions/runs/40894518592)
for root commit `e89a44b`, the final Step 71B scan manifests and the prior
remediation history. The canonical hosted JSON reproduces 49 findings across
12 CVEs: 44 OS package/advisory findings across eight CVEs, plus five Go findings
across four CVEs. Deduplication keys are advisory, package, installed version,
fixed version and ecosystem; multiple binary packages from one vulnerable source
package remain distinct findings. These are not 49 distinct CVEs.

Fresh scans use the same digest-pinned Trivy 0.71.0 and HIGH/CRITICAL policy,
including unfixed vulnerabilities and an empty ignore file. The advisory database
was downloaded on October 29 and frozen for the before/after scans. The old Jaeger
image reproduced its five HIGH findings; its replacement reports none. All five
unchanged OS images were rescanned without rebuilding them. There are no new
findings. Banking remains unchanged; its zero-finding result is from hosted CI.

## Compatible remediation applied

`local/Dockerfile.jaeger` now rebuilds the exact Jaeger **2.22.0** source commit
`462bb49fcff9af4be9556bf0206d07f5171bd8d7`, retaining the existing pinned runtime
base, UID 10001, entrypoint, defaults and BusyBox health check. The upstream 2.22.0
UI release assets are retained, not rebuilt or upgraded. Source and UI archives
are SHA-256 pinned; the UI checksum was verified against GitHub release metadata.

The static Go binary is rebuilt with **Go 1.27.3** and **x/net 0.60.0**.
The latter's minimum dependency closure requires x/crypto 0.57.0, x/sys 0.48.0,
x/term 0.46.0 and x/text 0.42.0. The actual go.mod delta and embedded module
versions were inspected. Other application versions and storage/backend contracts
are unchanged. Module checksums are verified, builds/tests use readonly module
mode after resolution, and no foreign distribution libraries enter the runtime.

This is a project-maintained build of the existing application version, not a
major Jaeger upgrade. The previously unavailable 2.22.1/2.23.0 image tags were not
retried. No installer/library file removal, package metadata editing, unstable
Debian repository or scanner suppression was used to improve counts.

| Resolved advisory | Package | Before | Patched runtime |
| --- | --- | --- | --- |
| CVE-2026-111943 | Go stdlib / crypto/x509 | 1.27.1 | 1.27.3 |
| CVE-2026-78667 | Go stdlib / net/http | 1.27.1 | 1.27.3 |
| CVE-2026-78669 | Go stdlib HTTP/2 | 1.27.1 | 1.27.3 |
| CVE-2026-78669 | golang.org/x/net HTTP/2 | 0.58.0 | 0.60.0 |
| CVE-2026-97031 | Go stdlib / crypto/tls | 1.27.1 | 1.27.3 |

Primary patch and affected-symbol references:
[Go release history](https://go.dev/doc/devel/release#go1.27.3),
[x509](https://pkg.go.dev/vuln/GO-2026-6809),
[HTTP Range](https://pkg.go.dev/vuln/GO-2026-6609),
[HTTP/2](https://pkg.go.dev/vuln/GO-2026-6611),
[TLS ECH](https://pkg.go.dev/vuln/GO-2026-6607).

## Exploitability and prioritization

**Priority 1, fixed: network-facing Jaeger code.** HTTP/2 settings-frame abuse
can exhaust CPU at a reachable client/server peer; OTLP gRPC uses HTTP/2.
The query UI's static handler invokes `http.FileServer`, providing a plausible
path to the Range-header CPU issue. These were prioritized over conditional
local OS issues. TLS ECH exhaustion requires an applicable TLS server setup;
x509 distrust requires relevant outbound certificate verification. The repository's
default local Jaeger setup is plaintext/memory-backed, so those TLS conditions
are not established there. The patches remove the affected versions regardless.
This investigation did not attempt a destructive denial-of-service exploit.

**Priority 2, blocked on supported vendor fixes: local OS paths.** All five
inspected images run as non-root users; Airflow's UID 50000 retains GID 0 as before.
They have unconfigured fstab files, no systemd-homed binary and no Archive::Tar
module at the checked standard Perl paths. They do contain infocmp, nsenter and
setuid mount. Application source searches found no direct invocation of the
vulnerable CLI/ACL entry points. These observations reduce demonstrated exposure;
they do not prove arbitrary transitive code paths unreachable or justify a waiver.

| OS advisory/family | Required path or attacker prerequisite | Supported fix status |
| --- | --- | --- |
| CVE-2025-69720 / ncurses | Crafted input to infocmp; utility is present but not invoked by an identified application route | Trixie remains vulnerable; unstable fixed source version 6.6+20251231-1 |
| CVE-2026-16742 / systemd | Local logged-in homed-managed user and vulnerable systemd-homed; homed binary absent | Trixie remains vulnerable; unstable fixed at 261.2-1 |
| CVE-2026-54369 / acl | Privileged ACL pathname operation on attacker-controlled symlink components | Trixie remains vulnerable; unstable fixed at 2.4.0-1; vendor notes ABI/backport constraints |
| CVE-2026-76642 / util-linux | Authorized mount helper failure followed by privileged post-hooks | No Trixie fix; unstable fixed at 2.42.3-1 |
| CVE-2026-78408 / util-linux | Privileged operator uses nsenter --join-cgroup against an attacker-controlled target | No Trixie fix; unstable fixed at 2.42.4-1 |
| CVE-2026-78409 / util-linux | Authorized X-mount.subdir entry and intermediate symlink control | No Trixie fix; unstable fixed at 2.42.3-1 |
| CVE-2026-78410 / util-linux | User-authorized bind mount, writable source ancestry and privileged mount options | No Trixie fix; unstable fixed at 2.42.3-1 |
| CVE-2026-9538 / perl | Archive::Tar parses a hostile tar header; module absent from inspected runtime paths | Trixie remains vulnerable; unstable Perl fixed at 5.42.3-1; Archive::Tar upstream fix 3.10 |

Signed stable repository policy checks offered exactly the installed source-family
versions: util-linux 2.41.5-0+deb13u1, ncurses 6.5+20250216-2, libacl1
2.3.2-2+b1, libsystemd0 257.13-1~deb13u1 and perl-base 5.40.1-6+deb13u1.
Several implicated packages are Essential, and other libraries are dependencies
of base utilities. No compatible supported apt update is currently available.
Do not substitute unstable shared libraries or force-remove essential packages.

Vendor records:
[ncurses](https://security-tracker.debian.org/tracker/CVE-2025-69720),
[systemd](https://security-tracker.debian.org/tracker/CVE-2026-16742),
[acl](https://security-tracker.debian.org/tracker/CVE-2026-54369),
[util-linux helper](https://security-tracker.debian.org/tracker/CVE-2026-76642),
[nsenter](https://security-tracker.debian.org/tracker/CVE-2026-78408),
[subdir](https://security-tracker.debian.org/tracker/CVE-2026-78409),
[bind mounts](https://security-tracker.debian.org/tracker/CVE-2026-78410),
[Perl](https://security-tracker.debian.org/tracker/CVE-2026-9538).

The October 28 CISA KEV feed checked during this investigation contains none of
these 12 CVEs. Absence from [KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
is not evidence that exploitation is impossible or has not occurred. Debian marks
several issues minor/no-DSA or postponed; Trivy's HIGH classifications and blocking
policy are retained without modification.

There is no production deployment established by this project. Reachability was
assessed for intended packaged/local configurations and the isolated candidate,
not certified for every possible deployment. The retained development stack still
runs its older images; this local fix has not been rolled out there. Localhost
publication and internal Docker networks limit access but are not authentication,
TLS or a security boundary against a compromised host/container administrator.

## Verification and final gates

| Check | Actual result |
| --- | --- |
| Upstream targeted UI, query and storage unit-test packages | All three packages passed during the build |
| Focused agent Jaeger regressions | 38 passed |
| Real candidate runtime | UID 10001, no-new-privileges and no attached volumes |
| UI/API compatibility | HTML/static assets and /api/v3/services passed |
| Trace integration | Synthetic OTLP HTTP ingest and actual agent collection passed; private synthetic attributes excluded from projected evidence |
| Candidate vulnerability analysis/SBOM | Completed; zero HIGH/CRITICAL; strict gate exit 0 |
| Five OS image analyses/SBOMs | Completed; strict gates exit 1 on remaining HIGH findings |

A smoke-harness attempt initially lacked a Python import; corrected the harness,
then completed the checks without changing application assertions. A concurrent
scanner attempt hit Trivy's filesystem-cache lock; repeated that scan serially
with the same archive/database. Neither infrastructure failure was counted as a
clean result. Full banking/frontend/Airflow suites were not repeated because
those application sources and images were unchanged; their hosted CI passed in
Step 72B. No Cassandra/Elasticsearch or production TLS integration certification
is claimed for the project-maintained Jaeger build.

| Image | HIGH | CRITICAL | Gate / evidence |
| --- | ---: | ---: | --- |
| Banking | 0 | 0 | Pass; unchanged hosted result |
| Jaeger | 0 | 0 | Pass; fresh local scan |
| Agent | 44 | 0 | Fail; fresh local scan |
| Frontend | 43 | 0 | Fail; fresh local scan |
| Airflow | 44 | 0 | Fail; fresh local scan |
| Airflow-test | 44 | 0 | Fail; fresh local scan |
| Database tooling | 44 | 0 | Fail; fresh local scan |

Blocking HIGH/CRITICAL thresholds, unfixed coverage, scanner pin, ignore policy
and both CI workflow files are unchanged. Flyway V1-V6 hashes are unchanged.
Changes are local to the publication checkout and are not committed or pushed.
The public repository's previous six failed image jobs will remain historical
until an explicitly approved push runs the revised Dockerfile.

Evidence is retained under ignored `.publication/step72c/`: deduplicated before
findings, seven fresh scan/SBOM/table sets (old/new Jaeger and five OS images),
image exports, frozen scanner DB metadata, vendor snapshots, package policy,
runtime inventories, build/module logs, integration results and summary.json.
`bankops-step72c/jaeger:verified` names the tested image. Verification containers
are removed; development databases/volumes and the original repository are unchanged.

## Remaining findings by package

Every remaining row is vendor-unfixed in the supported Trixie feed. Track signed
stable updates and refresh/test only affected images when a supported fix arrives.
The following full ledger also records the five resolved application findings.

| Advisory | Class | Package | Before installed | Fixed version in baseline report | Images | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| CVE-2025-69720 | OS | libncursesw6 | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database | Remaining: no Trixie fix |
| CVE-2025-69720 | OS | libtinfo6 | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2025-69720 | OS | ncurses-base | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2025-69720 | OS | ncurses-bin | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-111943 | Application | stdlib | v1.27.1 | 1.26.10, 1.27.3 | jaeger | Resolved in patched Jaeger |
| CVE-2026-16742 | OS | libsystemd0 | 257.13-1~deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-16742 | OS | libudev1 | 257.13-1~deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-54369 | OS | libacl1 | 2.3.2-2+b1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-76642 | OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78408 | OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78409 | OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78410 | OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-78667 | Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Resolved in patched Jaeger |
| CVE-2026-78669 | Application | golang.org/x/net | v0.58.0 | 0.60.0 | jaeger | Resolved in patched Jaeger |
| CVE-2026-78669 | Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Resolved in patched Jaeger |
| CVE-2026-9538 | OS | perl-base | 5.40.1-6+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | Remaining: no Trixie fix |
| CVE-2026-97031 | Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Resolved in patched Jaeger |
