# Publication status and verification

Published baseline:
[`36a88e892c10a7ffba6660a9096b42d5a65f812b`](https://github.com/Bharathraj009/bankops-ai/commit/36a88e892c10a7ffba6660a9096b42d5a65f812b),
branch `main`. The documentation quality-audit follow-up was committed and pushed
after implementation commit `8dff277`.

[Application CI](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960966)
passed all four jobs. [Image security](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960956)
analyzed all seven targets and generated their SBOMs; five strict gates blocked on
HIGH findings. The scans contain 44 unique HIGH package findings across eight CVEs
and zero CRITICAL. Banking and Jaeger passed. See [per-image verification](docs/verification/HOSTED_36A88E8.md).

The [2026-10-29 preparation record](docs/verification/PUBLICATION_READINESS_2026-10-29.md)
and [first quality audit](docs/verification/QUALITY_AUDIT_2026-10-30.md) preserve the
state at their respective local reviews, before those changes were published.
Their pending-commit/approval wording is historical. The original
[implementation scan record](docs/verification/HOSTED_BASELINE.md) remains available.

The [testing guide](docs/TESTING.md) documents tool and database prerequisites,
synthetic browser fixtures and the separate scheduler integration. The
[deployment limitations](README.md#deployment-scope-and-limitations) and
[security controls](SECURITY.md) describe the remaining engineering work and risks.
Hosted results apply to their source commit; later changes require new checks.
