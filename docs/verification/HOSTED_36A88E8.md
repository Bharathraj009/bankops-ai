# Hosted verification of the documentation baseline

Source: [`36a88e892c10a7ffba6660a9096b42d5a65f812b`](https://github.com/Bharathraj009/bankops-ai/commit/36a88e892c10a7ffba6660a9096b42d5a65f812b).
Verified 2026-10-30 (America/Chicago) after the normal follow-up push.

[Application CI](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960966)
passed all four jobs: Java banking/database authorization, Python agent,
Airflow/PostgreSQL security, and React/TypeScript/Chromium.
[Image security](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960956)
completed seven builds, scans and SBOMs. Five gates failed at the strict vulnerability
step; banking and Jaeger passed.

| Image | HIGH | CRITICAL | Gate |
| --- | --- | --- | --- |
| banking | 0 | 0 | Passed |
| agent | 44 | 0 | Blocked |
| airflow | 44 | 0 | Blocked |
| airflow-test | 44 | 0 | Blocked |
| frontend | 43 | 0 | Blocked |
| database | 44 | 0 | Blocked |
| jaeger | 0 | 0 | Passed |

The seven retained `build.json` source SHAs and CycloneDX SBOMs were verified;
`scan.json` records deduplicate to 44 advisory/package/installed-version findings
across eight CVEs, all HIGH, with zero CRITICAL. No fixed version was reported for
the outstanding OS findings in those artifacts. Counts are dated scan results;
HIGH/CRITICAL thresholds and unfixed coverage remain unchanged.

Remote `main` matched the commit and all 424 published file blobs matched the local
commit. README and architecture sources, GitHub Mermaid markup and screenshot
bytes were verified. Architecture diagrams were rendered and visually inspected.
GitHub About was updated to the technical description approved for that push.
The publication checkout was clean after verification; history was preserved.

These hosted application checks complement the separate
[scheduled integration record](STEP75_INTEGRATION_REPORT.md), which documents its
own disposable fixture and synthetic-data scope. Neither record establishes a
production deployment or successful live cloud inference.
