# Public repository quality review

Reviewed 2026-10-30 (America/Chicago), against public baseline `8dff277`.
This is a local follow-up review; no commit, push or history rewrite was performed.

## Confirmed mistakes and corrections

- Publication, CI and security introductions still described an unpublished update.
  Current status now identifies the published commit and actual hosted results.
- The README cited only an older local scan despite available hosted evidence.
  [Hosted baseline results](HOSTED_BASELINE.md) now provide exact per-image counts,
  source commit and workflow links, distinguishing package findings from CVEs.
- Four root milestone reports obscured the main navigation. They now live here;
  links were updated. The original preparation record is retained separately as
  [dated history](PUBLICATION_READINESS_2026-10-29.md).
- Root Compose and unified-launcher instructions used different ports and database
  prerequisites without enough context. Monitoring runbooks now identify that
  distinction. Root `.env.example` now includes the required infrastructure admin
  password placeholder and a distinct runtime identity. Python guidance is 3.12,
  matching the agent's `<3.13` package constraint.
- Main component introductions used implementation-step language. They now describe
  service behavior. Historical evidence keeps milestone numbers and honest limits.
- The architecture diagram omitted the banking proxy connection and left the
  approval boundary disconnected. Those relationships are now shown explicitly.
- `backups/` contained legacy verification source, not dumps. Its new README
  explains side effects, obsolete authentication assumptions and disposable-only
  use. No meaningful verification source was removed.
- A historical transient localhost trace was presented as a clickable evidence
  link. Its ID is now retained as text with its lifetime explained.

## Verification and public-file review

- Local Markdown targets, image targets and heading anchors checked across all
  public Markdown; no unresolved local reference found. Markdown parsed with
  Prettier; fences and UTF-8 checked. Historical reports retain their content.
- All five Mermaid blocks rendered with Mermaid CLI 12.0.0. The revised README
  diagram and the workspace screenshot were visually inspected. No customer data
  is visible in the screenshot; its static-preview label remains explicit.
- Fifty-nine external links checked. Ollama rejected HEAD but passed GET. CISA's
  catalog returned HTTP 403 for both; its link remains because this does not
  establish that the destination is missing. Historical localhost service/example
  URLs are not treated as live public endpoints.
- CI/security/launcher contracts: **72 passed**, warnings treated as errors. No
  banking database or cloud inference was used. Full application suites and live
  integration were not rerun for these documentation/template changes.
- Scoped secret/sensitive-file checks cover current public files and reachable
  named history blobs, provider/private-key/AWS patterns, known local secret values,
  excluded private banking UUIDs, unsafe paths, case collisions and files over
  1 MiB. No matching secret/private-data or unsafe public artifact was found.
  Five broad credential-literal matches were reviewed as synthetic values or
  generated-container assignment syntax. This is not proof that no unknown secret
  could exist. Private outputs remain ignored under `.publication/`.
- `local/` contains launcher/fixture source and configuration, not tracked runtime
  credentials/results. `backups/` contains authored verification source only.
  Application code, tests, workflows, lockfiles, Dockerfiles, security controls and
  migrations are preserved. No development repository file was edited.
- `git diff --check` passed with the repository's CR-at-EOL handling.

## Security status and remaining limits

[Application CI](https://github.com/Bharathraj009/bankops-ai/actions/runs/41002225074)
passed for the public baseline. Its hosted image run has five gates blocked by
outstanding HIGH vulnerabilities, zero CRITICAL, and unchanged strict thresholds.
The seven retained scan artifacts were checked directly against their source SHA.
This review does not claim a fresh image scan or production security approval.

Docker Desktop's Linux engine was unavailable, so the attempted fresh actionlint
container run could not execute. The workflow YAML contract tests passed; workflows
were not changed. No Docker stack was started to work around that limitation.

Manual investigation initiation, mocked-only cloud inference verification,
synthetic data, unresolved vulnerabilities, platform-specific historical harnesses
and non-production status remain explicit. No performance benchmark was added.
No `LICENSE` file is present; selecting a license remains an owner decision.

## GitHub About suggestion

The current description starts with "Enterprise Banking & AI Reliability Platform",
which is broader than the verified portfolio scope. Suggested replacement:

> Banking integrity and incident-investigation demo with Java, PostgreSQL,
> LangGraph, React, observability, read-only reconciliation and human approvals.

No GitHub metadata was modified.

## Proposed normal follow-up commit

```text
docs: audit public repository and clarify verification status

Document published baseline 8dff277 and its hosted security gates.
Archive dated verification records and repair documentation navigation.
Clarify legacy setup, credential templates and non-production limitations.
```

Review and explicit approval are required before committing or pushing.
No rebase, squash, amendment, force-push or history deletion is proposed.
