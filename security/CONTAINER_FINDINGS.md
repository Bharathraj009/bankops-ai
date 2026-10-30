# Step 71B container vulnerability inventory

Latest local assessment: [Step 72C](STEP72C_FINDINGS.md). The Step 71B rows below
are historical; five Jaeger findings are now resolved in the verified local image.


Final artifact, container and workflow verification: [Step 71B closeout](STEP71B_CLOSEOUT.md).

Generated from the actual baseline and final Trivy JSON reports. Snapshot: October 28, 2026 (America/Chicago).

Rows deduplicate advisory + package + installed/fixed version + ecosystem across images. Counts represent package/advisory findings, not distinct CVEs or exploitability determinations. No findings are suppressed.

Baseline: **245** unique findings ({'CRITICAL': 23, 'HIGH': 222}).
Final: **49** unique findings ({'HIGH': 49}).

## Remaining findings

| Advisory | Level / ecosystem | Package | Installed | Fixed version in report | Images | Blocker / next action |
|---|---|---|---|---|---|---|
| CVE-2025-69720 | OS / HIGH / debian | libncursesw6 | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2025-69720 | OS / HIGH / debian | libtinfo6 | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2025-69720 | OS / HIGH / debian | ncurses-base | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2025-69720 | OS / HIGH / debian | ncurses-bin | 6.5+20250216-2 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-111943 | Application / HIGH / gobinary | stdlib | v1.27.1 | 1.26.10, 1.27.3 | jaeger | Linked into upstream Jaeger binary; fixed Go/x/net versions require a validated upstream rebuild. Queried 2.22.1/2.23.0 image tags were unavailable. No unverified binary replacement. |
| CVE-2026-16742 | OS / HIGH / debian | libsystemd0 | 257.13-1~deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-16742 | OS / HIGH / debian | libudev1 | 257.13-1~deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-54369 | OS / HIGH / debian | libacl1 | 2.3.2-2+b1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-76642 | OS / HIGH / debian | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78408 | OS / HIGH / debian | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78409 | OS / HIGH / debian | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | libmount1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | mount | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78410 | OS / HIGH / debian | util-linux | 2.41.5-0+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (affected); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-78667 | Application / HIGH / gobinary | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Linked into upstream Jaeger binary; fixed Go/x/net versions require a validated upstream rebuild. Queried 2.22.1/2.23.0 image tags were unavailable. No unverified binary replacement. |
| CVE-2026-78669 | Application / HIGH / gobinary | golang.org/x/net | v0.58.0 | 0.60.0 | jaeger | Linked into upstream Jaeger binary; fixed Go/x/net versions require a validated upstream rebuild. Queried 2.22.1/2.23.0 image tags were unavailable. No unverified binary replacement. |
| CVE-2026-78669 | Application / HIGH / gobinary | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Linked into upstream Jaeger binary; fixed Go/x/net versions require a validated upstream rebuild. Queried 2.22.1/2.23.0 image tags were unavailable. No unverified binary replacement. |
| CVE-2026-9538 | OS / HIGH / debian | perl-base | 5.40.1-6+deb13u1 | not available | agent, airflow, airflow-test, database, frontend | No fixed version in vendor feed (fix_deferred); supported Trixie packages already upgraded. Track Debian stable security updates; retain essential runtime libraries. |
| CVE-2026-97031 | Application / HIGH / gobinary | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | Linked into upstream Jaeger binary; fixed Go/x/net versions require a validated upstream rebuild. Queried 2.22.1/2.23.0 image tags were unavailable. No unverified binary replacement. |

## Baseline disposition (all 245 original findings)

The after-image column includes every final affected image for that advisory/package, including changed base-image exposures. Resolved/partial/remaining is evaluated in each row's original affected images. A version update is not called resolved if the same advisory/package is still reported there.

| Advisory | Severity / level | Package | Before version | Fixed version in baseline | Before images | Final affected images | Current installed versions in original images | Disposition |
|---|---|---|---|---|---|---|---|---|
| CVE-2023-45853 | CRITICAL / OS | zlib1g | 1:1.2.13.dfsg-1 | not available | airflow, airflow-test, frontend | none | 1.3.dfsg+really1.3.1 | Resolved/removed |
| CVE-2025-7458 | CRITICAL / OS | libsqlite3-0 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | 3.46.1 | Resolved/removed |
| CVE-2025-7458 | CRITICAL / OS | sqlite3 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-13221 | CRITICAL / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-13221 | CRITICAL / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-13221 | CRITICAL / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-13221 | CRITICAL / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-42496 | CRITICAL / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-42496 | CRITICAL / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-42496 | CRITICAL / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-42496 | CRITICAL / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-60002 | CRITICAL / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-65182 | CRITICAL / Application | org.apache.tomcat.embed:tomcat-embed-core | 11.0.24 | 11.0.25, 10.1.58, 9.0.121 | banking | none | 11.0.27 | Resolved/removed |
| CVE-2026-65637 | CRITICAL / Application | org.apache.tomcat.embed:tomcat-embed-core | 11.0.24 | 11.0.25, 10.1.59, 9.0.121 | banking | none | 11.0.27 | Resolved/removed |
| CVE-2026-65905 | CRITICAL / Application | org.apache.tomcat.embed:tomcat-embed-core | 11.0.24 | 11.0.25, 10.1.58, 9.0.121 | banking | none | 11.0.27 | Resolved/removed |
| CVE-2026-6653 | CRITICAL / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-68525 | CRITICAL / Application | org.apache.tomcat.embed:tomcat-embed-core | 11.0.24 | 11.0.25, 10.1.58, 9.0.121 | banking | none | 11.0.27 | Resolved/removed |
| CVE-2026-8376 | CRITICAL / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8376 | CRITICAL / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8376 | CRITICAL / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-8376 | CRITICAL / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| GHSA-6q48-6c7w-9gw2 | CRITICAL / Application | certifi | 2026.6.17 | 2026.10.18 | airflow, airflow-test | none | 2026.10.19 | Resolved/removed |
| GHSA-hq85-5cpj-mr62 | CRITICAL / Application | uv | 0.12.15 | 0.13.4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2023-2953 | HIGH / OS | ldap-utils | 2.5.13+dfsg-5 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2023-2953 | HIGH / OS | libldap-2.5-0 | 2.5.13+dfsg-5 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2024-28757 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2025-47273 | HIGH / Application | setuptools | 70.3.0 | 78.1.1 | agent, airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2025-59375 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u5 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2025-69720 | HIGH / OS | libncurses6 | 6.4-4 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2025-69720 | HIGH / OS | libncursesw6 | 6.4-4 | not available | airflow, airflow-test | agent, airflow, airflow-test, database | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | libncursesw6 | 6.5+20250216-2 | not available | agent, database | agent, airflow, airflow-test, database | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | libtinfo6 | 6.4-4 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | libtinfo6 | 6.5+20250216-2 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | ncurses-base | 6.4-4 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | ncurses-base | 6.5+20250216-2 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | ncurses-bin | 6.4-4 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2025-69720 | HIGH / OS | ncurses-bin | 6.5+20250216-2 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 6.5+20250216 | Remaining |
| CVE-2026-102276 | HIGH / Application | brace-expansion | 2.0.2 | 5.0.10, 3.0.7, 2.1.5, 1.1.19 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-102278 | HIGH / Application | brace-expansion | 2.0.2 | 5.0.11, 3.0.8, 2.1.6, 1.1.20 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-102554 | HIGH / Application | com.google.guava:guava | 32.0.1-jre | 33.7.2 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-103111 | HIGH / OS | libpcre2-8-0 | 10.42-1+deb12u1 | 10.42-1+deb12u2 | airflow, airflow-test | none | 10.46 | Resolved/removed |
| CVE-2026-106553 | HIGH / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-106555 | HIGH / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-106583 | HIGH / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-111064 | HIGH / Application | aiohttp | 3.14.3 | 3.14.4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-111066 | HIGH / Application | aiohttp | 3.14.3 | 3.14.4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-111497 | HIGH / OS | libbrotli1 | 1.0.9-2+b6 | 1.0.9-2+deb12u1 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-111943 | HIGH / Application | stdlib | v1.26.8 | 1.26.10, 1.27.3 | airflow, airflow-test | jaeger | package/copy absent | Resolved/removed |
| CVE-2026-111943 | HIGH / Application | stdlib | v1.27.1 | 1.26.10, 1.27.3 | jaeger | jaeger | v1.27.1 | Remaining |
| CVE-2026-114613 | HIGH / Application | msgpack | 1.1.2 | 1.2.3 | agent, airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-11822 | HIGH / OS | libsqlite3-0 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | 3.46.1 | Resolved/removed |
| CVE-2026-11822 | HIGH / OS | sqlite3 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-11824 | HIGH / OS | libsqlite3-0 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | 3.46.1 | Resolved/removed |
| CVE-2026-11824 | HIGH / OS | sqlite3 | 3.40.1-2+deb12u2 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-12064 | HIGH / OS | curl | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-12064 | HIGH / OS | libcurl3-gnutls | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-12064 | HIGH / OS | libcurl4 | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-13149 | HIGH / Application | brace-expansion | 2.0.2 | 5.0.7, 1.1.16, 2.1.2 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-14257 | HIGH / Application | brace-expansion | 2.0.2 | 5.0.8, 3.0.3, 2.1.3, 1.1.17 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-16742 | HIGH / OS | libsystemd0 | 252.39-1~deb12u2 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 257.13 | Remaining |
| CVE-2026-16742 | HIGH / OS | libsystemd0 | 257.13-1~deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 257.13 | Remaining |
| CVE-2026-16742 | HIGH / OS | libudev1 | 252.39-1~deb12u2 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 257.13 | Remaining |
| CVE-2026-16742 | HIGH / OS | libudev1 | 257.13-1~deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 257.13 | Remaining |
| CVE-2026-25210 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-33671 | HIGH / Application | picomatch | 4.0.3 | 4.0.4, 3.0.2, 2.3.2 | frontend | none | 4.0.4 | Resolved/removed |
| CVE-2026-41992 | HIGH / OS | gzip | 1.12-1 | not available | airflow, airflow-test, frontend | none | 1.13 | Resolved/removed |
| CVE-2026-42497 | HIGH / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-42497 | HIGH / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-42497 | HIGH / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-42497 | HIGH / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-45186 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-48815 | HIGH / Application | sigstore | 3.1.0 | 4.1.1 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-48962 | HIGH / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-48962 | HIGH / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-48962 | HIGH / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-48962 | HIGH / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53613 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | 2.41.5 | Resolved/removed |
| CVE-2026-53615 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-53783 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53784 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53785 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53789 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53790 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53791 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53793 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53795 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53802 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-53803 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-54369 | HIGH / OS | libacl1 | 2.3.1-3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.3.2 | Remaining |
| CVE-2026-54369 | HIGH / OS | libacl1 | 2.3.2-2+b1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.3.2 | Remaining |
| CVE-2026-54399 | HIGH / Application | org.apache.httpcomponents.core5:httpcore5 | 5.0.2 | 5.4.3, 5.5-beta2 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57432 | HIGH / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57432 | HIGH / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57432 | HIGH / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-57432 | HIGH / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57433 | HIGH / OS | libperl5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57433 | HIGH / OS | perl | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-57433 | HIGH / OS | perl-base | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | 5.40.1 | Resolved/removed |
| CVE-2026-57433 | HIGH / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-58471 | HIGH / OS | wget | 1.21.3-1+deb12u1 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-58472 | HIGH / OS | wget | 1.21.3-1+deb12u1 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-59999 | HIGH / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-60000 | HIGH / OS | openssh-client | 1:9.2p1-2+deb12u10 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-6276 | HIGH / OS | curl | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-6276 | HIGH / OS | libcurl3-gnutls | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-6276 | HIGH / OS | libcurl4 | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-66046 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-68497 | HIGH / Application | com.fasterxml.jackson.core:jackson-databind | 2.18.8 | 2.18.10, 2.21.6, 2.22.2 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-69152 | HIGH / Application | brace-expansion | 2.0.2 | 1.1.18, 2.1.4, 3.0.6, 5.0.9 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-69192 | HIGH / Application | ip-address | 10.1.0 | 10.3.1 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-70452 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70455 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70456 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70457 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70458 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70460 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70461 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70463 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-70464 | HIGH / OS | rsync | 3.2.7-1+deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-74860 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-76642 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 4.16.0-2+really2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | mount | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-76642 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-77214 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u5 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-78408 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 4.16.0-2+really2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | mount | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78408 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-78409 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 4.16.0-2+really2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | mount | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78409 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-78410 | HIGH / OS | bsdutils | 1:2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | bsdutils | 1:2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libblkid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libblkid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | liblastlog2-2 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libmount1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libmount1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libsmartcols1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libsmartcols1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libuuid1 | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | libuuid1 | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | login | 1:4.16.0-2+really2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 4.16.0-2+really2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | mount | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | mount | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | util-linux | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | util-linux | 2.41.5-0+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 2.41.5 | Remaining |
| CVE-2026-78410 | HIGH / OS | util-linux-extra | 2.38.1-5+deb12u3 | not available | airflow, airflow-test, frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-78667 | HIGH / Application | stdlib | v1.26.8 | 1.26.9, 1.27.2 | airflow, airflow-test | jaeger | package/copy absent | Resolved/removed |
| CVE-2026-78667 | HIGH / Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | jaeger | v1.27.1 | Remaining |
| CVE-2026-78669 | HIGH / Application | golang.org/x/net | v0.58.0 | 0.60.0 | jaeger | jaeger | v0.58.0 | Remaining |
| CVE-2026-78669 | HIGH / Application | stdlib | v1.26.8 | 1.26.9, 1.27.2 | airflow, airflow-test | jaeger | package/copy absent | Resolved/removed |
| CVE-2026-78669 | HIGH / Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | jaeger | v1.27.1 | Remaining |
| CVE-2026-8286 | HIGH / OS | curl | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8286 | HIGH / OS | libcurl3-gnutls | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8286 | HIGH / OS | libcurl4 | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8458 | HIGH / OS | curl | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8458 | HIGH / OS | libcurl3-gnutls | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8458 | HIGH / OS | libcurl4 | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-84782 | HIGH / OS | libssl3 | 3.0.20-1~deb12u2 | 3.0.22-1~deb12u2 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-84782 | HIGH / OS | openssl | 3.0.20-1~deb12u2 | 3.0.22-1~deb12u2 | airflow, airflow-test | none | 3.5.7 | Resolved/removed |
| CVE-2026-86138 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-86140 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-86142 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-86143 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-86144 | HIGH / OS | libxml2 | 2.9.14+dfsg-1.3~deb12u6 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8927 | HIGH / OS | curl | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8927 | HIGH / OS | libcurl3-gnutls | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-8927 | HIGH / OS | libcurl4 | 7.88.1-10+deb12u15 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-89407 | HIGH / Application | com.fasterxml.jackson.core:jackson-core | 2.18.8 | 2.18.11, 2.21.7, 2.22.3 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-89425 | HIGH / Application | com.fasterxml.jackson.core:jackson-core | 2.18.8 | 2.21.7, 2.22.3, 2.18.11 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-91776 | HIGH / Application | com.fasterxml.jackson.core:jackson-databind | 2.18.8 | 2.18.11, 2.21.7, 2.22.3 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-91777 | HIGH / Application | com.fasterxml.jackson.core:jackson-databind | 2.18.8 | 2.21.7, 2.18.11, 2.22.3 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-93748 | HIGH / Application | http-cache-semantics | 4.2.0 | not available | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-93990 | HIGH / OS | libexpat1 | 2.5.0-1+deb12u3 | 2.5.0-1+deb12u4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-9496 | HIGH / Application | pacote | 19.0.2 | 21.5.1 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-9496 | HIGH / Application | pacote | 20.0.1 | 21.5.1 | frontend | none | package/copy absent | Resolved/removed |
| CVE-2026-9538 | HIGH / OS | libperl5.36 | 5.36.0-7+deb12u3 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-9538 | HIGH / OS | perl | 5.36.0-7+deb12u3 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-9538 | HIGH / OS | perl-base | 5.36.0-7+deb12u3 | not available | airflow, airflow-test | agent, airflow, airflow-test, database, frontend | 5.40.1 | Remaining |
| CVE-2026-9538 | HIGH / OS | perl-base | 5.36.0-7+deb12u4 | not available | frontend | agent, airflow, airflow-test, database, frontend | 5.40.1 | Remaining |
| CVE-2026-9538 | HIGH / OS | perl-base | 5.40.1-6+deb13u1 | not available | agent, database | agent, airflow, airflow-test, database, frontend | 5.40.1 | Remaining |
| CVE-2026-9538 | HIGH / OS | perl-modules-5.36 | 5.36.0-7+deb12u3 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-96512 | HIGH / OS | sudo | 1.9.13p3-1+deb12u4 | not available | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| CVE-2026-97031 | HIGH / Application | stdlib | v1.26.8 | 1.26.9, 1.27.2 | airflow, airflow-test | jaeger | package/copy absent | Resolved/removed |
| CVE-2026-97031 | HIGH / Application | stdlib | v1.27.1 | 1.26.9, 1.27.2 | jaeger | jaeger | v1.27.1 | Remaining |
| CVE-2026-97687 | HIGH / Application | urllib3 | 2.7.0 | 2.8.0 | agent, airflow, airflow-test | none | 2.8.0 | Resolved/removed |
| CVE-2026-97689 | HIGH / Application | urllib3 | 2.7.0 | 2.8.0 | agent, airflow, airflow-test | none | 2.8.0 | Resolved/removed |
| GHSA-2g87-pp6c-29x5 | HIGH / Application | aiohttp | 3.14.3 | 3.14.4 | airflow, airflow-test | none | package/copy absent | Resolved/removed |
| GHSA-6v7p-g79w-8964 | HIGH / Application | msgpack | 1.1.2 | 1.2.1 | agent, airflow, airflow-test | none | package/copy absent | Resolved/removed |

## Interpretation and evidence

- All 23 baseline CRITICAL findings are absent from final reports. Final strict gates still fail where HIGH findings remain.
- The remaining 44 OS findings have no vendor fixed version in the scan. The five Jaeger application findings have fixed library/toolchain versions, but no validated published replacement binary was available.
- Actual compatibility evidence, image counts, sources, failed intermediate checks and limitations are in [CI.md](../CI.md#step-71b-remediation-results).
- Full JSON/SBOM/table evidence is retained locally under ignored `local/results/step71/` and `local/results/step71-remediation/`; runtime fixture credentials and raw environment data are excluded from this inventory.
