# Hosted baseline verification

Reviewed 2026-10-30 (America/Chicago). Public source commit:
[`8dff277`](https://github.com/Bharathraj009/bankops-ai/commit/8dff2773c26471544afc25685294df53d4a4dc75).

[Application CI](https://github.com/Bharathraj009/bankops-ai/actions/runs/41002225074)
passed. [Image security](https://github.com/Bharathraj009/bankops-ai/actions/runs/41002225089)
blocked five strict vulnerability gates. All seven image analyses and SBOMs
completed. This review checked retained `build.json` source SHAs and `scan.json`
contents directly; the GitHub API independently confirmed job conclusions and
failed vulnerability-gate steps.

| Image | HIGH | CRITICAL | Gate |
| --- | --- | --- | --- |
| banking | 0 | 0 | Passed |
| agent | 44 | 0 | Blocked |
| airflow | 44 | 0 | Blocked |
| airflow-test | 44 | 0 | Blocked |
| frontend | 43 | 0 | Blocked |
| database | 44 | 0 | Blocked |
| jaeger | 0 | 0 | Passed |

Across images, 44 unique advisory/package/installed-version findings cover eight
CVEs; these are not 44 distinct CVEs. All are HIGH OS findings with no fixed
version reported in that scan. Zero CRITICAL and zero HIGH application findings
were reported. This dated result does not predict future vulnerability feeds.
Strict HIGH/CRITICAL gates include unfixed findings and remain unchanged.
No deployment or container publishing is performed by these workflows.
